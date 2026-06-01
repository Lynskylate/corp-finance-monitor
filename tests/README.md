# Tests for corp-finance-monitor

Run with the standard library `unittest` (no extra deps required):

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py" -v
```

Or one file at a time:

```bash
PYTHONPATH=src python3 -m unittest tests.test_cninfo_classification -v
PYTHONPATH=src python3 -m unittest tests.test_sqlite_state_concurrency -v
PYTHONPATH=src python3 -m unittest tests.test_api_smoke -v
```

## Layout

- `conftest.py` — adds `src/` to `sys.path` so tests can import the package
  without `pip install -e .`.
- `test_cninfo_classification.py` — boundary tests for `_detect_kind` /
  `CATEGORY_MAP` in `src/corp_finance_monitor/sources/cninfo.py`.
  Covers ANNUAL, ANNUAL_SUMMARY (→OTHER), SEMI, Q1, Q3, and OTHER buckets.
- `test_sqlite_state_concurrency.py` — multi-threaded tests of
  `SQLiteStateStore` (record_filing / record_run / create_subscription,
  has_filing, last_successful_run_start). Verifies the `check_same_thread=False`
  + `RLock` contract empirically.
- `test_api_smoke.py` — exercises the real `ThreadingHTTPServer` end-to-end:
  `/healthz`, `/api/filings`, `/api/filings/<source>/<source_id>`,
  `/api/runs`, `/api/subscriptions` (POST/GET), `/api/sync`
  (200 + 409 under lock contention + end-to-end fetch via a `FakeSource`).

## Dependencies

- Python ≥ 3.10
- `requests`, `pyyaml` (project deps)
- Standard library only: `unittest`, `threading`, `concurrent.futures`,
  `urllib`, `socket`, `tempfile`, `shutil`

Pytest is not required, but if available the same files are discoverable
via `pytest tests/`.
