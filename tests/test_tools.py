from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from import_practice1 import convert


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_keeps_missing_calls_and_retries_unknown(self):
        record = {
            "id": "fixture-run",
            "conditions": {"model": "fixture-model", "request_sha256": "0" * 64},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 10,
                "calls": [],
                "call_detail": "not_available",
            },
            "grade": {"status": "passed"},
            "elapsed_seconds": 3,
        }
        (self.root / "summary.json").write_text(json.dumps(record))
        row = convert(self.root, "reference")
        self.assertIs(row["success"], True)
        self.assertIsNone(row["llm_calls"])
        self.assertIsNone(row["retries"])

    def test_grade_must_belong_to_the_run(self):
        (self.root / "summary.json").write_text(
            json.dumps({"id": "a", "usage": {}, "conditions": {}})
        )
        (self.root / "grade.json").write_text(
            json.dumps({"run_id": "b", "status": "passed"})
        )
        with self.assertRaises(ValueError):
            convert(self.root, "reference", self.root / "grade.json")

    def test_timestamp_wrapper_forwards_events_without_changing_them(self):
        workspace = self.root / "run/workspace"
        workspace.mkdir(parents=True)
        fake = self.root / "fake.py"
        fake.write_text(
            "import json\nprint(json.dumps({'type':'turn.started'}),flush=True)\nprint(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':2}}),flush=True)\n"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/capture_codex.py"),
                sys.executable,
                str(fake),
                "-C",
                str(workspace),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        original = [json.loads(s) for s in result.stdout.splitlines()]
        timed = [
            json.loads(s)
            for s in (workspace.parent / "events-timed.jsonl").read_text().splitlines()
        ]
        self.assertEqual(original, [x["event"] for x in timed])
        self.assertTrue(all(x["observed_elapsed_seconds"] >= 0 for x in timed))
        repeated = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/capture_codex.py"),
                sys.executable,
                str(fake),
                "-C",
                str(workspace),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(repeated.returncode, 0)


if __name__ == "__main__":
    unittest.main()
