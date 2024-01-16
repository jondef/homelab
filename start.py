import os
import subprocess
import argparse
import sys

def create_env_file():
    with open('.templates/env.template') as f:
        default_env_content = f.read()

    for service in os.listdir('services'):
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

def get_enabled_services():
    env = load_env()
    enabled_services = []
    for key in env:
        if key.startswith('SVC_ENABLED_') and env[key] == 'true':
            service_name = key[len('SVC_ENABLED_'):]
            enabled_services.append(service_name.lower())
    return enabled_services

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
        enabled_svc = get_enabled_services()
        print("Starting services: " + ", ".join(enabled_svc))

        compose_args = [f"-f ./services/{svc}/docker-compose.yml" for svc in enabled_svc] + ['up', '-d', '--remove-orphans']
        run_docker_compose(compose_args)


    if args.down:
        print("Stopping services")
        run_docker_compose(['down', '--remove-orphans'])

def main():
    env = load_env()

    parser = argparse.ArgumentParser(description="Docker Compose Management Script")
    parser.add_argument('--reload_active', action='store_true', help='Reload active services')
    parser.add_argument('--up', action='store_true', help='Start enabled services')
    parser.add_argument('--down', action='store_true', help='Stop everything services')
    args = parser.parse_args()

    handle_commands(args)


if __name__ == '__main__':
    main()
