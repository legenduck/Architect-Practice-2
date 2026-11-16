"""Fresh clone through submission, resume, and instructor recomputation on real course data."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

from practice2.gitflow import git

ROOT = Path(__file__).resolve().parents[1]


class StudentFlowTests(unittest.TestCase):
    def test_course_commands_from_clone_to_collection_and_resubmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            git(root, "init", "--bare", "--initial-branch=main", str(remote))
            teacher = root / "teacher"
            git(root, "clone", str(remote), str(teacher))
            for name in ("practice2", "log_pairs", "tools", "metrics"):
                shutil.copytree(ROOT / name, teacher / name,
                                ignore=shutil.ignore_patterns("__pycache__", "my_metric.json"))
            for name in ("lab.py", "practice.py", ".gitignore", ".gitattributes"):
                shutil.copyfile(ROOT / name, teacher / name)
            for key, value in (("user.name", "Course test"), ("user.email", "course@example.invalid"), ("commit.gpgsign", "false")):
                git(teacher, "config", key, value)
            git(teacher, "add", ".")
            git(teacher, "commit", "-m", "Course")
            git(teacher, "push", "origin", "main")
            student = root / "student"
            git(root, "clone", str(remote), str(student))
            for key, value in (("user.name", "Student"), ("user.email", "student@example.invalid"), ("commit.gpgsign", "false")):
                git(student, "config", key, value)

            def command(folder, *args, ok=True):
                result = subprocess.run([sys.executable, *args], cwd=folder,
                                        capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
                return result

            command(student, "lab.py", "validate", "--require-ready")
            command(student, "lab.py", "analyze")
            command(student, "lab.py", "new-metric")
            command(student, "lab.py", "new-metric", ok=False)
            path = student / "metrics/my_metric.json"
            metric = json.loads(path.read_text(encoding="utf-8"))
            metric.update(name="동일 상태 재검증 비율", expression="100 * same_state_passed_rechecks / test_runs",
                          aggregation="mean", unit="%")
            path.write_text(json.dumps(metric), encoding="utf-8")
            command(student, "lab.py", "analyze", "--metric", "metrics/my_metric.json")
            command(student, "lab.py", "submit", ok=False)
            command(student, "lab.py", "enroll", "p01", "--repository", str(remote))
            command(student, "lab.py", "submit")
            head = git(student, "rev-parse", "HEAD").stdout
            command(student, "lab.py", "submit")
            self.assertEqual(git(student, "rev-parse", "HEAD").stdout, head)
            command(teacher, "tools/collect_metrics.py")
            collected = json.loads((teacher / "output/sharing/submissions.json").read_text(encoding="utf-8"))
            evaluation = json.loads((student / "output/evaluation.json").read_text(encoding="utf-8"))
            self.assertEqual(collected[0]["status"], "계산 확인")
            self.assertEqual(collected[0]["results"], evaluation["metric_results"])
            self.assertEqual(collected[0]["provenance"]["kind"], "constructed")
            self.assertEqual(git(student, "diff", "--name-only", "origin/main...HEAD").stdout.strip(), "submissions/metric.json")
            # A new computer must resume the existing branch and recover the metric.
            resumed = root / "resumed"
            git(root, "clone", str(remote), str(resumed))
            command(resumed, "lab.py", "enroll", "p01", "--repository", str(remote))
            self.assertTrue((resumed / "metrics/my_metric.json").is_file())
            self.assertEqual(json.loads((resumed / "metrics/my_metric.json").read_text(encoding="utf-8")), metric)


if __name__ == "__main__":
    unittest.main()
