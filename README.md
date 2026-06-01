# corp-finance-monitor

Multi-source corporate filing monitor with:

- source adapters for CNInfo, SSE, and HKEX
- local disk storage for downloaded documents
- SQLite state store for dedup, run history, and subscriptions
- CLI for sync/query/subscription management
- HTTP API for frontend query and subscription workflows

## Why this repo

The earlier plan was directionally right on source/storage/engine abstraction, but insufficient for product use:

- it treated background sync as the whole system
- it did not include a frontend-facing query API
- it did not include a subscription API
- it coupled state/dedup logic too tightly to the engine

This repo keeps the Python implementation for now because the current machine does not have `go`, `rustc`, or `cargo` available in `PATH`. The service boundaries were shaped so a later Go/Rust migration can preserve the same storage/state/source responsibilities and HTTP API surface.

## Architecture

```text
sources -> engine -> storage
                 -> state_store
                 -> http api / cli
```

Core modules:

- `src/corp_finance_monitor/core`
  - `config.py`
  - `model.py`
  - `source.py`
  - `storage.py`
  - `state.py`
  - `engine.py`
- `src/corp_finance_monitor/sources`
  - `cninfo.py`
  - `sse.py`
  - `hkex.py`
- `src/corp_finance_monitor/storage`
  - `disk.py`
- `src/corp_finance_monitor/state`
  - `sqlite.py`
- `src/corp_finance_monitor/api.py`

## Config

Generate a starter config:

```bash
python3 main.py init config.yaml
```

Important sections:

- `engine`
- `storage`
- `state_store`
- `api`
- `sources`

`storage.base_dir` and `state_store.path` are resolved relative to the config file location.

## CLI

Run one sync round:

```bash
python3 main.py sync -c config.yaml --source cninfo
```

List stored filings:

```bash
python3 main.py list -c config.yaml --source cninfo --stock 000725
```

Show run history:

```bash
python3 main.py runs -c config.yaml
```

Add a subscription:

```bash
python3 main.py subscribe add -c config.yaml \
  --name boe-annual \
  --source cninfo \
  --stock 000725 \
  --kind annual \
  --target local:test
```

Start the HTTP API:

```bash
python3 main.py serve -c config.yaml --host 127.0.0.1 --port 8080
```

## HTTP API

Health:

```bash
curl http://127.0.0.1:8080/healthz
```

List filings:

```bash
curl 'http://127.0.0.1:8080/api/filings?source=cninfo&stock_code=000725'
```

List runs:

```bash
curl 'http://127.0.0.1:8080/api/runs?limit=20'
```

Create subscription:

```bash
curl -X POST http://127.0.0.1:8080/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{"name":"boe-annual","source":"cninfo","stock_code":"000725","kind":"annual","target":"local:test"}'
```

Trigger sync:

```bash
curl -X POST http://127.0.0.1:8080/api/sync \
  -H 'Content-Type: application/json' \
  -d '{"sources":["cninfo"]}'
```

## Verified

Validated on June 1, 2026:

- config parsing with relative path resolution
- controlled CNInfo sync using a limited watchlist
- local storage writes under `filings/<source>/<stock>/<kind>/`
- run history persistence in SQLite
- HTTP API:
  - `/healthz`
  - `/api/filings`
  - `/api/runs`
  - `POST /api/subscriptions`

Example verified CNInfo classifications:

- `2025年年度报告` -> `annual`
- `2025年年度报告摘要` -> `other`
- `2025年半年度报告` -> `semi`
- `2025年半年度报告摘要` -> `semi`

## CI (GitHub Actions)

Automated on every push and pull request to `main`/`master`:

**File:** `.github/workflows/ci.yml`

**Test job** — runs on Python 3.10, 3.11, 3.12:
```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

**Build job** — runs after tests pass:
- Builds `wheel` and `sdist` via `python -m build`
- Uploads `dist/` as workflow artifact named `dist` (30-day retention)

**No repo secrets required** — the workflow uses only public actions (`actions/checkout`, `actions/setup-python`, `actions/upload-artifact`) and no external credentials.

## Next steps

- add pagination/filter extensions to the HTTP API
- add subscription delivery backends instead of only storing subscription intent
- add tests under `tests/`
- optionally migrate runtime to Go or Rust when toolchain is available
