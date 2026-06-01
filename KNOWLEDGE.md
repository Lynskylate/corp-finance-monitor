# corp-finance-monitor 知识库 (Knowledge Base)

> 这是一份为后续工作记录的关键事实、约定、踩坑点和扩展点。
> 任何对项目的修改、迁移、扩展前请先翻阅本文件。

---

## 1. 项目定位

- **目标**：多源企业财报/公告发现与下载系统。
- **数据源**：
  - `cninfo` — 巨潮资讯网 (A股 定期报告：年报/中报/Q1/Q3)
  - `sse`    — 上交所 (IPO 招股书)
  - `hkex`   — 港交所披露易 (港股 年报/中报/季报/招股书)
- **存储**：
  - 文件存储：`DiskStorage` (默认路径 `data/filings/<source>/<stock>/<kind>/...pdf`)
  - 元数据：`data/.cfm_state/meta.db` (filings 索引，唯一键 = `source:source_id`)
  - 状态：`data/.cfm_state/state.db` (filing_state / run_log / subscriptions)
- **入口**：
  - CLI: `python3 main.py {run|sync|list|runs|subscribe|serve|init} -c config.yaml`
  - HTTP: `python3 main.py serve -c config.yaml` (默认 `127.0.0.1:8190`)

## 2. 架构与模块布局

```
src/corp_finance_monitor/
├── core/         # 抽象与领域模型
│   ├── config.py    # Config dataclass + YAML 解析 (含相对路径解析)
│   ├── model.py     # FilingRef, Filing, FilingKind, RunRecord, Subscription
│   ├── source.py    # AbstractSource: discover() / fetch() / close()
│   ├── storage.py   # AbstractStorage: 增删查、exists、find_ref
│   ├── state.py     # AbstractStateStore: 去重、运行记录、订阅
│   └── engine.py    # Engine: 编排 (load→init→discover→dedup→fetch→store→notify→record)
├── sources/      # 三个数据源实现
│   ├── base.py      # http_get/http_post (重试/UA), parse_timestamp
│   ├── cninfo.py    # POST /new/hisAnnouncement/query
│   ├── sse.py       # GET query.sse.com.cn/commonSoaQuery.do (JSONP)
│   └── hkex.py      # GET /search/titleSearchServlet.do
├── storage/
│   └── disk.py      # 本地 PDF 存储 + SQLite 元数据
├── state/
│   └── sqlite.py    # 三张表: filing_state / run_log / subscriptions
├── notifiers/    # 订阅投递
│   ├── base.py      # AbstractNotifier + NotifierResult
│   ├── registry.py  # NotifierRegistry.dispatch(): 按 target 路由
│   ├── webhook.py   # ✅ 已实现 (POST JSON)
│   ├── email.py     # ⚠️ stub (匹配 `email:` 前缀)
│   └── wechat.py    # ⚠️ stub (匹配 `wechat:` 前缀)
├── api.py        # ThreadingHTTPServer, 端点见下
└── cli/main.py   # argparse 子命令
```

## 3. HTTP API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查 |
| GET | `/api/filings?source=&stock_code=&kind=&since=` | 列出已存文件 |
| GET | `/api/filings/<source>/<source_id>` | 单个文件详情 |
| GET | `/api/runs?limit=20` | 同步运行历史 |
| GET | `/api/subscriptions?source=&stock_code=&active_only=` | 列出订阅 |
| POST | `/api/subscriptions` | 创建订阅 (JSON body) |
| POST | `/api/sync` | 触发一轮同步, body: `{"sources": ["cninfo"]}` |

`/api/sync` 端点有 `run_lock` 互斥，并发触发会返回 409。

## 4. CLI 关键约定

- `sync --since YYYY-MM-DD`：显式起始日期
- `sync --since full`：全量同步，忽略日期过滤
- `sync` 不带 `--since`：自动从 `state_store.last_successful_run_start()` 推断
- `run_once: true` (config) → 执行一轮退出；`false` → 持续轮询
- `interval_minutes=360` 默认 6 小时轮询

## 5. 数据模型与去重

- `FilingRef.unique_key = f"{source}:{source_id}"` 是全局唯一键
- 三大数据源 `source_id` 来源：
  - cninfo: `announcementId`
  - sse: `f"audit_{auditId}_{fileVersion}"` (合成)
  - hkex: `NEWS_ID`
- `FilingKind` 枚举：`annual / semi / q1 / q3 / prospectus / esg / interim / quarterly / other`
- 标题分类规则：cninfo 按关键词匹配；hkex 用 `_resolve_kind` 按关键词在 title 中检索
- 中英文约定：
  - A股 标题用 "年度报告/半年度报告/一季度报告/三季度报告"
  - 港股 title 用 "ANNUAL REPORT/INTERIM REPORT/..." (大写英文)
  - "半年度报告" 与 "中期报告" 都归类为 `SEMI`

## 6. 已验证的分类示例 (来自 README)

| 标题 | kind |
|---|---|
| 2025年年度报告 | `annual` |
| 2025年年度报告摘要 | `other` |
| 2025年半年度报告 | `semi` |
| 2025年半年度报告摘要 | `semi` |

## 7. HTTP 客户端约束 (sources/base.py)

- `HEADERS` 使用固定 Chrome 125 UA
- `TIMEOUT=30` 秒, `MAX_RETRIES=3` (指数退避 `2 ** attempt`)
- `parse_timestamp(ts)` 支持：8位 `YYYYMMDD`、毫秒时间戳 (按 UTC+8 解析)、其他截前 10 字符
- cninfo 端点需要 `Referer: https://www.cninfo.com.cn/new/disclosure/stock?stockCode=...` + `X-Requested-With: XMLHttpRequest`
- sse 返回 JSONP，需要 `_jsonp_clean()` 去掉 `jsonpCallbackNNN(...)` 包裹
- hkex 端点 `result` 字段是 JSON 字符串，需要二次 `json.loads()`

## 8. 通知 (Notifier) 路由

- 订阅 `target` 字符串前缀决定路由：
  - `http://` / `https://` → `WebhookNotifier`
  - `email:` → `EmailNotifier` (stub)
  - `wechat:` → `WeChatNotifier` (stub)
- 订阅匹配规则 (`registry.dispatch`)：source / stock_code / kind 三者任一为空即通配
- 通知在 `Engine._notify()` 中触发：每次 `store` 成功之后

## 9. 已知 TODO / 扩展点

来自 README "Next steps"：
- HTTP API 增加分页 / 过滤扩展
- 投递后端从 stub 变为真实实现 (email/wechat)
- `tests/` 目录目前是空的，需要补充
- 当 go/rustc/cargo 可用时可整体迁移运行时 (Python 仅作过渡)
- 没有 `subscription delete` / `update` 端点，仅有 `create` 和 `list`
- 没有 `runs` 的统计 API (只列记录)

## 10. 迁移 / 二次开发时易踩的坑

- `Config.from_file()` 内部对 `storage.base_dir` 与 `state_store.path` 用 `_resolve_path()` 做相对路径解析，**相对路径基于配置文件所在目录**，不是 CWD。
- `state.db` 与 `meta.db` 是**两个独立 SQLite 文件**：state.db 存去重+运行日志+订阅；meta.db 存文件索引。
- `Engine._is_already_fetched()` 会同时查 state_store 与 storage。如果 disk 上有文件但 state_store 没有，会自动补登记 (修复存量数据)。
- 增量同步 (`--since`) 的"上次成功运行"判定：`state.db.run_log` 中 `fetched > 0` 的最新 `started_at`。
- cninfo `column` 推断靠股票代码首位：`0/2/3` → szse，`4/8` → bj，其余 → sse。
- HKEX 调用前要先 GET `STOCK_LIST_URL` 拿到 `stockId` 内部 ID（带 5 位补零）。
- `sse.discover()` 通过 `auditId` 二次查询文件列表，再按 `fileType == "30"` 过滤出招股书。
- HTTP API 创建订阅时 `name` 必填，其余字段可空 → 空字段在通知匹配时为通配。
- `api.py` 端点的 `run_lock` 是 `threading.Lock()`，仅防线程内并发，不能跨进程防抖。

## 11. 关键外部脚本（已废弃但保留）

`/home/lynskylate/` 下有原独立脚本，新版本不应再调用它们：
- `cninfo_financial_reports.py` — 已被 `src/corp_finance_monitor/sources/cninfo.py` 吸收
- `sse_ipo_prospectus.py`      — 已被 `src/corp_finance_monitor/sources/sse.py` 吸收
- `hkex_filings.py`            — 已被 `src/corp_finance_monitor/sources/hkex.py` 吸收

新需求请直接改 source 适配器，**不要**继续维护这三个脚本。

## 12. 常用命令速查

```bash
# 生成示例配置
python3 /home/lynskylate/corp-finance-monitor/main.py init config.yaml

# 单源同步（自动增量）
python3 /home/lynskylate/corp-finance-monitor/main.py sync -c config.yaml --source cninfo

# 全量同步
python3 /home/lynskylate/corp-finance-monitor/main.py sync -c config.yaml --source cninfo --since full

# 启动 API
python3 /home/lynskylate/corp-finance-monitor/main.py serve -c config.yaml --host 127.0.0.1 --port 8190

# 添加订阅
python3 /home/lynskylate/corp-finance-monitor/main.py subscribe add -c config.yaml \
  --name boe-annual --source cninfo --stock 000725 --kind annual \
  --target https://example.com/webhook

# 触发 API 同步
curl -X POST http://127.0.0.1:8190/api/sync \
  -H 'Content-Type: application/json' -d '{"sources":["cninfo"]}'
```

## 13. 运行时依赖

- Python ≥ 3.10
- `requests >= 2.28`
- `pyyaml >= 5.4`
- 系统无 go / rustc / cargo (迁移至 Go/Rust 前需要先装工具链)
