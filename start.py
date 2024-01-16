


import os
import subprocess
import sys

def load_env():
    """Load environment variables from a .env file"""
    if os.path.isfile('.env'):
        with open('.env') as f:
            for line in f:
                if line.startswith('#') or '=' not in line:
                    continue
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

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

def get_service_files(service_name):
    """Get a list of service files for a given service"""
    service_files = []
    paths = ['services-enabled', 'overrides-enabled']
    for path in paths:
        service_files.extend(glob.glob(f'{path}/{service_name}*.yml'))
    return service_files

def main():
    load_env()

    service_passed_dncased = sys.argv[2] if len(sys.argv) > 2 else ''
    service_passed_upcased = service_passed_dncased.replace('-', '_').upper()

    os.environ.update({
        'SERVICE_PASSED_DNCASED': service_passed_dncased,
        'SERVICE_PASSED_UPCASED': service_passed_upcased
    })

    if sys.argv[1] == 'start':
        run_docker_compose(['up', '-d', '--remove-orphans'])

    # Add other command implementations (e.g., 'stop', 'restart') here

if __name__ == '__main__':
    main()
