# Release Contract

`ops/` is the narrow interface between the project repo and the release-config repo.

## Layout

```text
ops/
|- services/
|  |- corp-finance-monitor-backend.yaml
|  `- corp-finance-monitor-frontend.yaml
`- scripts/
   |- list_services.py
   `- update_release_repo.py
```

## Rules

- Each `services/*.yaml` file declares one buildable image.
- Service contracts only declare:
  - `service_name`
  - `dockerfile`
  - `internal_port`
  - `healthcheck_path`
  - `exposure`
  - `env_profile`
- Runtime secrets are not stored in this repo.
- This repo does not SSH to target servers directly.
- GitHub Actions builds images, captures immutable digests, and opens a PR against the release-config repo.

## Current Services

- `corp-finance-monitor-backend`
  - Dockerfile: `Dockerfile`
  - Internal port: `8190`
- `corp-finance-monitor-frontend`
  - Dockerfile: `frontend/Dockerfile.ci`
  - Internal port: `80`
