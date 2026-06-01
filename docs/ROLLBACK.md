# Rollback Runbook (Phase 2)

This runbook covers **two** rollback paths:

- **Soft rollback** — stop services, keep data on disk. Used when a
  new release is broken but the previous wheel still works.
- **Hard rollback** — uninstall everything and restore data from
  backup. Used when the new release corrupted the SQLite state
  databases or data directory ownership is broken.

> ⚠️ Always snapshot `data/` **before** any rollback, even soft.
> A bad migration or ownership fix can still leave a broken state on
> disk that you want to be able to recover from.

## Pre-flight snapshot (do this first)

```bash
sudo -u cfm tar czf /var/backups/cfm-data-$(date +%Y%m%d-%H%M%S).tgz \
  -C /home/lynskylate/corp-finance-monitor data/
```

If `data/` is large, prefer streaming:

```bash
sudo -u cfm rsync -a --delete \
  /home/lynskylate/corp-finance-monitor/data/ \
  /var/backups/cfm-data-$(date +%Y%m%d-%H%M%S)/
```

Verify the snapshot:

```bash
sudo -u cfm sqlite3 /var/backups/cfm-data-*/.cfm_state/state.db \
  "SELECT COUNT(*) FROM filing_state;"
```

A non-zero count means the snapshot has data.

## Soft rollback (services stopped, data preserved)

### 1. Disable and stop the services

```bash
sudo systemctl disable --now cfm-api.service
sudo systemctl disable --now cfm-sync.timer
sudo systemctl stop cfm-sync.service   # in case a run is in flight
```

Verify:

```bash
systemctl is-active cfm-api cfm-sync.timer
# Both should print "inactive" or "failed".
```

### 2. Downgrade to the previous wheel

The previous wheel is **already on disk** in `dist/`. Re-install the
older one:

```bash
ls -la /home/lynskylate/corp-finance-monitor/dist/
# Pick an older wheel:
sudo /home/lynskylate/corp-finance-monitor/.venv/bin/pip install \
  --force-reinstall \
  /home/lynskylate/corp-finance-monitor/dist/corp_finance_monitor-OLD-VERSION-py3-none-any.whl
```

If using `uv`:

```bash
sudo -u cfm uv pip install --python \
  /home/lynskylate/corp-finance-monitor/.venv/bin/python \
  --force-reinstall \
  /home/lynskylate/corp-finance-monitor/dist/corp_finance_monitor-OLD-VERSION-py3-none-any.whl
```

### 3. Re-enable and start

```bash
sudo systemctl daemon-reload   # only needed if unit file changed
sudo systemctl enable --now cfm-api.service
sudo systemctl enable --now cfm-sync.timer
```

### 4. Verify

```bash
./scripts/verify_deploy.sh
```

If green → soft rollback done. If red → escalate to hard rollback.

## Hard rollback (uninstall + restore from snapshot)

### 1. Stop everything

Same as soft rollback step 1.

### 2. Uninstall the package

```bash
sudo -u cfm /home/lynskylate/corp-finance-monitor/.venv/bin/pip uninstall -y corp-finance-monitor
# or with uv:
sudo -u cfm uv pip uninstall --python \
  /home/lynskylate/corp-finance-monitor/.venv/bin/python corp-finance-monitor
```

### 3. Remove systemd units

```bash
sudo rm -f /etc/systemd/system/cfm-api.service \
          /etc/systemd/system/cfm-sync.service \
          /etc/systemd/system/cfm-sync.timer
sudo systemctl daemon-reload
sudo systemctl reset-failed cfm-api.service cfm-sync.service cfm-sync.timer 2>/dev/null || true
```

### 4. Remove venv (optional, only if you want a clean slate)

```bash
sudo rm -rf /home/lynskylate/corp-finance-monitor/.venv
```

### 5. Restore data from snapshot

```bash
# Move the broken data aside, do NOT delete it
sudo mv /home/lynskylate/corp-finance-monitor/data \
       /home/lynskylate/corp-finance-monitor/data.broken-$(date +%Y%m%d-%H%M%S)

# Restore from the latest snapshot
sudo -u cfm tar xzf /var/backups/cfm-data-LATEST.tgz \
  -C /home/lynskylate/corp-finance-monitor/
sudo chown -R cfm:cfm /home/lynskylate/corp-finance-monitor/data
```

### 6. Reinstall the previous wheel and re-enable

```bash
sudo -u cfm uv pip install --python \
  /home/lynskylate/corp-finance-monitor/.venv/bin/python \
  /home/lynskylate/corp-finance-monitor/dist/corp_finance_monitor-OLD-VERSION-py3-none-any.whl
sudo systemctl daemon-reload
sudo systemctl enable --now cfm-api.service
sudo systemctl enable --now cfm-sync.timer
```

### 7. Verify

```bash
./scripts/verify_deploy.sh
```

### 8. After-action

- Keep the broken `data.broken-*` directory around for 7 days
  before deleting, in case a deeper forensic is needed.
- File a post-mortem if the breakage was due to a migration that
  was not covered by the existing tests (we expect schema migrations
  to be added in `state/sqlite.py` with their own tests).

## When to skip rollback

If the failure is **environmental** (port conflict, missing disk
space, expired cert), do NOT roll back. Fix the environment and
restart the service:

```bash
sudo systemctl restart cfm-api.service
sudo systemctl start cfm-sync.service   # one-shot run
./scripts/verify_deploy.sh
```

## Owner / on-call

- Runbook author: @janny
- Source of truth: this file under `docs/ROLLBACK.md`
- Linked from: `docs/DEPLOY_VERIFICATION.md`
