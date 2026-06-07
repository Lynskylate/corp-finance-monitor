# AGENTS.md

本仓库是 **corp-finance-monitor（CFM）** — 多源企业财报发现、下载、查询与订阅系统。包含 Python 后端（FastAPI）、TypeScript/React 前端、Docker Compose 部署、以及 CI/CD 流水线。

所有文档使用 **中文**。

## 核心规矩

1. **Bootstrap 不是全量扫描** — 初始 stock registry 只覆盖 cninfo 的 50 只股票编码（`only_stock_codes=50`），不是全市场 6000+。部署后需要逐步扩展 watchlist。截至 2026-06，仅覆盖约 10% A 股。

2. **`--reset` 是全局的，不是 per-source** — `--reset` 清空全部数据源的 `scan_progress`，会导致已扫描的所有 source 进度丢失。目前没有 `--reset-source` 实现。修改 fetch_filter 后也需手动清 `scan_progress`，否则旧检查点会阻止重扫。

3. **cninfo 批查询有 403 限流** — 批量查询 100 只股票会触发 cninfo 的 403 反爬。必须 `concurrency=1` 逐只扫描。fallback 路径在 `cninfo.py` 中实现。

4. **单写者约束** — 手动运行 `sync` 之前必须停掉 scheduler（`systemctl stop scheduler.timer`），防止并发写 SQLite 导致冲突。

5. **Docker 网络** — Podman CNI bridge 在 K3s 10.x 子网下会冲突，已迁移到 host 网络模式（`docker-compose.yml` 使用 `network_mode: host`）。容器 DNS 在某些环境下需要显式 `--dns` 参数。

6. **Pre-commit** — 提交前自动运行 ruff format + ruff check。安装：`pip install pre-commit && pre-commit install`。或使用 Makefile：`make fix`（check --fix → format）。

## 仓库结构

```
corp-finance-monitor/
├── src/corp_finance_monitor/   # 后端源码
│   ├── api.py                  # FastAPI 应用工厂 (6 个 REST 端点)
│   ├── core/                   # Config, Engine, 抽象类, 模型
│   ├── sources/                # cninfo, sse, hkex 数据源适配器
│   ├── storage/disk.py         # 本地文件存储 + SQLite 元数据
│   ├── state/sqlite.py         # SQLite 状态存储 (3 表)
│   ├── notifiers/              # Webhook/Email/WeChat 通知器
│   └── cli/main.py             # argparse CLI
├── frontend/                   # React 19 + Vite 8 + Tailwind 4
│   └── src/
│       ├── app/                # providers, router, shell
│       ├── routes/             # home-page, filing-detail-page
│       └── features/filings/   # API client, types, components
├── tests/                      # 12 个 unittest 测试文件
├── ops/                        # Release Contract (服务声明 + 脚本)
│   └── services/               # backend.yaml, frontend.yaml
├── docs/                       # 架构文档、开发规范
├── data/                       # 本地开发数据目录
│   ├── filings/                # 下载的财报 PDF
│   └── .cfm_state/             # SQLite 状态 + 元数据
├── docker-compose.yml          # 生产部署 (host networking)
├── config.yaml                 # 引擎 + 数据源配置
├── Makefile                    # 开发命令入口
├── pyproject.toml              # Python 依赖 (uv + hatchling)
└── .github/workflows/          # CI (ci.yml) + CD (docker.yml)
```

## 基础设施拓扑

```
生产部署 (GTR, Podman host networking):
┌──────────────────────────────────────┐
│  Docker Host (tailscale node)        │
│                                      │
│  nginx (frontend:80)                 │
│  ├─ / → SPA (React)                 │
│  ├─ /api/* → backend:8190 (FastAPI) │
│  └─ /healthz → backend:8190         │
│                                      │
│  backend (FastAPI:8190)              │
│  ├─ Engine (discover→dedup→fetch)   │
│  ├─ DiskStorage (data/filings/)     │
│  └─ SQLiteStateStore (state.db)     │
│                                      │
│  tailscale serve :8190 → :443       │
│  → corp-finance-monitor.{tailnet}   │
└──────────────────────────────────────┘

数据源:
  cninfo (A股 ~6119 stocks, concurrency=1, 403 fallback)
  hkex  (港股 ~18292 stocks, concurrency=3)
  sse   (上交所, 招股书)

状态存储 (SQLite):
  filing_state   — 去重记录 (unique_key PK)
  run_log        — 运行历史 (id autoincrement)
  subscriptions  — 订阅 (id autoincrement)

数据路径:
  本地开发: /home/lynskylate/workspace/corp-finance-monitor/data/
  生产容器: /srv/projects/corp-finance-monitor/data/ (volume mount)
```

## 常用命令

```bash
# === 本地开发 ===
cd /home/lynskylate/workspace/corp-finance-monitor
uv sync                          # 安装依赖
make test                        # 跑全部测试
make fix                         # ruff check --fix + format
make gate                        # lint + test (预提交门禁)
make gate-full                   # lint + test + frontend build

# === 前端 ===
cd frontend && npm install && npm run dev   # Vite dev server (proxy /api → 127.0.0.1:8190)
cd frontend && npm run build                # 生产构建

# === 引擎运行 ===
uv run python -m corp_finance_monitor sync --since 2026-06-01   # 增量同步
uv run python -m corp_finance_monitor sync --since full --reset  # 全量重置（⚠️ 清全部 source 进度）
uv run python -m corp_finance_monitor serve                       # 启动 API 服务

# === 生产运维 ===
systemctl stop scheduler.timer    # 停调度器（单写者约束）
podman-compose up -d              # 启动服务
podman logs corp-finance-monitor-backend --tail 50  # 查看日志
curl http://127.0.0.1:8190/healthz                 # 健康检查
curl http://127.0.0.1:8190/api/stats                # 实时统计
sqlite3 /srv/projects/corp-finance-monitor/data/.cfm_state/state.db "SELECT * FROM scan_progress;"  # 扫描进度

# === CI/CD ===
gh workflow run ci.yml --ref main
gh workflow run docker.yml --ref main
```

## Gotchas

1. **Bootstrap 只覆盖 50 只股票**（`only_stock_codes=50`）。如果要扩展市场覆盖，需手动添加 watchlist 条目并重新 sync。

2. **`--reset` 清全部 source 的 scan_progress**，不是 per-source。没有 `--reset-source` 实现。后果：如果只想重扫 cninfo，HKEX 12 小时的扫描进度也会丢失。

3. **cninfo 批查询 100 只会触发 403**。`concurrency=1` 逐只扫描是生存策略，不是性能优化。

4. **fetch_filter 修改后旧 scan_progress 阻止重扫**。需手动清对应 source 的 scan_progress（目前无细粒度 API，只能 `--reset` 全局清）。

5. **手动 sync 前停 scheduler**。`systemctl stop scheduler.timer`，否则 SQLite 并发写冲突。

6. **数据路径区分**：本地开发是 `/home/lynskylate/workspace/corp-finance-monitor/data/`，生产 Podman 挂载是 `/srv/projects/corp-finance-monitor/data/`。文档和脚本中不要混用。

7. **Podman CNI bridge 与 K3s 10.x 子网冲突**。已迁移到 host 网络。新增容器注意 `network_mode: host`。

8. **podman logs 可能报 `cannot assign requested address`**。fallback：`sudo journalctl -u podman-cor-finance-monitor-backend` 或 `sudo cat /var/log/syslog | grep corp-finance`。

9. **GitHub Actions billing 可能阻断 CD**。如果 CI/CD 不可用，需要手动 `docker build` + `docker push` ghcr.io，然后 `podman-compose pull && podman-compose up -d`。

10. **pdftotext 不是预装的**。首次使用需 `sudo apt install poppler-utils`。

11. **增量 sync 的 `since` 窗口基于上次运行开始时间**，不是最后一份 filing 时间。如果超过 3 个月未运行（如财报淡季），下次增量 sync 会漏掉期间所有 filing。这就是 cninfo 覆盖缺口长期未被发现的原因 — `since` 窗口总是太窄。解决办法：定期（至少每月）执行一次 `--since full` 全量扫描作为兜底。

## 文档索引

| 主题 | 文档 |
|------|------|
| 项目概览 + 快速开始 | [`README.md`](README.md) |
| 架构详解 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 本地开发规范 | [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) |
| Tailscale Serve 配置 | [`docs/TAILSCALE_SERVE.md`](docs/TAILSCALE_SERVE.md) |
| 实现计划 | [`PLAN.md`](PLAN.md) |
| 领域知识 | [`KNOWLEDGE.md`](KNOWLEDGE.md) |
| 运维脚本 | [`ops/README.md`](ops/README.md) |
| 前端 | [`frontend/README.md`](frontend/README.md) |
| 测试约定 | [`tests/README.md`](tests/README.md) |
| CI/CD 详细流程 | [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/docker.yml`](.github/workflows/docker.yml) |
