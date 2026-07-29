#!/usr/bin/env python3
"""
Homeserver Stack Manager

Runs ON the docker host: compose bind-mounts resolve against the daemon,
so this repo and the containers must live on the same machine.
Usage: python manage.py <action> <service>
Actions: start, stop, restart, update, logs, status, list
Services: immich, n8n, nextcloud, traefik, or 'all'
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import json


class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    RESET = '\033[0m'


class Logger:
    """Simple logger with colored output"""

    @staticmethod
    def info(message: str):
        print(f"{Colors.BLUE}[INFO]{Colors.RESET} {message}")

    @staticmethod
    def success(message: str):
        print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} {message}")

    @staticmethod
    def warning(message: str):
        print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} {message}")

    @staticmethod
    def error(message: str):
        print(f"{Colors.RED}[ERROR]{Colors.RESET} {message}")

    @staticmethod
    def header(message: str):
        print(f"\n{Colors.CYAN}{'=' * 50}{Colors.RESET}")
        print(f"{Colors.CYAN}{message}{Colors.RESET}")
        print(f"{Colors.CYAN}{'=' * 50}{Colors.RESET}")


class DockerComposeManager:
    """Manages Docker Compose stacks for homeserver services"""

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.docker_dir = self.base_path / "docker"
        self.services_dir = self.docker_dir / "services"
        self.infrastructure_dir = self.docker_dir / "infrastructure"

        # Create directories if they don't exist
        self.docker_dir.mkdir(exist_ok=True)
        self.services_dir.mkdir(exist_ok=True)
        self.infrastructure_dir.mkdir(exist_ok=True)

    def check_dependencies(self) -> bool:
        """Check that docker and the compose plugin are available.

        This script is meant to run ON the docker host, so it talks to the local
        daemon. Bind-mount paths in the compose files are resolved by the daemon,
        which is why the repo has to live on the same machine as the containers.
        """
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            subprocess.run(["docker", "compose", "version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            Logger.error("docker or the compose plugin not found. Install docker-ce and docker-compose-plugin.")
            return False

        # Refuse to run against a remote daemon: the compose files bind-mount
        # /mnt/appdata and /mnt/main, which only exist on the docker host.
        try:
            result = subprocess.run(["docker", "context", "show"],
                                    capture_output=True, text=True, check=True)
            context = result.stdout.strip()
            if context != "default":
                Logger.error(
                    f"Docker context is '{context}', expected 'default'.\n"
                    "This script runs on the docker host itself - run it there, or\n"
                    "switch back with: docker context use default"
                )
                return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # no context support is fine, it means the local daemon

        return True

    def get_service_path(self, service: str) -> Optional[Path]:
        """Get the path to a service directory"""
        # Check infrastructure first
        infra_path = self.infrastructure_dir / service
        if infra_path.exists() and (infra_path / "docker-compose.yml").exists():
            return infra_path

        # Then check services
        service_path = self.services_dir / service
        if service_path.exists() and (service_path / "docker-compose.yml").exists():
            return service_path

        return None

    def get_all_services(self) -> Dict[str, List[str]]:
        """Get all available services organized by type"""
        services = {"infrastructure": [], "applications": []}

        # Get infrastructure services
        if self.infrastructure_dir.exists():
            for item in self.infrastructure_dir.iterdir():
                if item.is_dir() and (item / "docker-compose.yml").exists():
                    services["infrastructure"].append(item.name)

        # Get application services
        if self.services_dir.exists():
            for item in self.services_dir.iterdir():
                if item.is_dir() and (item / "docker-compose.yml").exists():
                    services["applications"].append(item.name)

        # Sort both lists
        services["infrastructure"].sort()
        services["applications"].sort()

        return services

    def _run_compose_command(self, service: str, command: List[str],
                             capture_output: bool = False) -> subprocess.CompletedProcess:
        """Run a docker compose command for a specific service"""
        service_path = self.get_service_path(service)
        if not service_path:
            raise ValueError(f"Service '{service}' not found")

        env_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        full_command = ["docker", "compose", "--env-file", env_file_path] + command

        Logger.info(f"Running: {' '.join(full_command)} in {service_path}")

        try:
            result = subprocess.run(
                full_command,
                cwd=service_path,
                capture_output=capture_output,
                text=True,
                check=True
            )
            return result
        except subprocess.CalledProcessError as e:
            Logger.error(f"Command failed for {service}: {e}")
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr)
            raise

    def start_service(self, service: str) -> bool:
        """Start a service"""
        try:
            Logger.info(f"Starting {service}...")
            self._run_compose_command(service, ["up", "-d"])
            Logger.success(f"Started {service}")
            return True
        except Exception as e:
            Logger.error(f"Failed to start {service}: {e}")
            return False

    def stop_service(self, service: str) -> bool:
        """Stop a service"""
        try:
            Logger.info(f"Stopping {service}...")
            self._run_compose_command(service, ["down"])
            Logger.success(f"Stopped {service}")
            return True
        except Exception as e:
            Logger.error(f"Failed to stop {service}: {e}")
            return False

    def restart_service(self, service: str) -> bool:
        """Restart a service"""
        Logger.info(f"Restarting {service}...")
        if self.stop_service(service):
            time.sleep(2)  # Brief pause between stop and start
            return self.start_service(service)
        return False

    def update_service(self, service: str) -> bool:
        """Update a service (pull latest images and restart)"""
        try:
            Logger.info(f"Updating {service}...")

            # Pull latest images
            Logger.info(f"Pulling latest images for {service}...")
            self._run_compose_command(service, ["pull"])

            # Stop and start with new images
            Logger.info(f"Restarting {service} with updated images...")
            self._run_compose_command(service, ["down"])
            self._run_compose_command(service, ["up", "-d"])

            Logger.success(f"Updated {service}")
            return True
        except Exception as e:
            Logger.error(f"Failed to update {service}: {e}")
            return False

    def show_logs(self, service: str, follow: bool = True, tail: int = 100):
        """Show logs for a service"""
        try:
            Logger.info(f"Showing logs for {service}...")
            command = ["logs"]
            if follow:
                command.append("-f")
            if tail:
                command.extend(["--tail", str(tail)])

            # Don't capture output for logs - let them stream to console
            self._run_compose_command(service, command, capture_output=False)
        except KeyboardInterrupt:
            Logger.info("Log streaming stopped")
        except Exception as e:
            Logger.error(f"Failed to show logs for {service}: {e}")

    def show_status(self, service: str) -> bool:
        """Show status of a service"""
        try:
            Logger.info(f"Status for {service}:")
            result = self._run_compose_command(service, ["ps"], capture_output=True)
            print(result.stdout)
            return True
        except Exception as e:
            Logger.error(f"Failed to get status for {service}: {e}")
            return False

    def prune(self) -> bool:
        """Reclaim disk space. Deliberate only - never run automatically.

        Uses "image prune" (dangling layers) rather than "system prune -a".
        The -a form deletes any image without a *running* container, so a
        temporarily stopped service would lose its image and have to re-pull.

        Note watchtower already sets WATCHTOWER_CLEANUP=true, which removes the
        superseded image after each update - that is the main source of growth,
        so this is usually a no-op.
        """
        Logger.info("Reclaiming space (dangling images, stopped containers, build cache)...")
        subprocess.run(["docker", "system", "df"], check=False)
        for target in (["image", "prune", "-f"],
                       ["container", "prune", "-f"],
                       ["builder", "prune", "-f"]):
            subprocess.run(["docker"] + target, check=False)
        Logger.success("Prune complete")
        subprocess.run(["docker", "system", "df"], check=False)
        return True

    def is_service_running(self, service: str) -> bool:
        """Check if a service is currently running"""
        try:
            result = self._run_compose_command(service, ["ps", "-q"], capture_output=True)
            return bool(result.stdout.strip())
        except:
            return False


def parse_env(env_path) -> Dict[str, str]:
    """Tiny KEY=VALUE parser for the repo .env (no quoting rules needed)."""
    env = {}
    for line in Path(env_path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


class PodmanQuadletManager:
    """Manages rootless podman quadlet services.

    Unit files live in the repo under podman/{infrastructure,services}/<name>/
    and must be synced into ~/.config/containers/systemd/ before the systemd
    user manager can see them. Everything here talks to the *user* manager -
    no root, no daemon. Run on the podman host, same reasoning as the compose
    manager: bind-mount paths only exist there.
    """

    # .socket is a plain systemd unit, not a quadlet - quadlet only
    # generates services from .container/.network/.volume/.pod. Sockets are
    # used for the traefik pasta-source-IP fallback (see
    # podman/infrastructure/traefik/{web,websecure}.socket): they let the
    # host systemd user manager own port 80/443 and hand the accepted fd to
    # traefik.service, so the real peer address survives instead of being
    # rewritten by rootless port publishing on the bridge network.
    UNIT_SUFFIXES = (".container", ".network", ".volume", ".pod", ".socket")

    def __init__(self, base_path: Optional[str] = None, quadlet_dir: Optional[str] = None,
                 systemd_user_dir: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.podman_dir = self.base_path / "podman"
        self.services_dir = self.podman_dir / "services"
        self.infrastructure_dir = self.podman_dir / "infrastructure"
        self.quadlet_dir = Path(quadlet_dir) if quadlet_dir else Path.home() / ".config/containers/systemd"
        # Plain .socket units aren't quadlets - they go straight into the
        # systemd user manager's unit search path, not the quadlet dir.
        self.systemd_user_dir = Path(systemd_user_dir) if systemd_user_dir else Path.home() / ".config/systemd/user"
        env_file = self.base_path / ".env"
        env = parse_env(env_file) if env_file.exists() else {}
        self.dockerdir = Path(env.get("DOCKERDIR", "/mnt/appdata"))

    def get_service_path(self, service: str) -> Optional[Path]:
        for parent in (self.infrastructure_dir, self.services_dir):
            path = parent / service
            if path.is_dir() and any(f.suffix in self.UNIT_SUFFIXES for f in path.iterdir()):
                return path
        return None

    def unit_files(self, service: str) -> List[Path]:
        path = self.get_service_path(service)
        if not path:
            raise ValueError(f"Podman service '{service}' not found")
        return sorted(f for f in path.iterdir() if f.suffix in self.UNIT_SUFFIXES)

    def container_units(self, service: str) -> List[str]:
        """Systemd unit names quadlet generates from the .container files."""
        return [f.stem + ".service" for f in self.unit_files(service)
                if f.suffix == ".container"]

    def sync_files(self, service: str):
        """Copy unit files to the quadlet dir (or, for plain .socket units,
        the systemd user unit dir) and dynamic/ config (if any) to
        ${DOCKERDIR}/<service>/dynamic/. No systemd interaction."""
        import shutil
        self.quadlet_dir.mkdir(parents=True, exist_ok=True)
        self.systemd_user_dir.mkdir(parents=True, exist_ok=True)
        for f in self.unit_files(service):
            dest_dir = self.systemd_user_dir if f.suffix == ".socket" else self.quadlet_dir
            shutil.copy2(f, dest_dir / f.name)
        dynamic = self.get_service_path(service) / "dynamic"
        if dynamic.is_dir():
            target = self.dockerdir / service / "dynamic"
            target.mkdir(parents=True, exist_ok=True)
            for f in dynamic.iterdir():
                if f.is_file():
                    shutil.copy2(f, target / f.name)

    def sync(self, service: str):
        self.sync_files(service)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

    def _systemctl(self, action: str, service: str) -> bool:
        try:
            for unit in self.container_units(service):
                Logger.info(f"systemctl --user {action} {unit}")
                subprocess.run(["systemctl", "--user", action, unit], check=True)
            return True
        except (subprocess.CalledProcessError, ValueError) as e:
            Logger.error(f"Failed to {action} {service}: {e}")
            return False

    def start_service(self, service: str) -> bool:
        self.sync(service)
        ok = self._systemctl("start", service)
        if ok:
            Logger.success(f"Started {service}")
        return ok

    def stop_service(self, service: str) -> bool:
        ok = self._systemctl("stop", service)
        if ok:
            Logger.success(f"Stopped {service}")
        return ok

    def restart_service(self, service: str) -> bool:
        self.sync(service)
        return self._systemctl("restart", service)

    def update_service(self, service: str) -> bool:
        """Quadlets update via podman auto-update (AutoUpdate=registry)."""
        self.sync(service)
        try:
            subprocess.run(["podman", "auto-update"], check=True)
            Logger.success(f"auto-update run (covers {service} and all AutoUpdate units)")
            return True
        except subprocess.CalledProcessError as e:
            Logger.error(f"auto-update failed: {e}")
            return False

    def show_logs(self, service: str, follow: bool = True, tail: int = 100):
        for unit in self.container_units(service):
            cmd = ["journalctl", "--user", "-u", unit, "-n", str(tail)]
            if follow:
                cmd.append("-f")
            try:
                subprocess.run(cmd)
            except KeyboardInterrupt:
                Logger.info("Log streaming stopped")

    def show_status(self, service: str) -> bool:
        ok = True
        for unit in self.container_units(service):
            result = subprocess.run(["systemctl", "--user", "status", unit, "--no-pager"])
            ok = ok and result.returncode == 0
        return ok

    def is_service_running(self, service: str) -> bool:
        try:
            return all(
                subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit]).returncode == 0
                for unit in self.container_units(service))
        except ValueError:
            return False


def resolve_dispatch(services: List[str], manager: "DockerComposeManager",
                      podman_manager: "PodmanQuadletManager",
                      all_mode: bool) -> Tuple[List[Tuple[str, Any]], List[str]]:
    """Resolve each requested service to the manager that owns it, applying
    docker's dependency check along the way.

    Podman-only hosts must be able to manage podman services even when
    docker isn't installed - so docker's check_dependencies() runs at most
    once, lazily, the first time a service resolves to the docker manager.
    If it fails:
      - in a --all/list batch, that service (and any later docker service)
        is skipped with a warning instead of aborting the whole batch, so
        the podman services in the same batch still get processed;
      - for a specifically-named service, it's still a hard failure
        (sys.exit) - a docker service was asked for by name on a host that
        can't run it, which should fail loudly rather than silently.

    Returns (targets, skipped): targets is the ordered list of
    (service, manager) pairs to actually dispatch; skipped is the docker
    services left out because docker is unavailable (only ever non-empty
    when all_mode is True).
    """
    targets: List[Tuple[str, Any]] = []
    skipped: List[str] = []
    docker_ok: Optional[bool] = None

    for service in services:
        if not manager.get_service_path(service) and not podman_manager.get_service_path(service):
            Logger.error(f"Service '{service}' not found")
            Logger.info("Use 'python manage.py list' to see available services")
            sys.exit(1)

        target = podman_manager if podman_manager.get_service_path(service) else manager
        if target is manager:
            if docker_ok is None:
                docker_ok = manager.check_dependencies()
            if not docker_ok:
                if all_mode:
                    skipped.append(service)
                    continue
                sys.exit(1)

        targets.append((service, target))

    return targets, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Homeserver Docker Compose Stack Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage.py start gitea
  python manage.py update immich
  python manage.py logs nextcloud
  python manage.py restart --all
  python manage.py list
  python manage.py prune          # deliberate cleanup, never automatic

Run this on the docker host. Compose resolves bind-mount paths against the
daemon, so the repo, the .env and the containers all have to be on the same
machine - which is why this lives on /mnt/appdata rather than a laptop.
        """
    )

    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "update", "logs", "status", "list", "prune"],
        help="Action to perform"
    )

    parser.add_argument(
        "services",
        nargs="*",
        help="Service name(s) to manage"
    )

    parser.add_argument(
        "--no-follow",
        action="store_true",
        help="Don't follow logs (for logs action)"
    )

    parser.add_argument(
        "--tail",
        type=int,
        default=100,
        help="Number of log lines to show (default: 100)"
    )

    parser.add_argument(
        "--path",
        type=str,
        help="Base path for services (default: script directory)"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Apply action to all services (only start/restart/update/stop/list actions)"
    )

    args = parser.parse_args()

    # Create managers
    manager = DockerComposeManager(args.path)
    podman_manager = PodmanQuadletManager(args.path)

    # Prune takes no service argument - it's docker-only, so check dependencies here
    if args.action == "prune":
        if not manager.check_dependencies():
            sys.exit(1)
        manager.prune()
        sys.exit(0)

    # Handle list action (doesn't need service parameter)
    if args.action == "list":
        Logger.header("Available Services")
        args.all = True

    # Validate that --all and specific services aren't used together
    if args.all and args.services:
        Logger.error("Cannot use --all flag with specific service names")
        sys.exit(1)

    if args.all:
        if args.action not in ["start", "stop", "restart", "update", "status", "list"]:
            Logger.error(f"--all flag is not supported for action '{args.action}'")
            parser.print_help()
            sys.exit(1)
        # Get all services and populate args.services
        all_services = manager.get_all_services()
        args.services = all_services["infrastructure"] + all_services["applications"] + sorted(
            set(p.name for parent in (podman_manager.infrastructure_dir, podman_manager.services_dir)
                if parent.exists() for p in parent.iterdir() if podman_manager.get_service_path(p.name)))
        Logger.info(f"Processing {len(args.services)} services: {', '.join(args.services)}")

    # All other actions need service parameter(s)
    if not args.services:
        Logger.error(f"Service name(s) or --all flag required for action '{args.action}'")
        parser.print_help()
        sys.exit(1)


    # Resolve each requested service to its manager, applying docker's
    # dependency check once (podman-only hosts must still be able to work
    # through the podman services in a --all/list batch even when docker
    # services in the same batch have to be skipped - see resolve_dispatch).
    targets, skipped_docker_services = resolve_dispatch(args.services, manager, podman_manager, args.all)
    if skipped_docker_services:
        Logger.warning(
            f"Docker unavailable - skipping docker-tree services: {', '.join(skipped_docker_services)}")

    # Handle actions
    overall_success = not skipped_docker_services  # a skip means a partial run

    for service, target in targets:
        service_success = False  # Track success for this specific service

        if args.action == "start":
            service_success = target.start_service(service)
        elif args.action == "stop":
            service_success = target.stop_service(service)
        elif args.action == "restart":
            service_success = target.restart_service(service)
        elif args.action == "update":
            service_success = target.update_service(service)
        elif args.action == "list":
            status_indicator = "🟢" if target.is_service_running(service) else "🔴"
            print(f"  {status_indicator} {service}")
            service_success = True
        elif args.action == "logs":
            target.show_logs(service, follow=not args.no_follow, tail=args.tail)
            service_success = True  # Logs don't really "fail"
        elif args.action == "status":
            service_success = target.show_status(service)

        # Update overall success - if any service fails, overall fails
        overall_success = overall_success and service_success

    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()