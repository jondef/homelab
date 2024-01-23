# inspired by
# https://github.com/traefikturkey/onramp/blob/master/Makefile

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
    print("Created .env file. Please edit it to enable services")

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

def run_cmd(cmd: list):
    print(f"Running: {' '.join(cmd)}")
    os.system(' '.join(cmd))

def handle_commands(args):
    enabled_svc = get_enabled_services()

    DOCKER_COMPOSE = [get_docker_compose_command(), "--project-directory", "."]

    DOCKER_COMPOSE_FLAGS = ["-f", "docker-compose.yml"]  # for traefik
    for svc in enabled_svc: DOCKER_COMPOSE_FLAGS += ['-f', f'./services/{svc}/docker-compose.yml']

    SERVICE_PASSED_DNCASED = args.service

    if args.action == 'start':
        run_cmd(DOCKER_COMPOSE + DOCKER_COMPOSE_FLAGS + ['up', '-d', '--build', '--remove-orphans'])

    if args.action == 'up':
        print("Starting services: " + ", ".join(enabled_svc))
        run_cmd(DOCKER_COMPOSE + DOCKER_COMPOSE_FLAGS + ["up", "--force-recreate", '--build', "--remove-orphans", "--abort-on-container-exit"])

    if args.action == 'down':
        print("Stopping all services")
        run_cmd(DOCKER_COMPOSE + DOCKER_COMPOSE_FLAGS + ["down", "--remove-orphans"])
        # rm volume with label remove_volume_on=down
        run_cmd(["docker", "volume", "ls", "--quiet", "--filter", "label=remove_volume_on=down", "|", "xargs", "-r", "docker", "volume", "rm"])

    if args.action == 'pull':
        print("Pulling images")
        run_cmd(DOCKER_COMPOSE + DOCKER_COMPOSE_FLAGS + ["pull"])

    if args.action == 'logs':
        if SERVICE_PASSED_DNCASED == "":
            print("Please specify a service to show logs for")
            sys.exit(1)
        print("Showing logs")
        run_cmd(DOCKER_COMPOSE + DOCKER_COMPOSE_FLAGS + ["logs", "-f", SERVICE_PASSED_DNCASED])

    if args.action == 'restart':
        print("Restarting services")
        run_cmd([sys.executable, sys.argv[0], "down"])
        run_cmd([sys.executable, sys.argv[0], "start"])

    if args.action == 'update':
        print("Updating services")
        run_cmd([sys.executable, sys.argv[0], "down"])
        run_cmd([sys.executable, sys.argv[0], "pull"])
        run_cmd([sys.executable, sys.argv[0], "start"])

    if args.action == 'run':
        if SERVICE_PASSED_DNCASED == "":
            print("Please specify a service to run")
            sys.exit(1)
        run_cmd(DOCKER_COMPOSE + DOCKER_COMPOSE_FLAGS + ["run", "-it", "--rm", SERVICE_PASSED_DNCASED, "sh"])

    if args.action == 'exec':
        if SERVICE_PASSED_DNCASED == "":
            print("Please specify a service to exec into")
            sys.exit(1)
        run_cmd(DOCKER_COMPOSE + DOCKER_COMPOSE_FLAGS + ["exec", SERVICE_PASSED_DNCASED, "sh"])

    #########################################################
    #
    # service commands
    #
    #########################################################
    if args.action == 'enable':
        with open('.env', 'r') as f:
            env_content = f.read()
        env_content = env_content.replace(f"SVC_ENABLED_{SERVICE_PASSED_DNCASED.upper()}=false", f"SVC_ENABLED_{SERVICE_PASSED_DNCASED.upper()}=true")
        with open('.env', 'w') as f:
            f.write(env_content)
        # start the service
        run_cmd([sys.executable, sys.argv[0], "start"])

    if args.action == 'disable':
        # stop the service
        # Here we run docker compose stop with context of the service only
        run_cmd(DOCKER_COMPOSE + ['-f', f'services/{SERVICE_PASSED_DNCASED}/docker-compose.yml', 'stop'])

        with open('.env', 'r') as f:
            env_content = f.read()
        env_content = env_content.replace(f"SVC_ENABLED_{SERVICE_PASSED_DNCASED.upper()}=true", f"SVC_ENABLED_{SERVICE_PASSED_DNCASED.upper()}=false")
        with open('.env', 'w') as f:
            f.write(env_content)


def setup_env():
    try:
        host_ip = subprocess.check_output("ip route get 1.1.1.1 | grep -oP 'src \\K\\S+'", shell=True).decode().strip()
        os.environ['HOSTIP'] = host_ip
        os.environ['PUID'] = str(os.getuid())
        os.environ['PGID'] = str(os.getgid())
        os.environ['HOST_NAME'] = os.environ.get('HOST_NAME', subprocess.check_output("hostname", shell=True).decode().strip())
        os.environ['CF_RESOLVER_WAITTIME'] = os.environ.get('CF_RESOLVER_WAITTIME', '60')
    except subprocess.CalledProcessError as e:
        print(f"Error setting up environment variables: {e}")
        sys.exit(1)

def main():

    parser = argparse.ArgumentParser(description="Docker Compose Management Script")

    # Add a positional argument for the action to be taken
    parser.add_argument('action',
                        nargs='?',
                        default='start',
                        choices=['start', 'up', 'down', 'pull', 'logs', 'restart', 'update', 'run', 'exec', 'enable', 'disable'],
                        help='Action to perform')
    # Add an optional argument for the service name
    parser.add_argument('service', nargs='?', default=None, help='Name of the service to act upon (optional for some actions)')
    args = parser.parse_args()

    handle_commands(args)


if __name__ == '__main__':
    main()
