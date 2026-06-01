# Deployment Verification (Phase 2)

This document is the acceptance checklist for a deployed
`corp-finance-monitor` instance. It assumes Phase 1A (CI) and
Phase 1B (CD) have already produced:

- A built wheel at `dist/corp_finance_monitor-*.whl` (CI artifact, or
  built locally with `uv build`).
- A deployed service: `cfm-api.service` + `cfm-sync.timer` running on
  the host via systemd.
- An installation under `{{ repo_path }}/.venv` (uv-managed) or
  `{{ repo_path }}/.venv` (pip) — see `deploy/VARIABLES.md`.

## Pre-flight (manual, ~2 minutes)

Run these on the target host **before** triggering deploy.sh:

```bash
# 1. Confirm artifacts exist
ls -la dist/corp_finance_monitor-*.whl
test -s dist/corp_finance_monitor-*.whl || { echo "WHEEL MISSING"; exit 1; }

# 2. Confirm target ports are free
ss -ltn '( sport = :8080 )' | grep -q LISTEN && { echo "PORT 8080 BUSY"; exit 1; }

# 3. Confirm uv (or pip) is available
command -v uv || command -v pip3 || { echo "NO INSTALLER"; exit 1; }

# 4. Confirm systemd can accept new units
systemctl show-environment >/dev/null || { echo "SYSTEMD UNAVAILABLE"; exit 1; }
```

## Deploy (idempotent)

```bash
sudo ./deploy/deploy.sh
```

The script is `set -euo pipefail` and will abort on first failure.
On success it prints `Deployment complete.` and the API URL.

## Automated smoke check

Run the bundled script after deploy:

```bash
./scripts/verify_deploy.sh
```

This script MUST exit 0. It checks, in order:

1. `/healthz` returns `{"ok": true}` within 5 s.
2. `/api/filings?source=__nonexistent__` returns `{"items": []}`.
3. `POST /api/subscriptions` returns 201 with a numeric `id`.
4. The cfm-api service is `active (running)`.
5. The cfm-sync timer is `active (waiting)` or `active (running)`.
6. `.venv/bin/cfm --help` lists all 7 subcommands
   (`run sync list runs subscribe serve init`).
7. The data directory is owned by `cfm:cfm` and writable.
8. The `.cfm_state` directory contains `state.db` and `meta.db`
   (created on first use, but should exist after step 1 if config
   loads successfully).

Any failure exits non-zero with a clear `FAIL: <step>` message and the
operator MUST run the manual deep checks below before re-attempting.

## Manual deep checks

Use these when `verify_deploy.sh` fails or you need to debug.

### 1. Service status

```bash
systemctl status cfm-api.service
systemctl status cfm-sync.timer
journalctl -u cfm-api.service -n 100 --no-pager
```

A healthy `cfm-api` should show `Active: active (running)` and
recent log lines from `cfm.api` logger (e.g. `HTTP API listening on
127.0.0.1:8080`).

### 2. Manual sync

```bash
sudo -u cfm /home/lynskylate/corp-finance-monitor/.venv/bin/cfm \
  sync -c /home/lynskylate/corp-finance-monitor/config.yaml \
  --source cninfo
```

Expected: `{"stats": {"discovered": N, "fetched": M, "failed": 0}}` JSON
on stdout, exit code 0. If `failed > 0`, check
`journalctl -u cfm-sync.service -n 200`.

### 3. Trigger the timer immediately

```bash
sudo systemctl start cfm-sync.service
journalctl -u cfm-sync.service -n 100 --no-pager
```

`cfm-sync.service` is `Type=oneshot` — it should run, write
sync.log, and exit. Verify a new row in `data/.cfm_state/state.db`:

```bash
sqlite3 data/.cfm_state/state.db "SELECT id,started_at,fetched,failed FROM run_log ORDER BY id DESC LIMIT 3;"
```

### 4. Subscriptions round-trip

```bash
# Create
curl -sS -X POST http://127.0.0.1:8080/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{"name":"verify-test","source":"cninfo","stock_code":"000725","kind":"annual","target":"https://example.com/wh"}'

# List
curl -sS 'http://127.0.0.1:8080/api/subscriptions?active_only=true'
```

Expected: the new subscription appears with a numeric `id`. Clean up
with:

```bash
sqlite3 data/.cfm_state/state.db "DELETE FROM subscriptions WHERE name='verify-test';"
```

### 5. Run history

```bash
curl -sS 'http://127.0.0.1:8080/api/runs?limit=5' | python3 -m json.tool
```

A healthy service has at least one row (the manual sync from step 2).
The row is most recent first.

## Pass / fail criteria

| Criterion | Source | Threshold |
|---|---|---|
| API `/healthz` returns 200 | `verify_deploy.sh` step 1 | within 5 s |
| All 8 `verify_deploy.sh` steps pass | script | exit 0 |
| `cfm-api.service` is active | `systemctl is-active cfm-api` | `active` |
| `cfm-sync.timer` is active | `systemctl is-active cfm-sync.timer` | `active` |
| Manual sync `fetched > 0` | `journalctl -u cfm-sync` | ≥ 1 |
| `data/` writable by `cfm:cfm` | `stat -c '%U:%G %a' data/` | `cfm:cfm 755` |
| `.venv/bin/cfm --help` works | direct call | lists 7 subcommands |
| 51/51 unit tests pass | `python -m unittest discover -s tests` | all green |

Deployment is **accepted** when every row in the table above is
green. If any row is red, jump to `ROLLBACK.md` or repeat the
failing manual deep check before re-attempting.

## Evidence to attach to the task

After a successful run, capture and post to the task thread:

```bash
{ \
  echo "=== git status ==="; git status --short; \
  echo "=== HEAD ==="; git log --oneline -3; \
  echo "=== systemd status ==="; \
  systemctl is-active cfm-api cfm-sync.timer; \
  echo "=== /healthz ==="; curl -sS http://127.0.0.1:8080/healthz; echo; \
  echo "=== verify_deploy.sh ==="; ./scripts/verify_deploy.sh; \
  echo "=== tests ==="; .venv/bin/python -m unittest discover -s tests -p "test_*.py"; \
} | tee deploy-verification.log
```

## Known follow-ups (not blockers)

- Log rotation: `StandardOutput=append:` grows without bound. Add
  `/etc/logrotate.d/cfm` or `RuntimeMaxAgeSec=` in the unit.
- Cross-process sync lock: `run_lock` in `api.py` is per-process.
  Two API instances on the same host can race. Document single-host
  constraint.
- No remote-write backends yet: subscription delivery is webhook
  only. Email / WeChat notifiers are stubs.
