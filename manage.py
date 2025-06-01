#!/usr/bin/env python3
"""
Homeserver Stack Manager
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

        # Service startup order (infrastructure first)
        self.startup_order = [
            "traefik",  # Always start traefik first
            "portainer",
            # Add other infrastructure services here
        ]

    def _check_dependencies(self) -> bool:
        """Check if required tools are available"""
        try:
            subprocess.run(["docker", "--version"],
                           capture_output=True, check=True)
            subprocess.run(["docker-compose", "--version"],
                           capture_output=True, check=True)
            result = subprocess.run(["docker", "context", "show"],
                           capture_output=True, text=True, check=True
            )
            current_context = result.stdout.strip()
            if current_context != "homelab":
                Logger.error(
                    f"Docker context is '{current_context}', but 'homelab' is required.\n"
                    "To create and use the correct context, run:\n"
                    "  docker context create homelab --docker \"host=ssh://user@your-server\"\n"
                    "  docker context use homelab"
                )
                return False
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            Logger.error("Docker or docker-compose not found. Please install them.")
            return False

    def _get_service_path(self, service: str) -> Optional[Path]:
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

    def _is_infrastructure_service(self, service: str) -> bool:
        """Check if a service is an infrastructure service"""
        return (self.infrastructure_dir / service).exists()

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
        """Run a docker-compose command for a specific service"""
        service_path = self._get_service_path(service)
        if not service_path:
            raise ValueError(f"Service '{service}' not found")

        env_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        full_command = ["docker-compose", "--env-file", env_file_path] + command
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

    def handle_all_services(self, action: str) -> bool:
        """Handle actions for all services"""
        all_services = self.get_all_services()

        # Combine services in startup order for start/restart/update
        if action in ["start", "restart", "update"]:
            ordered_services = []

            # Add infrastructure services in startup order
            for service in self.startup_order:
                if service in all_services["infrastructure"]:
                    ordered_services.append(service)

            # Add remaining infrastructure services
            for service in all_services["infrastructure"]:
                if service not in ordered_services:
                    ordered_services.append(service)

            # Add application services
            ordered_services.extend(all_services["applications"])

            services_to_process = ordered_services
        else:
            # For stop/status, order doesn't matter as much
            services_to_process = (all_services["infrastructure"] +
                                   all_services["applications"])

        if not services_to_process:
            Logger.warning("No services found!")
            return False

        Logger.header(f"Executing '{action}' for all services")
        Logger.info(f"Services: {', '.join(services_to_process)}")

        success_count = 0
        for service in services_to_process:
            print()  # Add spacing between services
            service_type = "Infrastructure" if self._is_infrastructure_service(service) else "Application"
            Logger.info(f"Processing {service_type.lower()} service: {service}")

            success = False
            if action == "start":
                success = self.start_service(service)
            elif action == "stop":
                success = self.stop_service(service)
            elif action == "restart":
                success = self.restart_service(service)
            elif action == "update":
                success = self.update_service(service)
            elif action == "status":
                success = self.show_status(service)

            if success:
                success_count += 1

            # Small delay between services
            if action in ["start", "restart", "update"]:
                time.sleep(1)

        Logger.header(f"Completed: {success_count}/{len(services_to_process)} services processed successfully")
        return success_count == len(services_to_process)

    def list_services(self):
        """List all available services"""
        services = self.get_all_services()

        Logger.header("Available Services")

        if services["infrastructure"]:
            print(f"\n{Colors.PURPLE}Infrastructure Services:{Colors.RESET}")
            for service in services["infrastructure"]:
                status_indicator = "🟢" if self._is_service_running(service) else "🔴"
                print(f"  {status_indicator} {service}")

        if services["applications"]:
            print(f"\n{Colors.CYAN}Application Services:{Colors.RESET}")
            for service in services["applications"]:
                status_indicator = "🟢" if self._is_service_running(service) else "🔴"
                print(f"  {status_indicator} {service}")

        if not services["infrastructure"] and not services["applications"]:
            Logger.warning("No services found!")
            Logger.info("Create service directories in 'docker/services/' or 'docker/infrastructure/' with docker-compose.yml files")

    def _is_service_running(self, service: str) -> bool:
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
  python manage.py start traefik
  python manage.py update immich
  python manage.py logs nextcloud
  python manage.py restart all
  python manage.py list
        """
    )

    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "update", "logs", "status", "list"],
        help="Action to perform"
    )

    parser.add_argument(
        "service",
        nargs="?",
        help="Service name or 'all' for all services"
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

    args = parser.parse_args()

    # Create manager
    manager = DockerComposeManager(args.path)

    # Check dependencies
    if not manager._check_dependencies():
        sys.exit(1)

    # Handle list action (doesn't need service parameter)
    if args.action == "list":
        manager.list_services()
        return

    # All other actions need a service parameter
    if not args.service:
        Logger.error(f"Service name required for action '{args.action}'")
        parser.print_help()
        sys.exit(1)

    # Handle actions
    success = False

    if args.service == "all":
        success = manager.handle_all_services(args.action)
    else:
        # Check if service exists
        if not manager._get_service_path(args.service):
            Logger.error(f"Service '{args.service}' not found")
            Logger.info("Use 'python manage.py list' to see available services")
            sys.exit(1)

        if args.action == "start":
            success = manager.start_service(args.service)
        elif args.action == "stop":
            success = manager.stop_service(args.service)
        elif args.action == "restart":
            success = manager.restart_service(args.service)
        elif args.action == "update":
            success = manager.update_service(args.service)
        elif args.action == "logs":
            manager.show_logs(args.service, follow=not args.no_follow, tail=args.tail)
            success = True  # Logs don't really "fail"
        elif args.action == "status":
            success = manager.show_status(args.service)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()