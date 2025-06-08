#!/usr/bin/env python3
"""
Homeserver Stack Manager with Config Sync
Usage: python manage.py <action> <service>
Actions: start, stop, restart, update, logs, status, list, sync-config
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


class ConfigSyncManager:
    """Manages syncing configuration files to remote Docker context"""

    def __init__(self, docker_context: str = "homelab"):
        self.docker_context = docker_context
        self.remote_temp_base = "/tmp/homeserver-configs"

    def _get_docker_host_info(self) -> Optional[Dict[str, str]]:
        """Extract SSH connection info from Docker context"""
        try:
            result = subprocess.run(
                ["docker", "context", "inspect", self.docker_context],
                capture_output=True, text=True, check=True
            )
            context_data = json.loads(result.stdout)[0]

            # Extract host info from Docker endpoint
            endpoint = context_data.get("Endpoints", {}).get("docker", {}).get("Host", "")
            if endpoint.startswith("ssh://"):
                # Parse ssh://user@host or ssh://host
                ssh_part = endpoint[6:]  # Remove 'ssh://'
                if "@" in ssh_part:
                    user, host = ssh_part.split("@", 1)
                else:
                    user = None
                    host = ssh_part

                return {"host": host, "user": user}

            return None
        except Exception as e:
            Logger.error(f"Failed to get Docker context info: {e}")
            return None

    def _run_ssh_command(self, command: str, host_info: Dict[str, str]) -> subprocess.CompletedProcess:
        """Run a command on the remote server via SSH"""
        ssh_cmd = ["ssh"]
        if host_info["user"]:
            ssh_cmd.append(f"{host_info['user']}@{host_info['host']}")
        else:
            ssh_cmd.append(host_info["host"])
        ssh_cmd.append(command)

        return subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)

    def sync_service_configs(self, service_path: Path, service_name: str) -> Optional[str]:
        """Sync service configuration files to remote server using rsync"""
        host_info = self._get_docker_host_info()
        if not host_info:
            Logger.warning("Could not determine remote host info - skipping config sync")
            return None

        # Look for config directories and files (excluding docker-compose.yml)
        config_items = []

        for item in service_path.iterdir():
            if item.name == "docker-compose.yml":
                continue
            if item.name.startswith('.'):
                continue
            if item.is_dir() or item.is_file():
                config_items.append(item)

        if not config_items:
            Logger.info(f"No config files found for {service_name}")
            return None

        # Create remote directory path
        remote_service_path = f"{self.remote_temp_base}/{service_name}"

        try:
            # Ensure remote directory exists
            self._run_ssh_command(f"mkdir -p {remote_service_path}", host_info)

            # Build remote destination
            if host_info["user"]:
                remote_dest = f"{host_info['user']}@{host_info['host']}:{remote_service_path}/"
            else:
                remote_dest = f"{host_info['host']}:{remote_service_path}/"

            # Use rsync to sync all config items at once
            rsync_cmd = ["rsync", "-avz", "--delete"]

            # Add all config items to the command
            for item in config_items:
                rsync_cmd.append(str(item))

            # Add destination
            rsync_cmd.append(remote_dest)

            Logger.info(f"Syncing configs for {service_name} to {remote_dest}")
            subprocess.run(rsync_cmd, check=True)

            Logger.success(f"Config sync completed for {service_name}")
            return remote_service_path

        except subprocess.CalledProcessError as e:
            Logger.error(f"Failed to sync configs for {service_name}: {e}")
            return None

    def update_compose_env_vars(self, service_name: str, remote_config_path: str) -> Dict[str, str]:
        """Generate environment variables for docker-compose to use remote config paths"""
        return {
            f"CONFIG_PATH_{service_name.upper()}": remote_config_path,
            f"REMOTE_CONFIG_BASE": self.remote_temp_base
        }


class DockerComposeManager:
    """Manages Docker Compose stacks for homeserver services"""

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.docker_dir = self.base_path / "docker"
        self.services_dir = self.docker_dir / "services"
        self.infrastructure_dir = self.docker_dir / "infrastructure"
        self.config_sync = ConfigSyncManager()

        # Create directories if they don't exist
        self.docker_dir.mkdir(exist_ok=True)
        self.services_dir.mkdir(exist_ok=True)
        self.infrastructure_dir.mkdir(exist_ok=True)

    def check_dependencies(self) -> bool:
        """Check if required tools are available"""
        try:
            subprocess.run(["docker", "--version"],
                           capture_output=True, check=True)
            subprocess.run(["docker-compose", "--version"],
                           capture_output=True, check=True)

            # Check for ssh and rsync
            subprocess.run(["ssh", "-V"], capture_output=True, check=True)
            subprocess.run(["rsync", "--version"], capture_output=True, check=True)

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
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            if "ssh" in str(e) or "rsync" in str(e):
                Logger.error("SSH or rsync not found. Please install them for config sync functionality.")
            else:
                Logger.error("Docker or docker-compose not found. Please install them.")
            return False

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
                             capture_output: bool = False, extra_env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        """Run a docker-compose command for a specific service"""
        service_path = self.get_service_path(service)
        if not service_path:
            raise ValueError(f"Service '{service}' not found")

        env_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        full_command = ["docker-compose", "--env-file", env_file_path] + command

        # Prepare environment
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)

        Logger.info(f"Running: {' '.join(full_command)} in {service_path}")

        try:
            result = subprocess.run(
                full_command,
                cwd=service_path,
                capture_output=capture_output,
                text=True,
                check=True,
                env=env
            )
            return result
        except subprocess.CalledProcessError as e:
            Logger.error(f"Command failed for {service}: {e}")
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr)
            raise

    def sync_service_config(self, service: str) -> Optional[Dict[str, str]]:
        """Sync configuration files for a service and return environment variables"""
        service_path = self.get_service_path(service)
        if not service_path:
            raise FileNotFoundError(f"Path for Service '{service}' not found")

        Logger.info(f"Syncing configuration files for {service}...")
        remote_config_path = self.config_sync.sync_service_configs(service_path, service)

        if remote_config_path:
            return self.config_sync.update_compose_env_vars(service, remote_config_path)

        return None

    def start_service(self, service: str, sync_config: bool = True) -> bool:
        """Start a service with optional config sync"""
        try:
            extra_env = None
            if sync_config:
                extra_env = self.sync_service_config(service)

            Logger.info(f"Starting {service}...")
            self._run_compose_command(service, ["up", "-d"], extra_env=extra_env)
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

    def restart_service(self, service: str, sync_config: bool = True) -> bool:
        """Restart a service with optional config sync"""
        Logger.info(f"Restarting {service}...")
        if self.stop_service(service):
            time.sleep(2)  # Brief pause between stop and start
            return self.start_service(service, sync_config=sync_config)
        return False

    def update_service(self, service: str, sync_config: bool = True) -> bool:
        """Update a service (pull latest images and restart) with optional config sync"""
        try:
            Logger.info(f"Updating {service}...")

            # Sync config first if requested
            extra_env = None
            if sync_config:
                extra_env = self.sync_service_config(service)

            # Pull latest images
            Logger.info(f"Pulling latest images for {service}...")
            self._run_compose_command(service, ["pull"], extra_env=extra_env)

            # Stop and start with new images
            Logger.info(f"Restarting {service} with updated images...")
            self._run_compose_command(service, ["down"])
            self._run_compose_command(service, ["up", "-d"], extra_env=extra_env)

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

    def is_service_running(self, service: str) -> bool:
        """Check if a service is currently running"""
        try:
            result = self._run_compose_command(service, ["ps", "-q"], capture_output=True)
            return bool(result.stdout.strip())
        except:
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Homeserver Docker Compose Stack Manager with Config Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage.py start traefik --sync
  python manage.py start traefik nextcloud owncloud --sync
  python manage.py start --all --sync
  python manage.py update immich
  python manage.py logs nextcloud
  python manage.py restart --all
  python manage.py list

Config Sync:
  Configuration files can be synced when starting/restarting services.
  Use --sync to sync config for start/restart/update actions.
  Files and directories (except docker-compose.yml) are copied to /tmp/homeserver-configs/ on the remote server.
        """
    )

    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "update", "logs", "status", "list"],
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

    parser.add_argument(
        "--sync",
        action="store_true",
        help="Config sync for start/restart/update actions"
    )

    args = parser.parse_args()

    # Create manager
    manager = DockerComposeManager(args.path)

    # Check dependencies
    if not manager.check_dependencies():
        sys.exit(1)

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

    # Determine if we should sync configs
    sync_config = args.sync and args.action in ["start", "restart", "update"]

    # Handle actions
    success = False

    for service in args.services:
        # Check if service exists
        if not manager.get_service_path(service):
            Logger.error(f"Service '{service}' not found")
            Logger.info("Use 'python manage.py list' to see available services")
            sys.exit(1)

        if args.action == "start":
            success = manager.start_service(service, sync_config=sync_config)
        elif args.action == "stop":
            success = manager.stop_service(service)
        elif args.action == "restart":
            success = manager.restart_service(service, sync_config=sync_config)
        elif args.action == "update":
            success = manager.update_service(service, sync_config=sync_config)
        elif args.action == "list":
            status_indicator = "🟢" if manager.is_service_running(service) else "🔴"
            print(f"  {status_indicator} {service}")
            success = True
        elif args.action == "logs":
            manager.show_logs(service, follow=not args.no_follow, tail=args.tail)
            success = True  # Logs don't really "fail"
        elif args.action == "status":
            success = manager.show_status(service)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()