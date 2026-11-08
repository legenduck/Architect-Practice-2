"""개인 브랜치 제출과 중앙 재계산. 임시 로컬 저장소만 사용한다."""

from pathlib import Path
import tempfile
import unittest

from practice2.data import load_study
from practice2.gitflow import enroll, git, push_metric
from tools.collect_metrics import collect
from test_metrics import fixture


class GitFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.teacher = self.root / "teacher"
        git(self.root, "clone", str(self.remote), str(self.teacher))
        self.identity(self.teacher)
        (self.teacher / ".gitignore").write_text("config.json\noutput/\n")
        (self.teacher / "data").mkdir()
        fixture(self.teacher / "data")
        git(self.teacher, "add", ".")
        git(self.teacher, "commit", "-m", "Test fixture")
        git(self.teacher, "push", "origin", "main")
        self.student = self.root / "student"
        git(self.root, "clone", str(self.remote), str(self.student))
        self.identity(self.student)
        self.cfg = {"repository": str(self.remote), "participant": "p01"}
        self.payload = {
            "participant": "p01",
            "dataset_sha256": load_study(self.teacher / "data").fingerprint,
            "metric": {
                "name": "Time",
                "purpose": "Test",
                "expression": "elapsed_seconds",
                "aggregation": "mean",
                "unit": "s",
                "interpretation": "Test",
            },
            "results": [{"value": 9999}],
        }

    def identity(self, folder):
        git(folder, "config", "user.name", "Test fixture")
        git(folder, "config", "user.email", "fixture@example.invalid")
        git(folder, "config", "commit.gpgsign", "false")

    def tearDown(self):
        self.tmp.cleanup()

    def test_main_and_unrelated_staged_changes_cannot_be_submitted(self):
        with self.assertRaises(ValueError):
            push_metric(self.student, self.cfg, self.payload)
        enroll(self.student, self.cfg, "p01")
        (self.student / "notes.txt").write_text("unrelated")
        git(self.student, "add", "notes.txt")
        with self.assertRaises(ValueError):
            push_metric(self.student, self.cfg, self.payload)

    def test_submit_only_metric_and_central_recomputes_values(self):
        self.assertEqual(enroll(self.student, self.cfg, "P01"), "students/p01")
        (self.student / "notes.txt").write_text("do not publish")
        push_metric(self.student, self.cfg, self.payload)
        files = git(self.remote, "ls-tree", "-r", "--name-only", "students/p01").stdout
        self.assertIn("submissions/metric.json", files)
        self.assertNotIn("notes.txt", files)
        self.assertNotIn("config.json", files)
        records = collect(self.teacher, self.teacher / "output")
        self.assertEqual(records[0]["status"], "계산 확인")
        self.assertEqual(
            [r["value"] for r in records[0]["results"]], [60, 120, 180, 240]
        )
        self.assertIn("계산식", (self.teacher / "output/sharing.md").read_text())

    def test_mismatched_dataset_and_code_expressions_are_rejected(self):
        enroll(self.student, self.cfg, "p01")
        original = self.payload["dataset_sha256"]
        self.payload["dataset_sha256"] = "different data"
        push_metric(self.student, self.cfg, self.payload)
        record = collect(self.teacher, self.teacher / "output")[0]
        self.assertEqual(record["status"], "확인 필요")
        self.assertIn("데이터 버전", record["message"])
        self.payload["dataset_sha256"] = original
        self.payload["metric"]["expression"] = "__import__('os').system('false')"
        push_metric(self.student, self.cfg, self.payload)
        record = collect(self.teacher, self.teacher / "output")[0]
        self.assertEqual(record["status"], "확인 필요")
        self.assertEqual(record["results"], [])

    def test_malformed_submission_does_not_abort_collection(self):
        enroll(self.student, self.cfg, "p01")
        push_metric(self.student, self.cfg, [])
        records = collect(self.teacher, self.teacher / "output")
        self.assertEqual(records[0]["status"], "확인 필요")
        self.assertIn("JSON 객체", records[0]["message"])

    def test_empty_collection_is_supported(self):
        self.assertEqual(collect(self.teacher, self.teacher / "output"), [])


if __name__ == "__main__":
    unittest.main()
