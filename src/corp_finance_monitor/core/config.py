from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml


@dataclass
class SourceConfig:
    name: str
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)
    watchlist: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StorageConfig:
    backend: str = "disk"
    base_dir: str = ""
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateStoreConfig:
    backend: str = "sqlite"
    path: str = ""
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineConfig:
    interval_minutes: int = 360
    run_once: bool = True
    concurrency: int = 1
    fetch_delay_seconds: float = 0.5


@dataclass
class APIConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    enabled: bool = True


@dataclass
class Config:
    sources: Dict[str, SourceConfig] = field(default_factory=dict)
    storage: StorageConfig = field(default_factory=StorageConfig)
    state_store: StateStoreConfig = field(default_factory=StateStoreConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    api: APIConfig = field(default_factory=APIConfig)

    @classmethod
    def from_file(cls, path: str) -> "Config":
        path = os.path.abspath(path)
        base_dir = os.path.dirname(path)
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        cfg = cls()
        cfg.engine = EngineConfig(**(raw.get("engine", {})))

        storage_raw = raw.get("storage", {})
        cfg.storage = StorageConfig(
            backend=storage_raw.get("backend", "disk"),
            base_dir=_resolve_path(base_dir, storage_raw.get("base_dir", "")),
            options=storage_raw.get("options", {}),
        )

        state_store_raw = raw.get("state_store", {})
        default_state_path = os.path.join(
            cfg.storage.base_dir or "./data",
            ".cfm_state",
            "state.db",
        )
        cfg.state_store = StateStoreConfig(
            backend=state_store_raw.get("backend", "sqlite"),
            path=_resolve_path(base_dir, state_store_raw.get("path", default_state_path)),
            options=state_store_raw.get("options", {}),
        )

        cfg.api = APIConfig(**(raw.get("api", {})))

        sources_raw = raw.get("sources", {})
        for name, s_raw in sources_raw.items():
            cfg.sources[name] = SourceConfig(
                name=name,
                enabled=s_raw.get("enabled", True),
                options=s_raw.get("options", {}),
                watchlist=s_raw.get("watchlist", []),
            )

        return cfg

    @classmethod
    def default(cls) -> "Config":
        return cls(
            storage=StorageConfig(backend="disk", base_dir="./data"),
            state_store=StateStoreConfig(
                backend="sqlite",
                path="./data/.cfm_state/state.db",
            ),
            engine=EngineConfig(run_once=True),
            api=APIConfig(),
            sources={
                "cninfo": SourceConfig(
                    name="cninfo",
                    watchlist=[
                        {"stock": "000725", "org_id": "gssz0000725",
                         "kinds": ["annual", "semi", "q1", "q3"]},
                    ],
                ),
            },
        )


def _resolve_path(config_dir: str, value: str) -> str:
    if not value:
        return value
    if os.path.isabs(value):
        return value
    return os.path.abspath(os.path.join(config_dir, value))
