from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

import yaml

from ops.scripts import list_services, update_release_repo

REPO_ROOT = Path(__file__).resolve().parent.parent
OPS = REPO_ROOT / "ops"


class TestProjectServiceContracts(unittest.TestCase):
    REQUIRED_KEYS: ClassVar[set[str]] = {
        "apiVersion",
        "kind",
        "service_name",
        "dockerfile",
        "internal_port",
        "healthcheck_path",
        "exposure",
        "env_profile",
    }

    def test_three_service_contracts_exist(self):
        contracts = sorted((OPS / "services").glob("*.yaml"))
        self.assertEqual(
            [path.name for path in contracts],
            [
                "corp-finance-monitor-backend.yaml",
                "corp-finance-monitor-frontend.yaml",
                "corp-finance-monitor-scheduler.yaml",
            ],
        )

    def test_contracts_match_minimal_schema(self):
        for path in sorted((OPS / "services").glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(data["apiVersion"], "deploy.lynskylate/v1alpha1")
            self.assertEqual(data["kind"], "ProjectService")
            self.assertEqual(set(data.keys()), self.REQUIRED_KEYS)
            self.assertTrue((REPO_ROOT / data["dockerfile"]).exists())
            self.assertIsInstance(data["internal_port"], int)


class TestReleaseWorkflow(unittest.TestCase):
    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docker.yml"

    def setUp(self):
        self.text = self.WORKFLOW.read_text(encoding="utf-8")

    def test_uses_release_contract_scripts(self):
        self.assertIn("ops/scripts/list_services.py", self.text)
        self.assertIn("ops/scripts/update_release_repo.py", self.text)

    def test_requires_release_repo_token(self):
        self.assertIn("RELEASE_CONFIG_REPO_TOKEN", self.text)
        self.assertIn("RELEASE_CONFIG_REPOSITORY", self.text)

    def test_uploads_release_metadata(self):
        self.assertIn("release-metadata-", self.text)
        self.assertIn("release-image-", self.text)
        self.assertIn("steps.build.outputs.digest", self.text)
        self.assertIn("source_run_id", self.text)

    def test_auto_merges_release_pr(self):
        self.assertIn("Auto-merge release PR", self.text)
        self.assertIn("gh pr merge", self.text)

    def test_service_discovery_matches_release_contract(self):
        matrix = list_services.build_matrix()
        self.assertEqual(
            [item["service_name"] for item in matrix["include"]],
            [
                "corp-finance-monitor-backend",
                "corp-finance-monitor-frontend",
                "corp-finance-monitor-scheduler",
            ],
        )

    def test_release_repo_updates_require_matching_stack_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_path = root / "environments/prod/stacks/corp-finance-monitor.yaml"
            stack_path.parent.mkdir(parents=True, exist_ok=True)
            stack_path.write_text(
                yaml.safe_dump(
                    {
                        "apiVersion": "deploy.lynskylate/v1alpha1",
                        "kind": "DeploymentStack",
                        "service_name": "corp-finance-monitor",
                        "target_group": "gtr-core",
                        "runtime": {"type": "rootless-podman", "network": {"name": "cfm"}},
                        "service_user": "svc-corp-finance-monitor",
                        "exposure": "tailscale",
                        "healthcheck": {"url": "http://127.0.0.1:8190/healthz"},
                        "containers": [],
                        "rollback_history": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing stack entries"):
                update_release_repo.update_stacks(
                    root,
                    "prod",
                    {
                        "corp-finance-monitor-backend": {
                            "service_name": "corp-finance-monitor-backend",
                            "image_repository": "ghcr.io/lynskylate/corp-finance-monitor-backend",
                            "image_digest": "sha256:1234",
                        }
                    },
                )

    def test_release_repo_updates_artifact_source_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_path = root / "environments/prod/stacks/corp-finance-monitor.yaml"
            stack_path.parent.mkdir(parents=True, exist_ok=True)
            stack_path.write_text(
                yaml.safe_dump(
                    {
                        "apiVersion": "deploy.lynskylate/v1alpha1",
                        "kind": "DeploymentStack",
                        "service_name": "corp-finance-monitor",
                        "target_group": "gtr-core",
                        "runtime": {"type": "rootless-podman", "network": {"name": "cfm"}},
                        "service_user": "svc-corp-finance-monitor",
                        "exposure": "tailscale",
                        "healthcheck": {"url": "http://127.0.0.1:8190/healthz"},
                        "containers": [
                            {
                                "service_ref": "corp-finance-monitor-backend",
                                "container_name": "corp-finance-monitor-backend",
                                "image_repository": "ghcr.io/lynskylate/corp-finance-monitor-backend",
                                "image_digest": "sha256:old",
                                "env_profile": "corp-finance-monitor-backend",
                                "container_port": 8190,
                            }
                        ],
                        "rollback_history": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            update_release_repo.update_stacks(
                root,
                "prod",
                {
                    "corp-finance-monitor-backend": {
                        "service_name": "corp-finance-monitor-backend",
                        "image_repository": "ghcr.io/lynskylate/corp-finance-monitor-backend",
                        "image_digest": "sha256:new",
                        "image_tag": "commit-sha",
                        "image_artifact": "release-image-corp-finance-monitor-backend",
                        "source_repository": "Lynskylate/corp-finance-monitor",
                        "source_run_id": 26771237800,
                    }
                },
            )

            stack = yaml.safe_load(stack_path.read_text(encoding="utf-8"))
            self.assertEqual(stack["artifact_source_repository"], "Lynskylate/corp-finance-monitor")
            self.assertEqual(stack["artifact_source_run_id"], 26771237800)
            self.assertEqual(
                stack["containers"][0]["image_artifact"],
                "release-image-corp-finance-monitor-backend",
            )


class TestLegacyDeployRemoved(unittest.TestCase):
    def test_deploy_tree_removed(self):
        self.assertFalse((REPO_ROOT / "deploy").exists())
        self.assertFalse((REPO_ROOT / "docs" / "DEPLOY_VERIFICATION.md").exists())
        self.assertFalse((REPO_ROOT / "docs" / "ROLLBACK.md").exists())
        self.assertFalse((REPO_ROOT / "scripts" / "verify_deploy.sh").exists())


if __name__ == "__main__":
    unittest.main()
