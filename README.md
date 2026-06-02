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

Phase 2 engine knobs:

- `engine.concurrency`
  - `1` keeps the historical serial behavior
  - `>1` enables concurrent fetch workers
- `engine.fetch_delay_seconds`
  - still defines the minimum gap between outbound fetch requests
  - in concurrent mode this is enforced by a shared global rate limiter
- `sources.cninfo.options.full_market_batch_size`
  - only used when `full_market: true`
  - controls how many stock codes are grouped into each discover batch

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
python3 main.py serve -c config.yaml --host 127.0.0.1 --port 8190
```

## HTTP API

Health:

```bash
curl http://127.0.0.1:8190/healthz
```

List filings:

```bash
curl 'http://127.0.0.1:8190/api/filings?source=cninfo&stock_code=000725'
```

List runs:

```bash
curl 'http://127.0.0.1:8190/api/runs?limit=20'
```

Create subscription:

```bash
curl -X POST http://127.0.0.1:8190/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{"name":"boe-annual","source":"cninfo","stock_code":"000725","kind":"annual","target":"local:test"}'
```

Trigger sync:

```bash
curl -X POST http://127.0.0.1:8190/api/sync \
  -H 'Content-Type: application/json' \
  -d '{"sources":["cninfo"]}'
```

## Docker + Tailscale

Phase 3 adds a containerized frontend/backend path:

```text
Browser -> :443 (tailscale serve) -> 127.0.0.1:8190 -> nginx -> /api -> backend:8190
```

Quick start:

```bash
docker compose up -d --build
./scripts/setup_tailscale_serve.sh
./scripts/verify_tailscale_serve.sh
```

The detailed runbook lives in `docs/TAILSCALE_SERVE.md`.

## Release Contract

项目仓现在只负责两件事：

- 维护应用代码和 Dockerfile
- 通过 `.github/workflows/docker.yml` 构建镜像并向 release config repo 提交 digest 更新 PR

最小发布契约放在 `ops/services/*.yaml`：

- `corp-finance-monitor-backend.yaml`
- `corp-finance-monitor-frontend.yaml`

每个契约只声明：

- `service_name`
- `dockerfile`
- `internal_port`
- `healthcheck_path`
- `exposure`
- `env_profile`

运行时 secrets、宿主机端口映射、rootless Podman 编排、Tailscale/Envoy 暴露都移到独立 release config repo 处理。

## Legacy Deploy Artifacts

旧的 `deploy/` 目录和基于 systemd/ansible 的项目内发布脚本已经移除。

新链路是：

```text
project repo -> build images -> release config PR -> controlled runner deploy
```

当前生产发布由 `gtr-release-config` 的受控 self-hosted runner 在 Tencent 节点执行。

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
- Docker + Tailscale deployment path documented under `docs/TAILSCALE_SERVE.md`

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
