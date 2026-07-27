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
from typing import List, Optional, Dict, Any
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

    # Create manager
    manager = DockerComposeManager(args.path)

    # Check dependencies
    if not manager.check_dependencies():
        sys.exit(1)

    # Prune takes no service argument
    if args.action == "prune":
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
        args.services = all_services["infrastructure"] + all_services["applications"]
        Logger.info(f"Processing {len(args.services)} services: {', '.join(args.services)}")

    # All other actions need service parameter(s)
    if not args.services:
        Logger.error(f"Service name(s) or --all flag required for action '{args.action}'")
        parser.print_help()
        sys.exit(1)


    # Handle actions
    overall_success = True  # Track overall success across all services

    for service in args.services:
        service_success = False  # Track success for this specific service

        # Check if service exists
        if not manager.get_service_path(service):
            Logger.error(f"Service '{service}' not found")
            Logger.info("Use 'python manage.py list' to see available services")
            sys.exit(1)

        if args.action == "start":
            service_success = manager.start_service(service)
        elif args.action == "stop":
            service_success = manager.stop_service(service)
        elif args.action == "restart":
            service_success = manager.restart_service(service)
        elif args.action == "update":
            service_success = manager.update_service(service)
        elif args.action == "list":
            status_indicator = "🟢" if manager.is_service_running(service) else "🔴"
            print(f"  {status_indicator} {service}")
            service_success = True
        elif args.action == "logs":
            manager.show_logs(service, follow=not args.no_follow, tail=args.tail)
            service_success = True  # Logs don't really "fail"
        elif args.action == "status":
            service_success = manager.show_status(service)

        # Update overall success - if any service fails, overall fails
        overall_success = overall_success and service_success

    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()