# Docker Setup — Local Notes

Personal runbook for the Docker-based Hermes deployment on this machine.
All host state lives in `~/hermes-data/` (bind-mounted as `/opt/data`).

## Build

```bash
docker build -t hermes-agent:dev /Users/adamb/Documents/Projects/hermes-agent
```

First build ~60 min (compiles npm + Playwright + Python deps). Subsequent
builds are cached — seconds.

## Config

- `~/hermes-data/.env` — `CUSTOM_API_KEY`, `WHATSAPP_*`, `BLUEBUBBLES_*`
- `~/hermes-data/config.yaml` — `model.provider: custom`, `model.api_key`,
  `model.base_url`, named `providers.trendai`, `model_aliases.{codex,gemini}`
- `~/hermes-data/SOUL.md` — agent persona

## First-time WhatsApp pairing

Scan the QR with phone → WhatsApp → Linked Devices → Link a Device.

```bash
docker run -it --rm \
  -e HERMES_UID=$(id -u) -e HERMES_GID=$(id -g) \
  -v ~/hermes-data:/opt/data \
  --name hermes-pair hermes-agent:dev whatsapp
```

Ctrl+C after it says "Linked". Session keys persist under
`~/hermes-data/platforms/whatsapp/`.

## Gateway daemon (keeps messaging platforms online)

Runs WhatsApp + (if configured) BlueBubbles/iMessage. Mounts project dirs so
the agent can work on real code via messages.

```bash
docker run -d --restart unless-stopped \
  -e HERMES_UID=$(id -u) -e HERMES_GID=$(id -g) \
  -v ~/hermes-data:/opt/data \
  -v ~/Documents/Projects:/opt/data/workspace/projects \
  -v ~/repos:/opt/data/workspace/repos \
  -p 8765:8765 \
  --add-host=host.docker.internal:host-gateway \
  --name hermes-gateway hermes-agent:dev gateway
```

- `-v ~/Documents/Projects:/opt/data/workspace/projects` — host code visible inside container
- `-v ~/repos:/opt/data/workspace/repos` — same
- `-p 8765:8765` — exposes the BlueBubbles webhook port on the host so BlueBubbles can POST into the container
- `--add-host=host.docker.internal:host-gateway` — harmless on Docker Desktop (auto-resolves), required on Linux so the container can reach BlueBubbles running on the host

Logs: `docker logs -f hermes-gateway`
Stop: `docker stop hermes-gateway`
Remove: `docker rm -f hermes-gateway`

## TUI (interactive chat)

```bash
docker run -it --rm \
  -e HERMES_UID=$(id -u) -e HERMES_GID=$(id -g) \
  -v ~/hermes-data:/opt/data \
  -v ~/Documents/Projects:/opt/data/workspace/projects \
  -v ~/repos:/opt/data/workspace/repos \
  -v $HOME:/opt/host-home:ro \
  --name hermes-tui hermes-agent:dev
```

- `~/Documents/Projects` + `~/repos` mounted rw at `/opt/data/workspace/{projects,repos}` — same as the gateway, so Hermes can edit real code from the TUI.
- `~/` mounted **read-only** at `/opt/host-home` — lets Hermes read host configs like `~/.gitconfig`, `~/.aws/credentials`, `~/.config/gh/hosts.yml`, `~/.claude/`, etc. without being able to modify them.
- Security note: the ro home mount includes `~/.ssh`. Anything running in the container (including any MCP server you wire up) can read your SSH private keys. Fine on a trusted personal machine; don't do this on shared infra. If that's a concern, swap the blanket `-v ~:/opt/host-home:ro` for per-path mounts (e.g. `-v ~/.gitconfig:/opt/host-home/.gitconfig:ro`).

Runs alongside the gateway — both share `~/hermes-data`, so memory, skills,
and sessions stay consistent.

## Switching models in the TUI

```
/model gemini                                    # alias → gemini-3.1-pro
/model codex                                     # alias → gpt-5.3-codex
/model gpt-5.3-codex --provider trendai          # explicit form
/model <name> --global                           # persist to config.yaml
```

## iMessage via BlueBubbles (per-Mac, one-time)

On each Mac you want to run this stack on:

1. Install **BlueBubbles Server** from https://bluebubbles.app (the `.dmg` Mac app, not the iPhone one).
2. Launch it. macOS will prompt for Full Disk Access (needed to read `chat.db`) and Automation → Messages (needed to send). Grant both.
3. In the BlueBubbles app → Settings → set a password. Use the **same string** as `BLUEBUBBLES_PASSWORD` in `~/hermes-data/.env`.
4. Confirm it's listening on port `1234` (default) — there's a "Server running" indicator in the app.
5. Start / restart the gateway (command above). The gateway will connect to `http://host.docker.internal:1234`, authenticate, and begin relaying iMessages.
6. Edit `BLUEBUBBLES_ALLOWED_USERS` in `.env` to your own Apple ID phone number / email so only you can talk to it.

Leave the BlueBubbles app running; it must stay open + the Mac must stay awake for iMessages to flow. A dedicated old Mac Mini is ideal; for a laptop use `caffeinate -dims &` or System Settings → "Prevent automatic sleeping when the display is off".

## Migration / portability

To move to a VPS or mini-server, `rsync ~/hermes-data/` to the new host and
re-run the same `docker run -d … gateway` command. The paired WhatsApp
session travels with the volume — no re-scan needed unless ~14 days have
passed.
