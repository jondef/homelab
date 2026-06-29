# Arr Stack Design

**Date:** 2026-06-28
**Status:** Approved

## Goal

Add automated media downloading (torrents) for Jellyfin using the *arr stack, reviving and fixing the archived setup in `docker/_archive/qbittorrent/`.

## Architecture

### Containers (single compose, shared internal network)

| Container | Purpose | Web UI | Bound to |
|---|---|---|---|
| **qBittorrent** | Torrent client — actually downloads files | 8081 | 127.0.0.1 |
| **Prowlarr** | Indexer hub — add trackers here once, pushes to all *arrs | 9696 | 127.0.0.1 |
| **Sonarr** | TV shows — finds episodes, sends to qBittorrent, organizes | 8989 | 127.0.0.1 |
| **Radarr** | Movies — same for movies | 7878 | 127.0.0.1 |
| **Lidarr** | Music — same for music | 8686 | 127.0.0.1 |

Jellyfin stays in `docker/services/jellyfin/` — untouched.

### Network

- Internal bridge network (`arr-network`) — containers talk to each other by name
- No Traefik labels, no `traefik-public` network, no public exposure
- All web UIs bound to `127.0.0.1:<port>` — accessible via SSH tunnel or local VPN only
- qBittorrent torrent traffic routed through existing host VPN (user-managed)

### Volume layout

All under `/mnt/main/data/` so hardlinks work (instant moves, zero extra space):

```
qBittorrent:  /mnt/main/data/downloads  ->  /data/downloads
Sonarr:       /mnt/main/data/downloads  ->  /data/downloads
              /mnt/main/data/nextcloud/__groupfolders/1/Shows  ->  /data/tvshows
Radarr:       /mnt/main/data/downloads  ->  /data/downloads
              /mnt/main/data/nextcloud/__groupfolders/1/Movies  ->  /data/movies
Lidarr:       /mnt/main/data/downloads  ->  /data/downloads
              /mnt/main/data/nextcloud/__groupfolders/1/Music  ->  /data/music
```

Jellyfin reads from the same Shows/Movies/Music directories — read-only, already configured.

### Permissions

PUID/PGID: `33:33` (www-data) — matches existing Jellyfin container for consistent file ownership.

### New env var

```
QBITTORRENT_DOWNLOAD_DIR=/mnt/main/data/downloads
```

Reusing existing: `SHOWS_DIR`, `MOVIES_DIR`, `MUSIC_DIR`.

### Location

`docker/services/arr-stack/docker-compose.yml`

### What's removed vs. archived version

- Readarr (books) — buggy in early dev, user downloads books manually, Kavita handles reading
- Jellyfin — already exists in `docker/services/jellyfin/`
- Traefik labels — local-only access, no public exposure
- `QBITTORRENT_DOWNLOAD_LOCATION`, `TVSHOWS_LOCATION`, `MOVIES_LOCATION`, etc. — replaced with env vars matching existing patterns

## Setup flow

After `docker compose up -d`, configure in this order:

1. **qBittorrent** (`127.0.0.1:8081`) — set download path to `/data/downloads`, set categories for sonarr/radarr/lidarr
2. **Prowlarr** (`127.0.0.1:9696`) — add torrent trackers, then add Sonarr/Radarr/Lidarr as apps (connects them automatically)
3. **Sonarr** (`127.0.0.1:8989`) — add download client (qBittorrent), configure quality profiles, start adding shows
4. **Radarr** (`127.0.0.1:7878`) — same as Sonarr but for movies
5. **Lidarr** (`127.0.0.1:8686`) — same but for music
