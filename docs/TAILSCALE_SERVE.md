# Docker + Tailscale Serve Deployment

This document is the Phase 3D runbook for exposing the Dockerized
`corp-finance-monitor` stack to the tailnet through `tailscale serve`.

Expected topology:

```text
Browser
  -> https://<hostname>.<tailnet>.ts.net
  -> tailscale serve
  -> http://127.0.0.1:8190
  -> nginx (frontend container)
     -> /             -> React SPA
     -> /api/*        -> backend:8190
     -> /healthz      -> backend:8190/healthz
```

The host port is bound to `127.0.0.1:8190`, not `0.0.0.0`, so the
container stack stays local-only and Tailscale becomes the intended
ingress path.

## Prerequisites

1. Docker Engine + `docker compose`
2. Tailscale installed and logged in on the host
3. MagicDNS enabled on the tailnet
4. A valid `config.yaml` at the repo root

On the current host (validated June 1, 2026):

- `tailscale status --json` reported `DNSName = gtr.tail414c32.ts.net`
- `tailscale serve` support is available in CLI `1.98.4`

## 1. Start the Docker stack

From the repo root:

```bash
docker compose up -d --build
```

Verify the local reverse proxy first:

```bash
curl -sS http://127.0.0.1:8190/healthz
curl -sS 'http://127.0.0.1:8190/api/filings?source=__nonexistent__'
curl -I http://127.0.0.1:8190/
```

Expected:

- `/healthz` returns `{"ok": true}`
- `/api/filings?source=__nonexistent__` returns `{"items": []}`
- `/` returns `200 OK` and serves the frontend HTML

## 2. Configure Tailscale Serve

Run the helper script:

```bash
./scripts/setup_tailscale_serve.sh
```

What it does:

1. Reads the current node DNS name from `tailscale status --json`
2. Confirms `http://127.0.0.1:8190/healthz` is reachable
3. Runs `tailscale serve --yes --bg http://127.0.0.1:8190`
4. Prints the tailnet URL and `tailscale serve status`

If you need a non-default local port:

```bash
LOCAL_PORT=8190 ./scripts/setup_tailscale_serve.sh
```

## 3. Verify tailnet access

Run the verification script:

```bash
./scripts/verify_tailscale_serve.sh
```

It checks:

1. Local `http://127.0.0.1:8190/healthz`
2. Local `http://127.0.0.1:8190/api/filings?source=__nonexistent__`
3. `tailscale serve status` points to `127.0.0.1:8190`
4. `https://<hostname>.<tailnet>.ts.net/` serves frontend HTML
5. `https://<hostname>.<tailnet>.ts.net/healthz` proxies correctly
6. `https://<hostname>.<tailnet>.ts.net/api/filings?...` proxies correctly

## 4. Operational commands

Inspect current serve configuration:

```bash
tailscale serve status
```

Reset serve configuration:

```bash
tailscale serve reset
```

Restart only the Docker stack:

```bash
docker compose down
docker compose up -d --build
```

After a stack restart, `tailscale serve` does not need to be recreated
as long as nginx is still reachable at `127.0.0.1:8190`.

## 5. Acceptance criteria

Phase 3D is accepted when all of the following are true:

1. `docker compose up -d --build` succeeds
2. `curl http://127.0.0.1:8190/healthz` returns `{"ok": true}`
3. `tailscale serve status` shows forwarding to `127.0.0.1:8190`
4. `https://<hostname>.<tailnet>.ts.net/` loads the frontend
5. `https://<hostname>.<tailnet>.ts.net/api/filings?...` returns API JSON
6. `./scripts/verify_tailscale_serve.sh` exits `0`

## Handoff to Phase 3E

Once the six checks above are green, hand off to `task #25` for
end-to-end validation of:

- homepage load over tailnet HTTPS
- stock code search
- filing detail page
- `/healthz`
- `/api/filings`
- CORS headers
