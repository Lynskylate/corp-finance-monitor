# corp-finance-monitor frontend

Vite + React + TypeScript + Tailwind CSS v4 + shadcn/ui-style foundations.

## Purpose

This frontend baseline covers two core workflows:

- latest updates sorted by time descending
- lookup of filing-related information by stock code, also sorted by newest first

Current routes:

- `/` — overview with latest updates and stock-code lookup
- `/filings/:source/:sourceId` — filing detail shell

## Commands

```bash
npm install
npm run dev
npm run build
npm run lint
npm run check
```

## API contract used in this baseline

- `GET /api/filings`
- `GET /api/filings/{source}/{source_id}`

The frontend defensively re-sorts filing lists by `published_at` descending.

## Structure

```text
src/
  app/          providers, shell, router
  components/   reusable UI primitives
  features/     filing list + code lookup feature modules
  lib/          API client and formatting helpers
  routes/       route-level pages
```
