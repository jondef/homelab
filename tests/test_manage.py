import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import manage


def make_repo(root: Path):
    """Minimal repo skeleton with one podman service, one podman infra unit
    and one docker service."""
    (root / "podman/infrastructure/traefik").mkdir(parents=True)
    (root / "podman/infrastructure/traefik/traefik.container").write_text("[Container]\n")
    (root / "podman/infrastructure/traefik/traefik-public.network").write_text("[Network]\n")
    (root / "podman/infrastructure/traefik/web.socket").write_text("[Socket]\n")
    (root / "podman/infrastructure/traefik/websecure.socket").write_text("[Socket]\n")
    (root / "podman/infrastructure/traefik/dynamic").mkdir()
    (root / "podman/infrastructure/traefik/dynamic/legacy-docker1.yml").write_text("tcp:\n")
    (root / "podman/services/whoami").mkdir(parents=True)
    (root / "podman/services/whoami/whoami.container").write_text("[Container]\n")
    (root / "docker/services/gitea").mkdir(parents=True)
    (root / "docker/services/gitea/docker-compose.yml").write_text("services:\n")
    (root / ".env").write_text("DOCKERDIR=/mnt/appdata\nHOST_DOMAIN=example.com\n# comment\n")


class TestPodmanQuadletManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)
        self.quadlet_dir = self.root / "quadlets"
        self.systemd_user_dir = self.root / "systemd-user"
        self.mgr = manage.PodmanQuadletManager(
            base_path=self.root, quadlet_dir=self.quadlet_dir,
            systemd_user_dir=self.systemd_user_dir)
        # dockerdir is a plain attribute set from .env's DOCKERDIR (which is
        # the real "/mnt/appdata" in the fixture, matching production) -
        # override it here so the dynamic/ sync in this test stays inside
        # the tmp tree instead of touching the real filesystem path.
        self.mgr.dockerdir = self.root / "appdata"

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_infrastructure_service(self):
        self.assertEqual(self.mgr.get_service_path("traefik"),
                         self.root / "podman/infrastructure/traefik")

    def test_finds_application_service(self):
        self.assertEqual(self.mgr.get_service_path("whoami"),
                         self.root / "podman/services/whoami")

    def test_unknown_service_is_none(self):
        self.assertIsNone(self.mgr.get_service_path("gitea"))  # docker, not podman

    def test_container_units(self):
        self.assertEqual(self.mgr.container_units("traefik"), ["traefik.service"])

    def test_sync_files_copies_units_and_dynamic(self):
        self.mgr.sync_files("traefik")
        self.assertTrue((self.quadlet_dir / "traefik.container").exists())
        self.assertTrue((self.quadlet_dir / "traefik-public.network").exists())
        # dynamic/ goes to ${DOCKERDIR}/<service>/dynamic/ - here redirected
        # into the tmp tree via dockerdir override
        self.assertTrue((self.mgr.dockerdir / "traefik/dynamic/legacy-docker1.yml").exists())

    def test_sync_files_routes_sockets_to_systemd_user_dir_not_quadlet_dir(self):
        """.socket units are plain systemd units, not quadlets - they must
        land in ~/.config/systemd/user/ (here redirected via
        systemd_user_dir), not ~/.config/containers/systemd/."""
        self.mgr.sync_files("traefik")
        self.assertTrue((self.systemd_user_dir / "web.socket").exists())
        self.assertTrue((self.systemd_user_dir / "websecure.socket").exists())
        self.assertFalse((self.quadlet_dir / "web.socket").exists())
        self.assertFalse((self.quadlet_dir / "websecure.socket").exists())

    def test_container_units_excludes_sockets(self):
        # .socket files must not be mistaken for quadlet-generated services
        self.assertEqual(self.mgr.container_units("traefik"), ["traefik.service"])

    def test_socket_units_lists_socket_files(self):
        self.assertEqual(self.mgr.socket_units("traefik"), ["web.socket", "websecure.socket"])

    def test_socket_units_empty_for_service_without_sockets(self):
        self.assertEqual(self.mgr.socket_units("whoami"), [])

    @patch("manage.subprocess.run")
    def test_start_service_enables_socket_units(self, mock_run):
        """A from-scratch `start` must enable+start any .socket units itself
        - sync_files() only copies them into place, it doesn't activate
        them, and nothing else in the start path used to touch sockets at
        all (the gap this test guards against)."""
        self.assertTrue(self.mgr.start_service("traefik"))
        calls = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(["systemctl", "--user", "enable", "--now", "web.socket"], calls)
        self.assertIn(["systemctl", "--user", "enable", "--now", "websecure.socket"], calls)
        self.assertIn(["systemctl", "--user", "start", "traefik.service"], calls)

    @patch("manage.subprocess.run")
    def test_start_service_without_sockets_skips_enable(self, mock_run):
        """Services with no .socket files (e.g. whoami) must not trigger any
        `enable` calls - the socket-activation path is opt-in per service."""
        self.assertTrue(self.mgr.start_service("whoami"))
        calls = [call.args[0] for call in mock_run.call_args_list]
        self.assertTrue(all("enable" not in call for call in calls))
        self.assertIn(["systemctl", "--user", "start", "whoami.service"], calls)

    @patch("manage.subprocess.run")
    def test_start_service_enable_failure_fails_the_run(self, mock_run):
        """enable --now failing (as opposed to it being a no-op on an
        already-active socket) must surface as an overall start_service()
        failure, not be silently swallowed."""
        import subprocess as sp

        def side_effect(cmd, **kwargs):
            if cmd[:3] == ["systemctl", "--user", "enable"]:
                raise sp.CalledProcessError(1, cmd)
            return MagicMock()

        mock_run.side_effect = side_effect
        self.assertFalse(self.mgr.start_service("traefik"))


class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_docker_manager_ignores_podman_tree(self):
        docker = manage.DockerComposeManager(str(self.root))
        self.assertIsNone(docker.get_service_path("whoami"))
        self.assertIsNotNone(docker.get_service_path("gitea"))

    def test_parse_env(self):
        env = manage.parse_env(self.root / ".env")
        self.assertEqual(env["DOCKERDIR"], "/mnt/appdata")
        self.assertEqual(env["HOST_DOMAIN"], "example.com")
        self.assertNotIn("# comment", env)


class TestResolveDispatch(unittest.TestCase):
    """Covers main()'s service-to-manager resolution, in particular the
    policy for docker's dependency check: a podman-only host (docker
    unavailable) must still be able to work through the podman services in
    a --all/list batch, even though the same repo also has docker-tree
    services listed first (docker/services/gitea sorts before
    podman/services/whoami - see make_repo)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)
        self.manager = manage.DockerComposeManager(str(self.root))
        self.podman_manager = manage.PodmanQuadletManager(base_path=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_mode_skips_docker_services_when_docker_unavailable(self):
        self.manager.check_dependencies = lambda: False
        targets, skipped = manage.resolve_dispatch(
            ["gitea", "whoami"], self.manager, self.podman_manager, all_mode=True)
        self.assertEqual(skipped, ["gitea"])
        self.assertEqual([service for service, _ in targets], ["whoami"])
        self.assertIs(targets[0][1], self.podman_manager)

    def test_named_docker_service_aborts_when_docker_unavailable(self):
        self.manager.check_dependencies = lambda: False
        with self.assertRaises(SystemExit):
            manage.resolve_dispatch(["gitea"], self.manager, self.podman_manager, all_mode=False)

    def test_all_mode_dispatches_normally_when_docker_available(self):
        self.manager.check_dependencies = lambda: True
        targets, skipped = manage.resolve_dispatch(
            ["gitea", "whoami"], self.manager, self.podman_manager, all_mode=True)
        self.assertEqual(skipped, [])
        self.assertEqual([service for service, _ in targets], ["gitea", "whoami"])
        self.assertIs(targets[0][1], self.manager)
        self.assertIs(targets[1][1], self.podman_manager)

    def test_podman_only_service_never_checks_docker_dependencies(self):
        def fail(): raise AssertionError("docker dependency check should not run")
        self.manager.check_dependencies = fail
        targets, skipped = manage.resolve_dispatch(
            ["whoami"], self.manager, self.podman_manager, all_mode=False)
        self.assertEqual(skipped, [])
        self.assertEqual(targets, [("whoami", self.podman_manager)])


if __name__ == "__main__":
    unittest.main()
