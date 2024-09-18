# Homelab

1. Clone repo including submodules with:
```sh
git clone --recurse-submodules git@github.com:jondef/homelab.git
```
or get submodules after cloning:
```sh
git submodule update --init --recursive
```

2. Configure zpool and zfs
3. Setup start containers on reboot
```sh
sudo vim /etc/systemd/system/start_containers.service
```
```sh
[Unit]
Description=Start Docker Containers
After=network.target

[Service]
WorkingDirectory=/home/user/homelab
ExecStart=python3 manage.py

[Install]
WantedBy=multi-user.target
```

## Useful commands
If you're importing into Nextcloud from outside Nextcloud, run:
```sh
docker exec --user www-data nextcloud php occ files:scan --all
```

## Todos

1. add flame dashbard
2. https://github.com/gethomepage/homepage
2. Increase security: https://www.reddit.com/r/selfhosted/comments/t6ap67/need_some_advice_to_tighten_up_security_for/
3. use docker mounts instead of file mounts: https://www.guguweb.com/2019/02/07/how-to-move-docker-data-directory-to-another-location-on-ubuntu/
4. configure traefik using middlewares https://community.traefik.io/t/all-middlewares-produce-middleware-not-found-error/18131
5. https://www.reddit.com/r/kubernetes/comments/15mq55d/want_to_setup_a_k8s_homelab_what_are_some/
6. https://www.windmill.dev/scripts

