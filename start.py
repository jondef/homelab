import os
import subprocess
import argparse
import sys

def create_env_file():
    with open('.templates/env.template') as f:
        default_env_content = f.read()

    for service in os.listdir('services'):
        if service == 'traefik':
            continue
        default_env_content += f"SVC_ENABLED_{service.upper()}=false\n"

    with open('.env', 'w') as f:
        f.write(default_env_content)

def load_env():
    hashmap = {}
    if not os.path.isfile('.env'):
        create_env_file()

    with open('.env') as f:
        for line in f:
            if line.startswith('#') or '=' not in line:
                continue

            key, value = line.strip().split('=', 1)
            hashmap[key] = value
    return hashmap

def get_docker_compose_command():
    """Determine the Docker Compose command to use"""
    if subprocess.run(['which', 'docker-compose'], stdout=subprocess.DEVNULL).returncode == 0:
        return 'docker-compose'
    else:
        return 'docker compose'

def run_docker_compose(args):
    """Run a Docker Compose command with additional arguments"""
    cmd = [get_docker_compose_command()] + args
    subprocess.run(cmd)

def handle_commands(args):
    """Handle command line arguments"""
    if args.reload_active:
        print("Reload active services")
        # Add the logic for reloading active services here

    if args.up:
        print("Starting services")
        run_docker_compose(['up', '-d', '--remove-orphans'])

    if args.down:
        print("Stopping services")
        run_docker_compose(['down', '--remove-orphans'])

def main():
    env = load_env()

    parser = argparse.ArgumentParser(description="Docker Compose Management Script")
    parser.add_argument('--reload_active', action='store_true', help='Reload active services')
    parser.add_argument('--up', action='store_true', help='Start services')
    parser.add_argument('--down', action='store_true', help='Stop services')
    args = parser.parse_args()

    handle_commands(args)


if __name__ == '__main__':
    main()
