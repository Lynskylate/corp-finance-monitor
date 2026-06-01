"""
Tests for deploy artifacts (Phase 2 verification).

Catches regressions in the deploy/ tree and ensures that the docs
and scripts stay self-consistent with the code we ship.

These tests do NOT require systemd, a running API, or root. They
read files from the repo and check structural invariants.
"""
import os
import re
import stat
import unittest
from pathlib import Path

from tests.conftest import SRC  # noqa: F401  (forces src/ onto sys.path)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "deploy"
DOCS = REPO_ROOT / "docs"
SCRIPTS = REPO_ROOT / "scripts"


class TestDeployFilesPresent(unittest.TestCase):
    """All 7 required deploy/ files must exist (Phase 1B acceptance)."""

    REQUIRED = [
        "deploy/deploy.sh",
        "deploy/smoke_test.sh",
        "deploy/config.yaml.example",
        "deploy/VARIABLES.md",
        "deploy/systemd/cfm-api.service.in",
        "deploy/systemd/cfm-sync.service.in",
        "deploy/systemd/cfm-sync.timer.in",
    ]

    def test_all_required_files_present(self):
        missing = [p for p in self.REQUIRED if not (REPO_ROOT / p).exists()]
        self.assertEqual(missing, [], f"missing deploy files: {missing}")


class TestPhase2DeliverablesPresent(unittest.TestCase):
    """Phase 2 must add docs/ and scripts/."""

    REQUIRED = [
        "docs/DEPLOY_VERIFICATION.md",
        "docs/ROLLBACK.md",
        "scripts/verify_deploy.sh",
    ]

    def test_all_phase2_files_present(self):
        missing = [p for p in self.REQUIRED if not (REPO_ROOT / p).exists()]
        self.assertEqual(missing, [], f"missing Phase 2 files: {missing}")


class TestVerifyDeployScript(unittest.TestCase):
    """scripts/verify_deploy.sh must be syntactically valid and executable."""

    SCRIPT = SCRIPTS / "verify_deploy.sh"

    def setUp(self):
        if not self.SCRIPT.exists():
            self.skipTest(f"{self.SCRIPT} not present")

    def test_executable_bit(self):
        mode = self.SCRIPT.stat().st_mode
        self.assertTrue(
            mode & stat.S_IXUSR,
            "verify_deploy.sh must be executable (chmod +x)",
        )

    def test_bash_syntax(self):
        import subprocess
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode, 0,
            f"bash -n failed: {result.stderr}",
        )

    def test_references_cfm_binary(self):
        text = self.SCRIPT.read_text()
        self.assertIn("cfm", text, "verify_deploy.sh should reference the cfm binary")
        self.assertIn(".venv/bin/cfm", text, "should default to venv cfm")

    def test_uses_curl(self):
        text = self.SCRIPT.read_text()
        self.assertIn("curl", text)
        self.assertIn("/healthz", text)
        self.assertIn("/api/filings", text)
        self.assertIn("/api/subscriptions", text)

    def test_uses_systemctl(self):
        text = self.SCRIPT.read_text()
        self.assertIn("systemctl", text)
        self.assertIn("is-active", text)

    def test_exits_nonzero_on_failure(self):
        text = self.SCRIPT.read_text()
        # set -u is on, but NOT set -e (we want to keep going on failures)
        self.assertIn("set -", text)
        # explicit exit 1 on failure path
        self.assertRegex(text, r"exit\s+1")


class TestDeployScript(unittest.TestCase):
    """deploy/deploy.sh must be syntactically valid and use cfm (not main.py)."""

    SCRIPT = DEPLOY / "deploy.sh"

    def setUp(self):
        if not self.SCRIPT.exists():
            self.skipTest(f"{self.SCRIPT} not present")

    def test_bash_syntax(self):
        import subprocess
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_main_py_reference(self):
        # main.py was removed by #16. The deploy script must not invoke it.
        text = self.SCRIPT.read_text()
        self.assertNotIn(
            "python3 main.py", text,
            "deploy.sh must not invoke the removed main.py",
        )
        self.assertNotIn(
            "python main.py", text,
            "deploy.sh must not invoke the removed main.py",
        )

    def test_uses_cfm_binary(self):
        text = self.SCRIPT.read_text()
        self.assertIn("cfm", text, "deploy.sh should install/run cfm binary")


class TestSystemdUnits(unittest.TestCase):
    """systemd .in templates must use cfm and have correct service types."""

    API = DEPLOY / "systemd" / "cfm-api.service.in"
    SYNC = DEPLOY / "systemd" / "cfm-sync.service.in"
    TIMER = DEPLOY / "systemd" / "cfm-sync.timer.in"

    def setUp(self):
        for p in (self.API, self.SYNC, self.TIMER):
            if not p.exists():
                self.skipTest(f"{p} not present")

    def test_api_service_uses_cfm(self):
        text = self.API.read_text()
        self.assertIn("Type=simple", text)
        self.assertIn("Restart=always", text)
        self.assertIn("cfm serve", text, "cfm-api must exec `cfm serve`")
        self.assertNotIn("python3 main.py", text)
        self.assertNotIn("python main.py", text)

    def test_sync_service_is_oneshot(self):
        text = self.SYNC.read_text()
        self.assertIn("Type=oneshot", text)
        self.assertIn("cfm sync", text, "cfm-sync must exec `cfm sync`")
        self.assertNotIn("python3 main.py", text)

    def test_timer_daily_with_persistent(self):
        text = self.TIMER.read_text()
        self.assertIn("OnCalendar=", text)
        self.assertIn("Persistent=true", text)


class TestVariablesDoc(unittest.TestCase):
    """VARIABLES.md docs must agree with the actual code defaults."""

    DOC = DEPLOY / "VARIABLES.md"

    def setUp(self):
        if not self.DOC.exists():
            self.skipTest(f"{self.DOC} not present")

    def test_install_method_default_is_uv(self):
        # Look for the row in the Install Method table
        text = self.DOC.read_text()
        # Match the install_method row; second column should be uv, not pip
        m = re.search(
            r"\|\s*`?install_method`?\s*\|\s*`?(\w+)`?\s*\|",
            text,
        )
        self.assertIsNotNone(m, "install_method row not found in VARIABLES.md")
        self.assertEqual(
            m.group(1), "uv",
            f"VARIABLES.md says install_method default is '{m.group(1)}', "
            f"but code (deploy.sh, ansible/vars) defaults to 'uv'",
        )

    def test_listen_port_default(self):
        text = self.DOC.read_text()
        m = re.search(r"\|\s*`?listen_port`?\s*\|\s*`?(\d+)`?\s*\|", text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "8080")


class TestDocsCrossReference(unittest.TestCase):
    """Docs should reference each other and the actual file paths."""

    def test_verification_doc_references_rollback(self):
        text = (DOCS / "DEPLOY_VERIFICATION.md").read_text()
        self.assertIn("ROLLBACK.md", text)

    def test_rollback_doc_references_verification(self):
        text = (DOCS / "ROLLBACK.md").read_text()
        self.assertIn("DEPLOY_VERIFICATION.md", text)

    def test_verification_doc_references_verify_script(self):
        text = (DOCS / "DEPLOY_VERIFICATION.md").read_text()
        self.assertIn("scripts/verify_deploy.sh", text)


class TestConfigExample(unittest.TestCase):
    """deploy/config.yaml.example must be loadable YAML with required sections."""

    CFG = DEPLOY / "config.yaml.example"

    def setUp(self):
        if not self.CFG.exists():
            self.skipTest(f"{self.CFG} not present")

    def test_yaml_loads(self):
        import yaml
        cfg = yaml.safe_load(self.CFG.read_text())
        self.assertIsInstance(cfg, dict)
        for section in ("engine", "storage", "state_store", "api", "sources"):
            self.assertIn(section, cfg, f"missing section: {section}")

    def test_storage_backend_disk(self):
        import yaml
        cfg = yaml.safe_load(self.CFG.read_text())
        self.assertEqual(cfg["storage"]["backend"], "disk")

    def test_state_store_backend_sqlite(self):
        import yaml
        cfg = yaml.safe_load(self.CFG.read_text())
        self.assertEqual(cfg["state_store"]["backend"], "sqlite")


if __name__ == "__main__":
    unittest.main()
