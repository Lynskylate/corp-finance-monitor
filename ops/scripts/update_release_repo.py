from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def load_metadata(artifact_dir: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(artifact_dir.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        result[payload["service_name"]] = payload
    if not result:
        raise ValueError(f"no metadata artifacts found in {artifact_dir}")
    return result


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def record_previous_release(stack: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = {
        "released_at": datetime.now(timezone.utc).isoformat(),
        "containers": {
            container["service_ref"]: container["image_digest"]
            for container in stack["containers"]
        },
    }
    if any(not digest.endswith("0" * 64) for digest in snapshot["containers"].values()):
        return [snapshot]
    return []


def update_stacks(release_repo: Path, environment: str, metadata: dict[str, dict[str, Any]]) -> list[Path]:
    changed_paths: list[Path] = []
    matched_services: set[str] = set()
    stack_dir = release_repo / "environments" / environment / "stacks"
    for path in sorted(stack_dir.glob("*.yaml")):
        stack = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(stack, dict):
            continue
        previous_history = stack.get("rollback_history", [])
        previous_release = json.loads(json.dumps(stack))
        changed = False
        for container in stack.get("containers", []):
            service_ref = container.get("service_ref")
            if service_ref not in metadata:
                continue
            matched_services.add(service_ref)
            payload = metadata[service_ref]
            if (
                container.get("image_repository") != payload["image_repository"]
                or container.get("image_digest") != payload["image_digest"]
            ):
                changed = True
                container["image_repository"] = payload["image_repository"]
                container["image_digest"] = payload["image_digest"]
        if changed:
            stack["rollback_history"] = record_previous_release(previous_release) + previous_history
            stack["updated_at"] = datetime.now(timezone.utc).isoformat()
            write_yaml(path, stack)
            changed_paths.append(path)
    unmatched = sorted(set(metadata) - matched_services)
    if unmatched:
        raise ValueError(f"metadata references missing stack entries: {', '.join(unmatched)}")
    return changed_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Update release-config stack digests from build metadata")
    parser.add_argument("--release-repo-path", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args()

    release_repo = Path(args.release_repo_path).resolve()
    metadata = load_metadata(Path(args.artifact_dir).resolve())
    changed = update_stacks(release_repo, args.environment, metadata)
    for path in changed:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
