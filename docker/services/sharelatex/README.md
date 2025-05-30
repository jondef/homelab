


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


What worked:https://www.reddit.com/r/LaTeX/comments/1bzlp8j/local_overleaf_installation_uses_wrong_texlive/
Just ran into this as well - you can either do what you did, or I opted for the "oh well, I want 2024 anyways for our users" approach:

bin/shell inside your toolkit dir to connect in (or manual docker exec -it sharelatex /bin/bash)

wget http://mirror.ctan.org/systems/texlive/tlnet/update-tlmgr-latest.sh && chmod +x update-tlmgr-latest.sh && ./update-tlmgr-latest.sh

tlmgr update (not sure if this is needed)

tlmgr install scheme-full

just worked for mine!

tlmgr revision 70671 (2024-03-17 02:10:09 +0100)
tlmgr using installation: /usr/local/texlive/2023
TeX Live (https://tug.org/texlive) version 2024

I'm just ignoring the fact it used the (hardcoded) path to /usr/local/texlive/2023 and enjoying the fact 2024 works and my compiles work haha