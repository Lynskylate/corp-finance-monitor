from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
VALID_EXPOSURES = {"none", "tailscale", "envoy"}


def load_service(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain an object")
    required = [
        "apiVersion",
        "kind",
        "service_name",
        "dockerfile",
        "internal_port",
        "healthcheck_path",
        "exposure",
        "env_profile",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{path} missing keys: {missing}")
    if data["apiVersion"] != "deploy.lynskylate/v1alpha1":
        raise ValueError(f"{path} apiVersion must be deploy.lynskylate/v1alpha1")
    if data["kind"] != "ProjectService":
        raise ValueError(f"{path} kind must be ProjectService")
    if data["exposure"] not in VALID_EXPOSURES:
        raise ValueError(f"{path} exposure must be one of {sorted(VALID_EXPOSURES)}")
    dockerfile = ROOT / data["dockerfile"]
    if not dockerfile.exists():
        raise ValueError(f"{path} references missing dockerfile: {dockerfile}")
    context = dockerfile.parent.relative_to(ROOT)
    data["context"] = "." if str(context) == "." else str(context)
    tencent_registry = os.environ.get("TENCENT_CCR_REGISTRY") or "ccr.ccs.tencentyun.com"
    tencent_prefix = os.environ.get("TENCENT_CCR_PREFIX") or "fin-monitor"
    data["image_repository"] = f"{tencent_registry}/{tencent_prefix}/{data['service_name']}"
    data["build_args"] = (
        "VITE_API_BASE_URL=/api" if data["service_name"].endswith("-frontend") else ""
    )
    data["contract_path"] = str(path.relative_to(ROOT))
    return data


def build_matrix() -> dict[str, list[dict[str, Any]]]:
    services_dir = ROOT / "ops" / "services"
    services = [load_service(path) for path in sorted(services_dir.glob("*.yaml"))]
    return {"include": services}


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit GitHub Actions matrix for project services")
    parser.add_argument("--github-output", help="Path to the GitHub Actions output file")
    args = parser.parse_args()

    matrix = build_matrix()
    payload = json.dumps(matrix, separators=(",", ":"))
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as handle:
            handle.write(f"matrix={payload}\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
