from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from practice2.doctor import diagnose
from practice2.gitflow import git

ROOT = Path(__file__).resolve().parents[1]


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.student = self.root / "student"
        git(self.root, "clone", str(self.remote), str(self.student))
        git(self.student, "config", "user.name", "Doctor test")
        git(self.student, "config", "user.email", "doctor@example.invalid")
        git(self.student, "config", "commit.gpgsign", "false")
        (self.student / "README.md").write_text("fixture")
        git(self.student, "add", "README.md")
        git(self.student, "commit", "-m", "fixture")
        git(self.student, "push", "origin", "main")
        (self.student / "config.json").write_text(json.dumps({"repository": str(self.remote)}))

    def tearDown(self):
        self.tmp.cleanup()

    def diagnose(self, *, offline=False, login=0, missing=False, sandbox=0):
        original_run = subprocess.run
        original_which = shutil.which

        def run(args, **kwargs):
            if args[0] == "fake-codex":
                return subprocess.CompletedProcess(args, login if "login" in args else sandbox, "", "")
            return original_run(args, **kwargs)

        def which(name):
            return (None if missing else "fake-codex") if name.startswith("codex") else original_which(name)

        with patch("practice2.doctor.shutil.which", side_effect=which), patch("practice2.doctor.subprocess.run", side_effect=run):
            return diagnose(self.student, ROOT / "log_pairs", offline)

    def test_ready_probe_does_not_create_a_remote_branch_or_change_files(self):
        before = git(self.remote, "show-ref").stdout
        status = git(self.student, "status", "--porcelain").stdout
        result = self.diagnose()
        self.assertTrue(result["ready"], result)
        self.assertEqual(git(self.remote, "show-ref").stdout, before)
        self.assertEqual(git(self.student, "status", "--porcelain").stdout, status)

    def test_missing_or_logged_out_codex_is_actionable(self):
        for kwargs in ({"missing": True}, {"login": 1}):
            result = self.diagnose(**kwargs)
            self.assertFalse(result["ready"])
            self.assertTrue(next(c for c in result["checks"] if c["name"] == "Codex 로그인")["fix"])

    def test_offline_does_not_claim_submission_ready(self):
        result = self.diagnose(offline=True)
        self.assertTrue(result["local_ready"])
        self.assertFalse(result["ready"])
        self.assertIn("SKIP", [c["status"] for c in result["checks"]])

    def test_login_alone_is_not_ready_when_sandbox_cannot_execute(self):
        result = self.diagnose(sandbox=1)
        self.assertFalse(result["ready"])
        checks = {c["name"]: c for c in result["checks"]}
        self.assertEqual(checks["Codex 로그인"]["status"], "PASS")
        self.assertEqual(checks["Codex 실행 환경"]["status"], "FAIL")

    def test_failed_remote_is_reported_without_traceback(self):
        self.remote.rename(self.root / "unavailable.git")
        result = self.diagnose()
        self.assertFalse(result["ready"])
        self.assertEqual(next(c for c in result["checks"] if c["name"] == "GitHub 쓰기 연결")["status"], "FAIL")

    def test_wrong_branch_and_push_url_cannot_pass(self):
        (self.student / "config.json").write_text(json.dumps({"repository": str(self.remote), "participant": "p01"}))
        self.assertFalse(self.diagnose()["ready"])
        (self.student / "config.json").write_text(json.dumps({"repository": str(self.remote)}))
        git(self.student, "remote", "set-url", "--push", "origin", str(self.root / "other.git"))
        self.assertFalse(self.diagnose()["ready"])


if __name__ == "__main__":
    unittest.main()
