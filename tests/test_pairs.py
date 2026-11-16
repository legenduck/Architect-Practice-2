from pathlib import Path
import json
import shutil
import tempfile
import unittest

from practice2.data import default_data, load_study
from practice2.metrics import custom_metric, estimated_cost, readiness
from practice2.report import render

ROOT = Path(__file__).resolve().parents[1]


def metric(expression):
    return dict(name="반복 검증", purpose="같은 상태의 재검증 비율 확인",
                expression=expression, aggregation="mean", unit="%",
                interpretation="작업 필요성은 로그에서 별도로 판단")


class PairTests(unittest.TestCase):
    def test_bundled_records_support_full_analysis_with_provenance(self):
        study = load_study(default_data(ROOT))
        self.assertTrue(readiness(study)["class_ready"])
        self.assertEqual(study.provenance["kind"], "constructed")
        self.assertIn("재구성한 교육용 로그", render(study))
        expected = [0, 100 * 5 / 9, 0, 0]
        actual = custom_metric(study, metric("100 * same_state_passed_rechecks / test_runs"))
        for row, value in zip(actual, expected):
            self.assertAlmostEqual(row["value"], value)
        self.assertTrue(all(r["value"] is None for r in custom_metric(study, metric("retries"))))
        for run in study.runs:
            self.assertAlmostEqual(estimated_cost(run, study.pricing), run["estimated_cost"])
            phases = [p for p in study.phases if p["run_id"] == run["id"]]
            for field in ("input_tokens", "output_tokens", "elapsed_seconds"):
                self.assertAlmostEqual(sum(p[field] for p in phases), run[field])

    def test_fingerprint_ignores_generated_views_but_tracks_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "log_pairs"
            shutil.copytree(ROOT / "log_pairs", folder)
            before = load_study(folder).fingerprint
            (folder / "materials.json").write_text("{}")
            (folder / "index.html").write_text("modified view")
            self.assertEqual(load_study(folder).fingerprint, before)
            path = folder / "manifest.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["pricing"]["output_per_million"] += 1
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertNotEqual(load_study(folder).fingerprint, before)

    def test_missing_or_corrupt_evidence_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "log_pairs"
            shutil.copytree(ROOT / "log_pairs", folder)
            path = next((folder / "objects").glob("*.txt"))
            path.write_text("corrupt")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_study(folder)

    def test_duplicate_scenario_cannot_look_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "log_pairs"
            shutil.copytree(ROOT / "log_pairs", folder)
            path = folder / "manifest.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["runs"][0] = value["runs"][1]
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "네 작업 방식"):
                load_study(folder)


if __name__ == "__main__":
    unittest.main()
