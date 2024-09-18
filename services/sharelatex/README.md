


To create the admin user:
https://github.com/overleaf/overleaf/wiki/Creating-and-managing-users

# Overleaf Toolkit users:
$ bin/docker-compose exec sharelatex /bin/bash -ce "cd /overleaf/services/web && node modules/server-ce-scripts/scripts/create-user --admin --email=joe@example.com"

# legacy docker-compose.yml users:
$ docker exec sharelatex /bin/bash -ce "cd /overleaf/services/web && node modules/server-ce-scripts/scripts/create-user --admin --email=joe@example.com"



This image comes with minimal install of packages. To install full installation:
https://github.com/overleaf/toolkit/blob/master/doc/ce-upgrading-texlive.md
In the container: tlmgr install scheme-full

Steps: remove the mount for the latex packages, run the tlmgr install scheme-full
and then once the packages are here, copy them to the host, make the bind mount and 
start the container.

Also see: https://dev.to/corusm/host-sharelatex-in-docker-https-293f
