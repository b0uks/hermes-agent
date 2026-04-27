# Docker Deployment

Run Hermes in a container for portability — the same image works on a laptop, a $5 VPS, or a Mac mini. All persistent state lives in a single host directory (`~/hermes-data` by default) bind-mounted to `/opt/data` inside the container, so migrating to a new host is `rsync ~/hermes-data/` plus re-running the gateway command.

This is an outline of the moving parts. For broader configuration details (providers, models, memory, skills) see the [hosted docs](https://hermes-agent.nousresearch.com/docs/).

---

## Build

```bash
docker build -t hermes-agent:dev .
```

First build is ~60 minutes (Python + npm + Playwright + Chromium). Subsequent builds reuse cache.

---

## Bind-mount layout

| Host path | Container path | Mode | Purpose |
|---|---|---|---|
| `~/hermes-data` | `/opt/data` | rw | All Hermes state — config, memory, sessions, skills, platform auth |
| `~/Documents/Projects` | `/opt/data/workspace/projects` | rw | Project code, visible to the agent |
| `~/repos` | `/opt/data/workspace/repos` | rw | Repos kept outside `Projects/` |
| `$HOME` | `/opt/host-home` | ro | Host configs (`.gitconfig`, `.aws/`, etc.). Mount per-path instead if you'd rather not expose `~/.ssh` |

`~/hermes-data` is created on first run if missing. Drop `config.yaml`, `.env`, and `SOUL.md` (persona) there before starting the gateway.

---

## First-time messaging-platform pairing

Some platforms (notably WhatsApp) require an interactive QR scan once per host. Run a one-shot container in pairing mode:

```bash
docker run -it --rm \
  -e HERMES_UID=$(id -u) -e HERMES_GID=$(id -g) \
  -v ~/hermes-data:/opt/data \
  --name hermes-pair hermes-agent:dev whatsapp
```

Session keys persist under `~/hermes-data/platforms/`, so subsequent runs don't need a re-scan.

---

## Gateway daemon

Keeps messaging platforms online. Run detached:

```bash
docker run -d --restart unless-stopped \
  -e HERMES_UID=$(id -u) -e HERMES_GID=$(id -g) \
  -v ~/hermes-data:/opt/data \
  -v ~/Documents/Projects:/opt/data/workspace/projects \
  -v ~/repos:/opt/data/workspace/repos \
  -v $HOME:/opt/host-home:ro \
  -p 8765:8765 \
  --add-host=host.docker.internal:host-gateway \
  --name hermes-gateway hermes-agent:dev gateway
```

- `-p 8765:8765` exposes the inbound webhook port (e.g. for BlueBubbles).
- `--add-host=host.docker.internal:host-gateway` lets the container reach services running on the host. Required on Linux; harmless on Docker Desktop.

Logs: `docker logs -f hermes-gateway`. Stop: `docker stop hermes-gateway`.

---

## Interactive TUI

Talk to the agent directly. Runs alongside the gateway — both share `~/hermes-data`, so memory, skills, and sessions stay consistent.

```bash
docker run -it --rm \
  -e HERMES_UID=$(id -u) -e HERMES_GID=$(id -g) \
  -v ~/hermes-data:/opt/data \
  -v ~/Documents/Projects:/opt/data/workspace/projects \
  -v ~/repos:/opt/data/workspace/repos \
  -v $HOME:/opt/host-home:ro \
  --name hermes-tui hermes-agent:dev
```

---

## MCP servers

The `mcp_servers:` block in `~/hermes-data/config.yaml` works the same as in a local install, with two container-specific notes:

- **Local stdio MCPs run inside the container.** Use container paths (e.g. `/opt/data/workspace/repos/...`), and rely on tools present in the image (`npx`, `uv`, `python3`). Project credentials go in the server's `env:` block or in `~/hermes-data/.env`.
- **Servers that need host CLIs** (gcloud, firebase) need either the CLI added to the Dockerfile, or docker-in-docker (mount `/var/run/docker.sock` and install `docker-cli`).
- **Remote `url:` servers** (HTTP/SSE) work without modification.

See the [MCP integration guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) for full configuration reference.

---

## Migration

```bash
rsync -a ~/hermes-data/ user@new-host:~/hermes-data/
```

Re-run the same `docker run -d ... gateway` command on the new host. Paired messaging-platform sessions travel with the volume (re-pair only if more than ~14 days have passed).

---

## See also

- [Configuration reference](https://hermes-agent.nousresearch.com/docs/user-guide/configuration)
- [Messaging gateway guide](https://hermes-agent.nousresearch.com/docs/user-guide/messaging)
- [Security model](https://hermes-agent.nousresearch.com/docs/user-guide/security)
