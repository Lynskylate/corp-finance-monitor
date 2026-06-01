# corp-finance-monitor frontend

Vite + React 19 + TypeScript + Tailwind CSS v4 + shadcn/ui-style primitives.

## Purpose

企业公告更新流的前端操作台，覆盖两条核心路径：

- **最新更新流** — 按发布时间倒序浏览所有公告，支持来源/类型过滤和分页
- **按代码查询** — 输入股票代码定向检索关联公告

## Tech Stack

| Layer | Choice | Version |
|---|---|---|
| Build | Vite | 8.x |
| Framework | React | 19.x |
| Type Check | TypeScript | 6.x |
| Styling | Tailwind CSS | 4.x (`@tailwindcss/vite` plugin) |
| UI Primitives | shadcn/ui (nova style) | manual copy (`components.json`) |
| Data Fetching | TanStack React Query | 5.x |
| Routing | React Router | 7.x |
| Icons | Lucide React | 1.x |

## Quick Start

```bash
# Install dependencies
npm install

# Development server (port 5173 by default)
npm run dev

# Production build
npm run build

# Lint
npm run lint

# Full check (lint + build)
npm run check
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `""` (same origin) | Backend API base URL. Set only when the API runs on a different host/port (e.g. `http://localhost:8080`). |

Usage:

```bash
# API on same origin (default, e.g. behind a reverse proxy)
npm run dev

# API on a different port
VITE_API_BASE_URL=http://localhost:8080 npm run dev
```

The variable is consumed in `src/lib/api-client.ts`:

```ts
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
```

## Build Artifact

```bash
npm run build
# Output: frontend/dist/
#   index.html
#   assets/index-*.css
#   assets/index-*.js
```

Serve the `dist/` directory with any static file server. For preview:

```bash
npm run preview
```

## Project Structure

```text
frontend/
├── components.json          shadcn/ui config (nova style, aliases)
├── vite.config.ts           Vite + React + Tailwind plugin + @ alias
├── tsconfig.app.json        TS config with @/* path mapping
├── eslint.config.js         ESLint flat config (ts, react-hooks, react-refresh)
├── index.html               Entry HTML
├── public/                  Static assets
└── src/
    ├── main.tsx             App bootstrap (StrictMode + providers + router)
    ├── index.css            Tailwind import + global styles + grid background
    ├── app/
    │   ├── providers.tsx    QueryClientProvider (30s staleTime, 1 retry)
    │   ├── router.tsx       BrowserRouter routes
    │   └── shell.tsx        App shell (header + nav + outlet)
    ├── components/ui/       shadcn/ui-style primitives
    │   ├── badge.tsx
    │   ├── button.tsx       CVA variants: primary, secondary, ghost
    │   ├── card.tsx
    │   ├── input.tsx
    │   ├── separator.tsx
    │   └── skeleton.tsx
    ├── features/
    │   ├── filings/
    │   │   ├── api.ts           listFilings, getFilingDetail
    │   │   ├── constants.ts     SOURCE_OPTIONS, KIND_OPTIONS
    │   │   ├── types.ts         FilingItem, FilingListResponse, FilingDetailResponse
    │   │   └── components/
    │   │       ├── filing-table.tsx        Data table (code, title, kind, time, actions)
    │   │       └── latest-updates-panel.tsx  Filter bar + pagination + table
    │   └── lookup/
    │       └── components/
    │           └── code-search-panel.tsx   Stock code search form + results
    ├── lib/
    │   ├── api-client.ts    fetchJson helper with VITE_API_BASE_URL
    │   ├── format.ts        formatDateTime, formatRelativeTime, formatKind
    │   └── utils.ts         cn() (clsx + tailwind-merge)
    ├── hooks/               (placeholder for custom hooks)
    └── routes/
        ├── home-page.tsx         "/" — overview + latest updates + code lookup
        ├── filing-detail-page.tsx "/filings/:source/:sourceId" — detail view
        └── not-found-page.tsx    "/*" — 404 fallback
```

## Routes

| Path | Component | Description |
|---|---|---|
| `/` | `HomePage` | Overview: stats cards + latest updates panel + code search panel |
| `/filings/:source/:sourceId` | `FilingDetailPage` | Single filing detail with metadata and link to original |
| `/*` | `NotFoundPage` | 404 page with link back to home |

## API Contract

All endpoints are on the backend; the frontend only consumes them.

### `GET /api/filings`

Query parameters:

| Param | Type | Description |
|---|---|---|
| `limit` | int | Page size (default 50) |
| `offset` | int | Skip count (default 0) |
| `stock_code` | string | Filter by stock code |
| `source` | string | Filter by source: `sse`, `cninfo`, `hkex` |
| `kind` | string | Filter by filing kind: `annual`, `semi`, `q1`, `q3`, `interim`, `prospectus`, `quarterly`, `esg`, `other` |
| `since` | string | Filter by date (ISO format) |

Response:

```json
{
  "items": [FilingItem, ...],
  "total": 123,
  "limit": 20,
  "offset": 0
}
```

### `GET /api/filings/:source/:source_id`

Response:

```json
{
  "filing": FilingItem,
  "stored_path": "/path/to/local/file" | null
}
```

The frontend defensively re-sorts filing lists by `published_at` descending via `sortFilingsByNewest()` in `api.ts`.

## Interaction States

Every data view handles these states:

| State | Where | How |
|---|---|---|
| **Loading** | Latest updates panel | 3 skeleton rows (`<Skeleton>`) |
| **Loading** | Code search results | 2 skeleton rows |
| **Loading** | Filing detail | Skeleton block + bar |
| **Empty (no data)** | Latest updates table | Dashed border box: "当前还没有可展示的更新记录。" |
| **Empty (filtered)** | Latest updates table (with filters active) | Dashed border box: "没有符合过滤条件的更新记录。" |
| **Empty (no search yet)** | Code search results | Dashed border box: "输入代码后即可查看该标的的相关更新。" |
| **Empty (no results)** | Code search results | Dashed border box: "该代码当前没有查到匹配记录…" |
| **Validation error** | Code search input | Red inline message below input (empty or invalid format) |
| **Query error** | Code search results | Red card: "查询失败" with error message and retry hint |
| **Not found (404)** | Filing detail | Red card: "公告不存在" with source/sourceId shown |
| **API error** | Filing detail | Amber card: "加载失败" with error message and retry hint |
| **Missing params** | Filing detail (no source/sourceId) | Dashed border box: "缺少路径参数" with link to home |
| **404 route** | Unknown paths | `NotFoundPage` with "页面不存在" message and link back to home |

## Acceptance Checklist

- [x] `npm install` completes without errors
- [x] `npm run lint` passes (ESLint flat config)
- [x] `npm run build` passes (tsc + vite build)
- [x] `npm run check` passes (lint + build combined)
- [x] `npm run dev` starts Vite dev server on port 5173
- [x] `@/` path alias works in both TS and Vite
- [x] Tailwind v4 via `@tailwindcss/vite` plugin — no `tailwind.config.*` file needed
- [x] shadcn `components.json` aliases match actual `src/` layout
- [x] Button variants: `primary`, `secondary`, `ghost` (no `outline` — custom design system)
- [x] Source filter values match backend: `sse`, `cninfo`, `hkex`
- [x] Filing list sorted by `published_at` descending (frontend defensive sort)
- [x] All components use consistent import style (`@/` aliases)
- [x] Loading / empty / error / not-found / validation states handled for all views
- [x] Code search validates input (empty + format) before submitting
- [x] API errors surfaced as visible UI (red/amber cards) instead of silent failures
- [x] `ApiError` class distinguishes 404 from other HTTP errors
- [x] Filing detail handles missing params, 404, and network errors separately
- [x] `VITE_API_BASE_URL` env var documented and functional
- [x] Build output in `frontend/dist/` (<400 KB JS gzipped)

## Known Limitations & Future Work

- **No global error boundary** — individual views handle errors, but no React error boundary catches render crashes
- **No global loading indicator** — each panel has its own skeleton state
- **Client-side pagination only** — pagination controls are wired but rely on server-side `offset/limit`
- **No unit tests** — frontend has no test framework configured yet
- **Accessibility** — no explicit ARIA labels on filter pills; keyboard navigation works via native `<button>`
