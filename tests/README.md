# Tests for corp-finance-monitor

Run the standard unit and integration suite with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py" -v
```

Run deployed-stack checks only when a live service is available:

```bash
RUN_DEPLOYED_E2E=1 PYTHONPATH=src python3 -m unittest tests.test_e2e_deployed -v
RUN_DEPLOYED_E2E=1 BASE_URL=https://gtr.tail414c32.ts.net PYTHONPATH=src python3 -m unittest tests.test_e2e_deployed -v
```

## Layout

- `conftest.py` adds `src/` to `sys.path` so tests can import the package without `pip install -e .`.
- `test_cninfo_classification.py` covers filing-kind classification boundaries.
- `test_sqlite_state_concurrency.py` exercises SQLite state-store locking and persistence behavior.
- `test_api_smoke.py` runs the FastAPI app end-to-end against a local in-process `uvicorn` server.
- `test_e2e_deployed.py` checks a live deployed stack and is skipped unless `RUN_DEPLOYED_E2E=1` is set.
- `test_release_contract.py` verifies the new release-contract files and workflow integration.
