import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import manage


def make_repo(root: Path):
    """Minimal repo skeleton with one podman service, one podman infra unit
    and one docker service."""
    (root / "podman/infrastructure/traefik").mkdir(parents=True)
    (root / "podman/infrastructure/traefik/traefik.container").write_text("[Container]\n")
    (root / "podman/infrastructure/traefik/traefik-public.network").write_text("[Network]\n")
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
        self.mgr = manage.PodmanQuadletManager(
            base_path=self.root, quadlet_dir=self.quadlet_dir)
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


if __name__ == "__main__":
    unittest.main()
