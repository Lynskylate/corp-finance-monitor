# corp-finance-monitor 架构文档

> 多源企业财报发现、下载、查询与订阅系统。
> 调研日期: 2026-06-02

---

## 1. 项目概览

| 项目 | 说明 |
|------|------|
| 目的 | 从多个交易所/数据源自动发现并下载企业财报，提供查询 API 和前端界面，支持订阅通知 |
| 语言 | Python 3.10+ (后端), TypeScript/React (前端) |
| 包管理 | uv (Python), npm (前端) |
| 构建 | hatchling (Python wheel), Vite (前端) |
| 部署 | Docker Compose (生产), shell script (本地 CD) |

---

## 2. 整体架构

```
                          ┌─────────────────────────┐
                          │     Browser / curl       │
                          └──────────┬──────────────┘
                                     │ HTTPS (tailscale serve)
                          ┌──────────▼──────────────┐
                          │   nginx (frontend:80)    │
                          │   / → SPA               │
                          │   /api/* → backend:8190  │
                          │   /healthz → backend     │
                          └──────────┬──────────────┘
                                     │ HTTP
                          ┌──────────▼──────────────┐
                          │  FastAPI (backend:8190)  │
                          │  - /api/filings          │
                          │  - /api/runs             │
                          │  - /api/subscriptions    │
                          │  - /api/sync (POST)      │
                          └──────────┬──────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
  ┌───────▼───────┐        ┌────────▼────────┐       ┌────────▼────────┐
  │  Engine       │        │  DiskStorage    │       │ SQLiteStateStore│
  │  (编排器)      │        │  (文件存储)      │       │  (状态/订阅)     │
  │  discover→    │        │  data/filings/  │       │  data/.cfm_state│
  │  dedup→fetch→ │        │  {src}/{stock}/ │       │  /state.db      │
  │  store→notify │        │  {kind}/*.pdf   │       └────────────────┘
  └───────┬───────┘        └────────────────┘
          │
  ┌───────┴─────────────────────────┐
  │         Sources (数据源)          │
  │  ┌────────┐ ┌──────┐ ┌────────┐ │
  │  │ cninfo │ │ sse  │ │ hkex   │ │
  │  │ (A股)  │ │(上交所)│ │ (港股) │ │
  │  └────────┘ └──────┘ └────────┘ │
  └───────────────────────────────────┘
```

---

## 3. 后端架构 (`src/corp_finance_monitor/`)

### 3.1 模块结构

```
src/corp_finance_monitor/
├── __main__.py          # python -m 入口 → cli.main
├── api.py               # FastAPI 应用工厂 + 6 个 REST 端点
├── core/
│   ├── __init__.py      # 导出 Config, Engine, 抽象类, 模型
│   ├── config.py        # Config / SourceConfig / StorageConfig / API 配置
│   ├── model.py         # FilingRef, Filing, FilingKind, RunRecord, Subscription
│   ├── source.py        # AbstractSource (discover/fetch/close)
│   ├── storage.py       # AbstractStorage (增删改查)
│   ├── state.py         # AbstractStateStore (去重/运行记录/订阅)
│   └── engine.py        # Engine: 编排发现→下载→存储→通知的全流程
├── sources/
│   ├── __init__.py      # 注册 cninfo/sse/hkex
│   ├── base.py          # HTTP 工具 (重试/UA/时间戳解析)
│   ├── cninfo.py         # 巨潮资讯网适配器
│   ├── sse.py           # 上交所适配器
│   └── hkex.py          # 港交所适配器
├── storage/
│   └── disk.py          # 本地文件存储 + SQLite 元数据索引
├── state/
│   └── sqlite.py        # SQLite 状态存储 (3 表: filing_state/run_log/subscriptions)
├── notifiers/
│   ├── base.py          # AbstractNotifier
│   ├── registry.py      # NotifierRegistry (按 target 前缀路由)
│   ├── webhook.py       # HTTP POST 投递 (已实现)
│   ├── email.py         # stub
│   └── wechat.py        # stub
└── cli/
    └── main.py          # argparse CLI (run/sync/list/runs/subscribe/serve/init)
```

### 3.2 核心流程 (Engine.run_once)

```
Config → Engine.initialize()
  → _init_storage()      # DiskStorage + meta.db
  → _init_state_store()  # SQLiteStateStore + state.db
  → _init_sources()      # 按 config 加载启用的 source
  → _init_notifiers()    # Webhook / Email / WeChat

Engine.run_once(sources?, since?)
  └─ for each source:
       ├─ source.discover(watchlist, since) → List[FilingRef]
       ├─ Engine._is_already_fetched(ref)    # dedup by unique_key
       ├─ source.fetch(ref) → Filing (bytes)
       ├─ storage.store(filing) → stored_path
       ├─ Engine._record_state(ref, path)    # 写入 state.db
       └─ Engine._notify(ref, stored_path)   # 按订阅投递通知
  └─ state_store.record_run(start, end, stats)
```

### 3.3 HTTP API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 健康检查 → `{"ok": true}` |
| GET | `/api/filings?source=&stock_code=&kind=&since=&limit=&offset=` | 列表(分页+过滤) |
| GET | `/api/filings/{source}/{source_id}` | 详情 + 落盘路径 |
| GET | `/api/runs?limit=20` | 运行历史 |
| GET | `/api/subscriptions?source=&stock_code=&active_only=` | 订阅列表 |
| POST | `/api/subscriptions` | 创建订阅 (JSON: name/source/stock_code/kind/target) |
| POST | `/api/sync` | 触发同步 (JSON: {sources, since})，有 run_lock 互斥 (409) |

### 3.4 数据模型

```
FilingKind(Enum): annual / semi / q1 / q3 / prospectus / esg / interim / quarterly / other

FilingRef:
  source + source_id = unique_key (去重依据)
  stock_code, stock_name, title, kind, published_at, url

Filing:
  FilingRef ref
  bytes content
  content_type, file_size, stored_path

Subscription:
  id, name, source, stock_code, kind, target, active

RunRecord:
  id, started_at, finished_at, discovered, fetched, failed
```

### 3.5 股票注册表 (Stock Registry)

`src/corp_finance_monitor/sources/stock_registry.py` — 自动获取并缓存 cninfo 全量股票列表:

- 数据源: `http://www.cninfo.com.cn/new/data/szse_stock.json` (~6000 条, 无需分页)
- 本地缓存: `data/.cfm_state/stocks.db` (SQLite), TTL 24 小时自动过期
- 失败时 graceful degradation (返回空列表, 不 crash)
- `StockEntry`: stock_code, org_id, name, exchange (SZSE/SSE/BSE), category
- 交易所推断: 0/2/3 开头 → SZSE, 4/8/920 → BSE, 其他 → SSE

### 3.6 数据源适配器

| 数据源 | 市场 | 报告类型 | API 方式 |
|--------|------|----------|----------|
| cninfo | A股 (深交所+上交所+北交所) | 年报/中报/Q1/Q3 | POST JSON |
| sse | 上交所 | 招股书 | GET JSONP → _jsonp_clean |
| hkex | 港股 | 年报/中报/季报/招股书 | GET → 内嵌 JSON string |

---

## 4. 前端架构 (`frontend/`)

### 4.1 技术栈

| 技术 | 用途 |
|------|------|
| React 19 | UI 框架 |
| TypeScript 6.0 | 类型系统 |
| Vite 8 | 构建工具 + dev server (proxy /api → 127.0.0.1:8190) |
| Tailwind CSS 4 | 样式框架 |
| @tanstack/react-query 5 | 服务端状态/数据获取 |
| react-router-dom 7 | 路由 |
| shadcn/ui (Radix) | UI 组件库 |
| lucide-react | 图标 |

### 4.2 组件结构

```
frontend/src/
├── main.tsx                        # 入口: StrictMode + AppProviders + RouterProvider
├── index.css                       # Tailwind 入口
├── app/
│   ├── providers.tsx               # QueryClientProvider (retry=1, staleTime=30s)
│   ├── router.tsx                  # 3 路由: / → HomePage, /filings/:source/:sourceId, *
│   └── shell.tsx                   # AppShell: header + nav + Outlet
├── routes/
│   ├── home-page.tsx               # 首页: stats + LatestUpdatesPanel + CodeSearchPanel
│   ├── filing-detail-page.tsx      # 详情: show metadata + stored_path + original link
│   └── not-found-page.tsx          # 404
├── features/
│   ├── filings/
│   │   ├── types.ts               # FilingItem, FilingListResponse, FilingDetailResponse
│   │   ├── api.ts                 # listFilings(), getFilingDetail()
│   │   ├── constants.ts           # SOURCE_OPTIONS, KIND_OPTIONS
│   │   └── components/
│   │       ├── filing-table.tsx   # 统一表格: stock_code/title/kind/time/actions
│   │       ├── latest-updates-panel.tsx  # 最新更新流 (过滤+分页)
│   │       └── code-search-panel.tsx     # 按代码查询面板
│   └── lookup/
│       └── components/
│           └── code-search-panel.tsx     # (复用 filing-table)
├── lib/
│   ├── api-client.ts              # fetchJson<T>() with ApiError
│   ├── format.ts                  # formatDateTime, formatKind, formatRelativeTime
│   └── utils.ts                   # cn() (tailwind-merge + clsx)
└── components/ui/                  # shadcn/ui 组件 (card, button, input, badge, etc.)
```

### 4.3 数据流

```
HomePage
  ├─ useQuery(['latest-filings', filters]) → listFilings({limit, offset, source, kind})
  ├─ useQuery(['stock-filings', activeStockCode]) → listFilings({stockCode})
  └─ render: stats / LatestUpdatesPanel / CodeSearchPanel

FilingDetailPage
  └─ useQuery(['filing-detail', source, sourceId]) → getFilingDetail()
```

### 4.4 前端 Docker 部署

```Dockerfile
# Multi-stage build: node:22-slim build → nginx:1.27-alpine serve
# Build: npm ci → npm run build
# Serve: nginx with:
#   - /assets/ → 1y cache (immutable)
#   - /api/ → proxy_pass backend:8190
#   - / → SPA fallback (index.html)
```

---

## 5. 存储架构

### 5.1 文件存储 (DiskStorage)

```
{base_dir}/
├── filings/
│   └── {source}/
│       └── {stock_code}/
│           └── {kind}/
│               └── {published_at}_{source_id}_{title}.pdf
└── .cfm_state/
    └── meta.db       # 文件元数据索引 (SQLite)
```

### 5.2 状态存储 (SQLiteStateStore)

```
state.db 包含 3 张表:

filing_state — 去重记录:
  unique_key (PK), source, source_id, stock_code, title, kind,
  published_at, fetched_at, stored_path

run_log — 运行历史:
  id (PK autoincrement), started_at, finished_at, discovered, fetched, failed

subscriptions — 订阅:
  id (PK autoincrement), name, source, stock_code, kind, target,
  active, created_at, updated_at
```

---

## 6. CI/CD 流水线

### 6.1 CI — 代码质量与构建 (`.github/workflows/ci.yml`)

| 阶段 | 触发条件 | 内容 |
|------|----------|------|
| **test** | push/PR → main/master, workflow_dispatch | Python 3.10/3.11/3.12 × unittest |
| **build** | test 通过后 | uv build → wheel + sdist → upload artifact (30d retention) |

详细步骤:
```
test job:
  1. checkout@v4
  2. astral-sh/setup-uv@v6
  3. setup-python@v5 (matrix: 3.10, 3.11, 3.12)
  4. uv sync
  5. uv run python -m unittest discover -s tests -p "test_*.py" -v

build job:
  1. (needs: test)
  2. checkout@v4 + uv + python 3.12
  3. uv build
  4. upload-artifact@v4: dist/ → 保留 30 天
```

### 6.2 CD — Docker 镜像构建 + Release PR (`.github/workflows/docker.yml`)

采用了 **Release Contract** 模式：由 `ops/` 目录中的服务声明文件驱动构建。

| 阶段 | 触发条件 | 内容 |
|------|----------|------|
| **discover** | push → main/master, tag v*, workflow_dispatch | 扫描 `ops/services/*.yaml` → 生成 build matrix |
| **build-and-push** (matrix) | discover 通过后 | 按 matrix 并行构建各服务镜像 → push GHCR → 保存 release metadata + image artifact |
| **open-release-pr** | build-and-push 通过后 (仅 main/master) | 更新 `Lynskylate/gtr-release-config` 仓库的 stack yaml → 自动创建/merge PR |

详细步骤:
```
discover job:
  1. checkout@v4
  2. 运行 python ops/scripts/list_services.py
  3. 输出 matrix JSON 到 $GITHUB_OUTPUT
     → matrix 包含 {service_name, dockerfile, context, image_repository, build_args, internal_port, ...}

build-and-push job (matrix: backend + frontend):
  1. checkout@v4
  2. docker/setup-buildx-action@v3
  3. docker/login-action@v3 → ghcr.io (GITHUB_TOKEN)
  4. docker/build-push-action@v6:
     - context: matrix.context (`.` or `frontend`)
     - file: matrix.dockerfile (`Dockerfile` or `frontend/Dockerfile.ci`)
     - push: true
     - tags: {image_repo}:{sha}, latest
     - build-args: (frontend → VITE_API_BASE_URL=/api)
     - cache: gha
  5. Write release metadata JSON (service_name, image_repository, digest, tag, source, internal_port, healthcheck_path, exposure, env_profile)
  6. docker save → .tar artifact (保留 7 天)
  7. Upload release metadata + image archive

open-release-pr job:
  1. (if: github.ref_name == main/master)
  2. Download release metadata from all build-and-push jobs
  3. Sync GHCR read token to release-config repo
  4. Check out Lynskylate/gtr-release-config
  5. python ops/scripts/update_release_repo.py → 更新 stack yaml 中的 image digest
  6. peter-evans/create-pull-request@v6 → 创建 release PR
  7. gh pr merge --merge --delete-branch → 自动合并
```

### 6.3 Release Contract (`ops/` 目录)

```
ops/
├── services/
│   ├── corp-finance-monitor-backend.yaml   # service_name, dockerfile, internal_port, healthcheck, exposure, env_profile
│   └── corp-finance-monitor-frontend.yaml  # 同上
└── scripts/
    ├── list_services.py      # 扫描 services/*.yaml → GH Actions matrix
    └── update_release_repo.py # 更新 release-config 仓库的 stack yaml 中的 digests
```

服务声明示例:
```yaml
apiVersion: deploy.lynskylate/v1alpha1
kind: ProjectService
service_name: corp-finance-monitor-backend
dockerfile: Dockerfile
internal_port: 8190
healthcheck_path: /healthz
exposure: none
env_profile: corp-finance-monitor-backend
```

### 6.4 部署拓扑

#### Docker 部署 (生产) — `docker-compose.yml`

```
┌───────────────────────────────────┐
│  Docker Host (tailscale node)     │
│                                   │
│  ┌───────────┐   ┌──────────────┐ │
│  │ frontend  │   │   backend    │ │
│  │ nginx:80  │←──│  FastAPI     │ │
│  │ SPA + API │   │  :8190       │ │
│  │ proxy     │   │  + config    │ │
│  └─────┬─────┘   └──────┬───────┘ │
│        │                │         │
│  ┌─────▼────────────────▼───────┐ │
│  │  volumes: config.yaml, data/ │ │
│  └──────────────────────────────┘ │
│                                    │
│  tailscale serve :8190 → :443     │
│  → corp-finance-monitor.xxx.ts.net│
└───────────────────────────────────┘
```

#### 镜像来源

```
GitHub Actions build → ghcr.io/lynskylate/
  ├── corp-finance-monitor-backend:{sha, latest}
  └── corp-finance-monitor-frontend:{sha, latest}

docker-compose.yml 通过 ghcr.io 拉取:
  image: ghcr.io/lynskylate/corp-finance-monitor-{backend|frontend}:${IMAGE_TAG:-latest}
```

---

## 7. 通知系统

| 投递方式 | target 前缀 | 状态 |
|----------|-------------|------|
| Webhook | `http://` / `https://` | ✅ 已实现 (POST JSON) |
| Email | `email:` | ⚠️ stub |
| WeChat | `wechat:` | ⚠️ stub |

路由逻辑: `NotifierRegistry.dispatch()` — source/stock_code/kind 任一为空即通配。

---

## 8. 配置结构 (config.yaml)

```yaml
engine:
  run_once: true              # true=一轮后退出, false=持续轮询
  interval_minutes: 360       # 轮询间隔
  fetch_delay_seconds: 0.5    # 下载间延迟
  concurrency: 1

storage:
  backend: disk               # 仅支持 disk
  base_dir: ./data            # 相对路径基于 config 文件所在目录

state_store:
  backend: sqlite
  path: ./data/.cfm_state/state.db

api:
  host: 0.0.0.0
  port: 8190

sources:
  cninfo:                     # 数据库名称 → 映射到 SOURCE_REGISTRY
    enabled: true
    watchlist:
      - stock: "000725"
        org_id: "gssz0000725"
        kinds: [annual, semi, q1, q3]
  sse:
    enabled: true
    watchlist: []
  hkex:
    enabled: true
    watchlist:
      - stock: "00700"
        kinds: [annual, interim]
```

---

## 9. 已知约束与扩展点

| 约束/问题 | 说明 |
|-----------|------|
| 跨进程 sync 锁 | api.py 的 run_lock 是 per-process Lock，多实例会 race |
| 日志轮转 | 容器化后依赖 Docker log driver，宿主机无额外 logrotate |
| 无 subscription 删除/更新 API | 仅有 create 和 list |
| no remote-write backends | Email/WeChat 通知器是 stub |
| 无 runs 统计 API | 仅有 list |
| Python 过渡 | 设计时预留了 Go/Rust 迁移路径 (相同接口抽象) |
| release-config repo token | 需要 `RELEASE_CONFIG_REPO_TOKEN` secret 才能 auto-merge PR |
| stock registry 仅 cninfo | 上交所/港交所的股票注册表尚未实现 |

---

## 10. 代码质量

- 测试框架: unittest (12 个测试文件)
- 测试覆盖: 数据源单元测试 / API smoke / 部署校验 / E2E / 并发 / 分类 / 股票注册表 / release contract
- 前端校验: `npm run check` = eslint + tsc -b + vite build
- CI 矩阵: Python 3.10 / 3.11 / 3.12

---

## 11. 依赖清单

**Python (pyproject.toml)**:
- requests >= 2.28
- pyyaml >= 5.4
- fastapi >= 0.100
- uvicorn >= 0.20

**前端 (package.json)**:
- react 19, react-dom 19, react-router-dom 7
- @tanstack/react-query 5
- @radix-ui/react-slot
- tailwindcss 4, vite 8, typescript 6
- lucide-react, class-variance-authority, tailwind-merge
