# corp-finance-monitor 开发规范

> 本文档定义了 `corp-finance-monitor` 项目的日常开发流程、质量门禁和协作规范。
> 所有贡献者在提交 PR 前应熟悉并遵循本文档。

---

## 1. 本地开发环境

### 1.1 依赖安装

```bash
# Python 后端 (uv) — 安装所有依赖（含 dev group: ruff）
uv sync

# 前端
cd frontend && npm ci
```

### 1.2 代码风格工具

| 工具 | 范围 | 配置位置 |
|------|------|----------|
| ruff (lint) | `src/` `tests/` | `pyproject.toml [tool.ruff]` |
| ruff (format) | `src/` `tests/` | `pyproject.toml [tool.ruff.format]` |
| ESLint | `frontend/src/` | `frontend/eslint.config.js` |
| TypeScript | `frontend/src/` | `frontend/tsconfig*.json` |

ruff 规则集：E (错误)、F (pyflakes)、I (isort)、B (bugbear)、SIM (simplify)、C4 (comprehensions)、UP (upgrade)、RUF (ruff-specific)；目标 Python 3.10。

### 1.3 快速修复

```bash
make fix       # 自动修复 lint + 格式化 Python 代码
make format    # 仅格式化
cd frontend && npm run lint -- --fix  # 修复 ESLint 问题
```

---

## 2. 质量门禁体系

本项目有三层门禁：**pre-commit hook → 本地 review gate → CI (PR check)**。

### 2.1 Pre-commit Hook（提交时自动运行）

项目默认通过 `.pre-commit-config.yaml` 安装 Git hook。执行 `make pre-commit-install` 后，每次 `git commit` 都会对当前 staged 的 Python 文件运行以下检查：

| 检查项 | 触发条件 | 说明 |
|--------|----------|------|
| ruff format | staged Python 文件 | 自动格式化；如有改动会中断 commit，需重新 stage |
| ruff check | staged Python 文件 | Lint / import / upgrade 规则检查；带 `--fix` 自动修复 |

**安装：**

```bash
make pre-commit-install
```

等价命令：

```bash
uv run pre-commit install
```

**绕过（仅在紧急情况下）：**

```bash
git commit --no-verify
```

> ⚠️ 绕过 pre-commit 并不绕过 CI，CI 仍会检查所有规则。使用 `--no-verify` 的提交如果 CI 不通过，仍需修复。
>
> 如果你想在 commit 前额外检查 staged 的前端文件，可手动运行 `bash scripts/pre-commit.sh`。这个脚本是更严格的本地辅助入口，不是默认安装的 hook。

### 2.2 本地 Review Gate（提交 PR 前）

在请求 code review 之前，运行完整的 review gate 确保所有检查通过。

```bash
# 推荐方式：Makefile
make gate            # Python: lint + format-check + test
make gate-full       # Python + Frontend (eslint + tsc + vite build)

# 或使用脚本
bash scripts/review-gate.sh   # 等价于 make gate-full
```

**Review gate 检查清单：**

| 检查项 | 命令 | 说明 |
|--------|------|------|
| ruff lint | `uv run ruff check src tests` | 全量 lint |
| ruff format check | `uv run ruff format --check src tests` | 格式一致性 |
| Python tests | `uv run python -m unittest discover -s tests -p "test_*.py" -v` | 全量单元测试 |
| ESLint | `cd frontend && npm run lint` | 前端 lint |
| Frontend build | `cd frontend && npm run build` | tsc + vite |

**针对性 gate（仅修改特定模块时）：**

```bash
make gate-scheduling   # 仅检查 scheduling/full_market 相关模块
make test-quick        # 快速本地测试（无网络，<1s）
```

### 2.3 Latest-Main Integrated Gate（任务收口前）

分支上的检查通过并不等于最终合入 `main` 后仍然是绿的。每个代码类 task 在进入 `in_review` 之前，都必须在 **latest `main`** 上跑一次 integrated gate，确认没有格式漂移、flaky test 或主线集成回归。

**标准收口动作：**

```bash
git checkout main
git pull
cd frontend && npm ci && cd ..
make gate-full
```

如果实际交付是在独立 worktree 上完成，等价要求是：**在基于 latest `main` 的干净 worktree 中准备好依赖后运行 `make gate-full` 并贴结果**。

**前置条件：**

- Python 依赖已通过 `uv sync` 准备好
- 如果是干净 worktree，前端依赖要先执行一次 `cd frontend && npm ci`

**thread 中至少要贴这 3 项证据：**

- latest `main` / latest-main worktree 上执行的命令
- gate 结果（pass / fail + 关键输出）
- 最终落到 `main` 的 commit SHA

> 这一步是 task 收口动作，不是可选加分项。feature branch 自己绿，只能证明“局部改动可工作”；latest-main integrated gate 绿，才证明“最终交付可工作”。

### 2.4 CI / PR Check（远程强制）

每次向 `main`/`master` 提交 PR 时，CI 自动运行以下检查：

| Job | 检查内容 | 说明 |
|-----|----------|------|
| `lint` | ruff check + ruff format --check | Python 代码质量 |
| `frontend` | ESLint + tsc + vite build | 前端完整性 |
| `test` (3.10) | unittest discover | 最低支持版本 |
| `test` (3.11) | unittest discover | 中间版本 |
| `test` (3.12) | unittest discover | 当前目标版本 |
| `build` | uv build (wheel + sdist) | 依赖 lint + frontend + test 通过 |

**PR 合并要求（由 branch protection 规则强制）：**

- 以上 6 个 status check 全部通过
- 至少 1 个 reviewer approve
- 分支必须与 main 同步（up-to-date）
- 所有 conversation 已 resolve

> 详见 `.github/branch-protection.md`。

---

## 3. 分支与 PR 流程

### 3.1 分支命名

```
<type>/<short-description>

# 示例
feat/add-hkex-pagination
fix/cninfo-timeout-retry
dx/dev-standards
refactor/engine-concurrency
```

类型前缀：`feat` / `fix` / `refactor` / `dx` / `docs` / `test` / `chore`

### 3.2 开发流程

```
1. 从 main 创建分支
   git checkout main && git pull
   git checkout -b <type>/<description>

2. 本地开发
   - 编写代码 + 测试
   - 频繁运行 make test-quick 或 make gate 做快速验证

3. 提交前检查
   make fix              # 自动修复 lint + 格式化
   make gate-full        # 运行完整 review gate

4. 推送并创建 PR
   git push origin <branch>
   # 在 GitHub 上创建 PR，目标分支为 main

5. CI 自动运行
   - 如果 CI 失败：本地修复后 push 新 commit
   - 如果分支落后 main：先 rebase 再 push
     git fetch origin
     git rebase origin/main

6. 等待 review + CI 全部通过后合并

7. 任务收口前，在 latest `main` 上跑 integrated gate
   git checkout main
   git pull
   make gate-full
   # 在 task thread 贴命令、结果、最终 main commit SHA
```

### 3.3 分支落后 main 的处理

**关键规则：** PR 合并要求分支必须与 main 同步。如果本地分支落后于 main：

```bash
git fetch origin
git rebase origin/main

# 如果有冲突，解决后继续
git add <resolved-files>
git rebase --continue

# 强制推送更新远程分支（rebase 后需要）
git push origin <branch> --force-with-lease
```

> 这是本项目防止"旧分支合并回退 main 已有行为"的核心机制。Branch protection 的 "Require branches to be up to date before merging" 会强制执行这一规则。

### 3.4 Commit 消息规范

```
<type>(<scope>): <简短描述>

# 示例
feat(api): add pagination to /api/filings endpoint
fix(cninfo): handle empty response in discover
dx(lint): update ruff rules to include UP
```

### 3.5 多 Agent 并行开发

当多个 agent 同时在同一仓库工作时：

1. **使用 worktree 隔离：** 每个任务使用独立的 `git worktree`
   ```bash
   cd /home/lynskylate/workspace/corp-finance-monitor
   git worktree add ../corp-finance-monitor-<task> -b <branch> origin/main
   ```

2. **不要在 base checkout 上直接开发：** 保持 `/home/lynskylate/workspace/corp-finance-monitor` 作为干净的 base clone

3. **任务完成后清理 worktree：**
   ```bash
   git worktree remove ../corp-finance-monitor-<task>
   ```

---

## 4. 测试规范

### 4.1 测试分层

| 层级 | 命令 | 范围 | 用途 |
|------|------|------|------|
| 快速测试 | `make test-quick` | 本地、无网络、<1s | 开发中频繁运行 |
| 单元测试 | `make test` | tests/test_*.py（排除 e2e） | 提交前 / CI |
| 针对性测试 | `make test-scheduling` | scheduling/full_market 模块 | 修改特定模块时 |
| E2E 测试 | `make test-e2e` | 需要部署环境 + `RUN_DEPLOYED_E2E=1` | 发布前验证 |

### 4.2 测试文件命名

```
tests/
├── test_cninfo.py              # 数据源单元测试
├── test_engine_concurrency.py  # 并发测试
├── test_e2e_deployed.py        # E2E（需要 live 服务）
├── test_scheduling.py          # 调度逻辑
├── test_scan_checkpoint.py     # 扫描检查点
├── test_cninfo_full_market.py  # 全市场扫描
├── test_cninfo_classification.py # 分类逻辑
├── test_stock_registry.py      # 股票注册表
├── test_disk_storage_pagination.py # 分页
└── test_release_contract.py    # 发布契约
```

新测试文件遵循 `test_<module_or_feature>.py` 命名，确保 `unittest discover -p "test_*.py"` 能自动发现。

### 4.3 CI 测试矩阵

CI 在 Python 3.10 / 3.11 / 3.12 三个版本上运行测试。本地开发使用任一版本即可，但请注意不要使用仅高版本支持的语法特性。

---

## 5. 代码风格细则

### 5.1 Python

- **Formatter:** ruff format (double quotes, space indent, line-length 100)
- **Import sort:** isort via ruff，`corp_finance_monitor` 作为 first-party
- **Lint 规则:** E / F / I / B / SIM / C4 / UP / RUF
- **忽略项:** E501 (行长度)、B027、RUF001 / RUF002 / RUF003（保留中日韩字符）
- **排除目录:** `.venv` `dist` `.git` `__pycache__` `wheelhouse` `data` `.claude/`

### 5.2 Frontend

- **Formatter:** 无独立 formatter，依赖 ESLint 规则
- **Lint:** ESLint + typescript-eslint
- **TypeScript:** strict mode
- **UI 组件:** `src/components/ui/` 下的 shadcn 组件不做 lint 检查（自动生成）

---

## 6. 常用命令速查

```bash
# === 质量检查 ===
make lint              # Python lint (非变更)
make format-check      # Python 格式检查 (非变更)
make fix               # 自动修复 lint + 格式化 (会写入文件)
make test              # 运行单元测试
make test-quick        # 快速本地测试

# === Review Gate ===
make gate              # Python 全量 gate: lint + format + test
make gate-full         # Python + Frontend 全量 gate
make gate-scheduling   # 针对性 gate

# === 脚本 ===
bash scripts/pre-commit.sh    # 可选：更严格的 staged-file 检查（含前端 lint + tsc）
bash scripts/review-gate.sh   # 等同于 make gate-full

# === Docker ===
docker compose up -d --build  # 本地构建并启动
```

---

## 7. 相关文档索引

| 文档 | 位置 | 说明 |
|------|------|------|
| 架构文档 | `docs/ARCHITECTURE.md` | 项目架构、模块、数据流 |
| 知识库 | `KNOWLEDGE.md` | 关键事实、约定、踩坑点 |
| Branch Protection | `.github/branch-protection.md` | GitHub 仓库保护规则配置指南 |
| CI 配置 | `.github/workflows/ci.yml` | CI 流水线定义 |
| 发布流水线 | `.github/workflows/docker.yml` | Docker 镜像构建 + Release PR |
| 通用开发规范 | `llm-wiki/docs/topic/collaboration/development-standards.md` | 跨项目共享协作规范 |
