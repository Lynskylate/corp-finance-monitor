# corp-finance-monitor Plan

## Goal

Build a single Python repo that discovers and downloads company information updates from multiple sources, with clear abstractions for:

- source adapters
- configuration
- file/blob storage
- metadata/state persistence
- update orchestration

Initial storage target is local disk. The design should allow later replacement with S3 or database-backed storage without changing source implementations.

## Current State

There is already an initial scaffold in this repo:

- `src/core/config.py`
- `src/core/source.py`
- `src/core/storage.py`
- `src/core/model.py`
- `src/core/engine.py`

There are also three working single-purpose scripts outside the repo that should be reused instead of rewritten:

- `/home/lynskylate/cninfo_financial_reports.py`
- `/home/lynskylate/sse_ipo_prospectus.py`
- `/home/lynskylate/hkex_filings.py`

Current gaps:

- no concrete `sources/` implementations
- no `storage/disk.py`
- no CLI entrypoint implementation
- no sample config file
- no tests
- state storage and file storage responsibilities are mixed inside `Engine`
- repo is a plain directory now, not yet a git repository

## Architecture

### 1. Domain Model

Keep two levels of objects:

- `FilingRef`: normalized metadata returned by discovery
- `Filing`: fetched document with bytes and normalized metadata

Add one more metadata object:

- `WatchTarget`: normalized config for one monitored entity

Recommended normalized fields on `FilingRef`:

- `source`
- `source_id`
- `stock_code`
- `stock_name`
- `title`
- `kind`
- `published_at`
- `url`
- `market`
- `language`
- `checksum_hint`
- `raw` for source-specific metadata

### 2. Source Abstraction

`AbstractSource` should stay small:

- `discover(watchlist) -> list[FilingRef]`
- `fetch(ref) -> Filing | None`
- `close()`

Implementation rule:

- source adapters are responsible for HTTP details and source-specific field mapping
- engine is responsible for dedup, scheduling, retry policy at the job level, and storage handoff

Phase-1 sources:

- `cninfo`: A-share periodic reports
- `sse`: IPO prospectus and related listing files
- `hkex`: HK financial filings and prospectuses

### 3. Storage Abstraction

Split storage into two concerns:

- blob/file storage: where PDFs or raw documents live
- metadata/state store: what has been seen, fetched, failed, retried

Do not keep both concerns hidden inside `Engine`.

Recommended interfaces:

- `AbstractStorage`: store/get/delete file content
- `AbstractStateStore`: dedup index, run logs, fetch status

Phase-1 implementations:

- `DiskStorage`
- `SQLiteStateStore`

Disk layout:

```text
data/
  blobs/
    <source>/<stock_code>/<year>/<published_at>_<kind>_<source_id>.pdf
  metadata/
    state.db
```

### 4. Config Abstraction

Use one YAML file as the top-level config, but normalize it into typed config objects.

Top-level sections:

- `engine`
- `storage`
- `state_store`
- `sources`

Recommended config shape:

```yaml
engine:
  run_once: true
  interval_minutes: 360
  concurrency: 2
  fetch_delay_seconds: 0.5

storage:
  backend: disk
  base_dir: ./data

state_store:
  backend: sqlite
  path: ./data/metadata/state.db

sources:
  cninfo:
    enabled: true
    options:
      timeout: 30
    watchlist:
      - stock: "000725"
        org_id: "gssz0000725"
        kinds: [annual, semi, q1, q3]
  sse:
    enabled: true
    watchlist:
      - audit_id: "497"
        kinds: [prospectus]
  hkex:
    enabled: true
    watchlist:
      - stock: "00700"
        kinds: [annual, interim, prospectus]
```

### 5. Engine Responsibilities

The engine should do only orchestration:

1. load config
2. initialize sources
3. initialize storage + state store
4. call `discover`
5. deduplicate via state store
6. call `fetch`
7. persist file via storage
8. persist metadata/run state
9. emit a summary

Recommended CLI commands:

- `cfm run --config config.yaml`
- `cfm discover --source cninfo`
- `cfm fetch --source cninfo --id <source_id>`
- `cfm list --source cninfo --stock 000725`
- `cfm runs`

## Implementation Plan

### Phase 1: Stabilize repo skeleton

- keep `/home/lynskylate/corp-finance-monitor` as repo root
- add `PLAN.md`, `README.md`, and `config.example.yaml`
- clean package layout so imports are consistent
- fix script entrypoint declared in `pyproject.toml`

Exit criteria:

- repo can be installed locally
- config loads
- CLI boots

### Phase 2: Separate storage from state

- add `src/state/base.py`
- add `src/state/sqlite.py`
- implement `src/storage/disk.py`
- remove direct SQLite ownership from `Engine`

Exit criteria:

- engine no longer writes SQL directly except through `StateStore`
- dedup and run log work through abstractions

### Phase 3: Extract reusable source clients

- convert the three standalone scripts into source modules:
  - `src/sources/cninfo.py`
  - `src/sources/sse.py`
  - `src/sources/hkex.py`
- keep their proven HTTP logic, headers, and parsing
- move only reusable internals, not the old CLI wrappers

Exit criteria:

- each source implements `discover` and `fetch`
- each source can run from config watchlist entries

### Phase 4: CLI and operator workflow

- implement `src/cli/main.py`
- add `run`, `discover`, `list`, `runs`
- print clear summaries: discovered, fetched, skipped, failed

Exit criteria:

- one command can perform a full run from config
- operator can inspect stored filings and run history

### Phase 5: Tests

Minimum tests:

- config parsing
- `FilingRef.unique_key`
- disk path generation and dedup
- sqlite state transitions
- source parser tests with recorded fixtures

Exit criteria:

- offline unit tests cover core logic
- live integration tests remain optional/manual

## Key Design Decisions

### Reuse adapters, not whole scripts

The existing standalone scripts already contain the important reverse-engineered request logic. The repo should absorb that logic into source adapters instead of shelling out to scripts.

### Separate file storage from job state

This is the main design correction needed in the current scaffold. Blob persistence and dedup/run metadata are different responsibilities and should be replaceable independently.

### Normalize metadata early

Each source has different field names and document taxonomies. Normalize to `FilingKind` and shared `FilingRef` fields during discovery, not later in storage.

## Immediate Next Step

If this plan is approved, implementation should start with:

1. repo cleanup and `README/config.example.yaml`
2. `DiskStorage` + `SQLiteStateStore`
3. `cninfo` source extraction first

That order gets one end-to-end source working quickly, then the SSE/HKEX adapters can be added on top of the same abstractions.
