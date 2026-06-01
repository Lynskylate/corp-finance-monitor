# Deployment Variables

All variables can be overridden via `--extra-vars` when running ansible-playbook.

## Paths

| Variable       | Default                                                    | Description          |
|----------------|------------------------------------------------------------|----------------------|
| `repo_path`    | `/home/lynskylate/corp-finance-monitor`                    | Project code root    |
| `venv_path`    | `{{ repo_path }}/.venv`                                    | Virtualenv (unused when install_method=uv) |
| `data_dir`     | `{{ repo_path }}/data`                                     | Filing storage root  |
| `config_path`  | `{{ repo_path }}/config.yaml`                              | Config file          |
| `dist_path`    | `{{ repo_path }}/dist`                                     | Built .whl / .tar.gz |
| `log_dir`      | `/var/log/cfm`                                             | Log output directory |

## API Service

| Variable       | Default       | Description                    |
|----------------|---------------|--------------------------------|
| `listen_host`  | `127.0.0.1`   | API bind address               |
| `listen_port`  | `8190`        | API bind port                  |
| `service_name` | `cfm-api`     | systemd service unit name      |

## Sync Timer

| Variable               | Default    | Description                       |
|------------------------|------------|-----------------------------------|
| `sync_service_name`    | `cfm-sync` | systemd oneshot unit name         |
| `timer_name`           | `cfm-sync` | systemd timer unit name           |

## Install Method

| Variable          | Default | Description                                      |
|-------------------|---------|--------------------------------------------------|
| `install_method`  | `uv`    | `uv` (default) or `pip` (fallback, local .whl)    |

## OS User

| Variable     | Default | Description                |
|--------------|---------|----------------------------|
| `cfm_user`   | `cfm`   | System user for the daemon |
| `cfm_group`  | `cfm`   | System group for the daemon|
