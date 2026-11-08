"""가상 수치는 계산 검증용이며 수업 데이터로 배포하지 않는다."""

from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from practice2.data import SCENARIOS, load_study, write_jsonl
from practice2.metrics import custom_metric, estimated_cost, readiness, summary
from practice2.report import render


def fixture(folder: Path):
    runs = []
    phases = []
    for i, key in enumerate(SCENARIOS):
        run = {
            "id": f"test-{i}",
            "scenario": key,
            "model": "fixture-model",
            "task_sha256": "0" * 64,
            "baseline_sha256": "1" * 64,
            "success": True,
            "input_tokens": 1_000_000,
            "cached_input_tokens": 400_000,
            "output_tokens": 100_000,
            "elapsed_seconds": 60 + i * 60,
            "llm_calls": 3 + i,
            "tool_calls": 5 + i,
            "retries": 0,
            "source_sha256": "synthetic-test-fixture",
        }
        runs.append(run)
        write_jsonl(
            folder / "raw" / f"{run['id']}.jsonl",
            [{"type": "fixture", "description": "synthetic test fixture"}],
        )
        write_jsonl(
            folder / "traces" / f"{run['id']}.jsonl",
            [
                {
                    "event_id": "fixture-event",
                    "type": "command_execution",
                    "command": "fixture only",
                }
            ],
        )
        phases.append(
            {
                "run_id": run["id"],
                "id": "phase-1",
                "phase": "테스트용 구간",
                "input_tokens": 500_000,
                "output_tokens": 50_000,
                "elapsed_seconds": 30,
                "evidence": "synthetic fixture",
                "attribution_method": "계산 검증을 위해 만든 수치. 실제 실행 아님",
            }
        )
    pricing = {
        "models": {
            "fixture-model": {
                "input_per_million": 2,
                "cached_input_per_million": 0.5,
                "output_per_million": 4,
                "currency": "TEST-UNIT",
                "source": "synthetic test fixture",
                "as_of": "2026-01-01",
            }
        }
    }
    write_jsonl(folder / "runs.jsonl", runs)
    write_jsonl(folder / "phases.jsonl", phases)
    (folder / "pricing.json").write_text(json.dumps(pricing))
    return runs, phases, pricing


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_dataset_is_not_ready_and_has_no_fake_zero_values(self):
        study = load_study(self.root)
        self.assertFalse(readiness(study)["class_ready"])
        self.assertTrue(all(r["task_success_rate"] is None for r in summary(study)))
        self.assertIn("기록이 아직 등록되지 않았습니다", render(study))

    def test_cost_separates_cached_input_without_double_counting(self):
        runs, _, rates = fixture(self.root)
        self.assertAlmostEqual(estimated_cost(runs[0], rates), 1.8)

    def test_missing_cache_split_is_not_treated_as_zero(self):
        runs, _, rates = fixture(self.root)
        runs[0]["cached_input_tokens"] = None
        self.assertIsNone(estimated_cost(runs[0], rates))
        rates["models"]["fixture-model"]["cached_input_per_million"] = 2
        self.assertAlmostEqual(estimated_cost(runs[0], rates), 2.4)

    def test_missing_cached_price_does_not_assume_full_price(self):
        runs, _, rates = fixture(self.root)
        rates["models"]["fixture-model"]["cached_input_per_million"] = None
        self.assertIsNone(estimated_cost(runs[0], rates))

    def test_failed_attempt_cost_is_included(self):
        runs, _, _ = fixture(self.root)
        failed = {**runs[0], "id": "failed-attempt", "success": False}
        write_jsonl(self.root / "runs.jsonl", runs + [failed])
        study = load_study(self.root)
        r = summary(study)[0]
        self.assertEqual(r["task_success_rate"], 0.5)
        self.assertAlmostEqual(r["cost_per_success"], 3.6)
        self.assertFalse(readiness(study)["all_tasks_successful"])

    def test_unknown_outcome_is_not_counted_as_failure_or_pass(self):
        runs, _, _ = fixture(self.root)
        runs[0]["success"] = None
        write_jsonl(self.root / "runs.jsonl", runs)
        r = summary(load_study(self.root))[0]
        self.assertIsNone(r["task_success_rate"])
        self.assertIsNone(r["cost_per_success"])

    def test_models_or_tasks_must_match(self):
        runs, _, _ = fixture(self.root)
        runs[0]["model"] = "different-model"
        write_jsonl(self.root / "runs.jsonl", runs)
        with self.assertRaises(ValueError):
            load_study(self.root)

    def test_duplicate_runs_are_rejected(self):
        runs, _, _ = fixture(self.root)
        write_jsonl(self.root / "runs.jsonl", runs + [runs[0]])
        with self.assertRaises(ValueError):
            load_study(self.root)

    def test_phase_double_allocation_is_rejected(self):
        _, phases, _ = fixture(self.root)
        phases[0]["input_tokens"] = 2_000_000
        write_jsonl(self.root / "phases.jsonl", phases)
        with self.assertRaises(ValueError):
            load_study(self.root)

    def test_missing_phase_evidence_is_rejected(self):
        _, phases, _ = fixture(self.root)
        phases[0]["evidence"] = ""
        write_jsonl(self.root / "phases.jsonl", phases)
        with self.assertRaises(ValueError):
            load_study(self.root)

    def test_arbitrary_code_cannot_be_used_as_metric(self):
        fixture(self.root)
        study = load_study(self.root)
        metric = {
            "name": "test",
            "purpose": "test",
            "expression": "__import__('os').system('echo bad')",
            "aggregation": "mean",
            "unit": "test",
            "interpretation": "test",
        }
        with self.assertRaises(ValueError):
            custom_metric(study, metric)

    def test_threshold_rate_preserves_scenario_order(self):
        fixture(self.root)
        study = load_study(self.root)
        metric = {
            "name": "time threshold",
            "purpose": "test",
            "expression": "elapsed_seconds > 120",
            "aggregation": "percentage",
            "unit": "%",
            "interpretation": "test",
        }
        rows = custom_metric(study, metric)
        self.assertEqual([r["scenario"] for r in rows], list(SCENARIOS))
        self.assertEqual([r["value"] for r in rows], [0, 0, 100, 100])

    def test_missing_material_and_zero_division_stay_unknown(self):
        runs, _, _ = fixture(self.root)
        runs[0]["llm_calls"] = None
        write_jsonl(self.root / "runs.jsonl", runs)
        study = load_study(self.root)
        metric = {
            "name": "test",
            "purpose": "test",
            "expression": "input_tokens / llm_calls",
            "aggregation": "mean",
            "unit": "token",
            "interpretation": "test",
        }
        self.assertIsNone(custom_metric(study, metric)[0]["value"])
        metric["expression"] = "input_tokens / retries"
        self.assertTrue(all(r["value"] is None for r in custom_metric(study, metric)))

    def test_rendered_text_cannot_inject_html(self):
        fixture(self.root)
        study = load_study(self.root)
        metric = {
            "name": "<script>alert(1)</script>",
            "purpose": "test",
            "expression": "elapsed_seconds",
            "aggregation": "mean",
            "unit": "s",
            "interpretation": "test",
        }
        page = render(study, metric)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_dataset_fingerprint_changes_with_pricing(self):
        _, _, rates = fixture(self.root)
        before = load_study(self.root).fingerprint
        rates["models"]["fixture-model"]["output_per_million"] = 5
        (self.root / "pricing.json").write_text(json.dumps(rates))
        self.assertNotEqual(before, load_study(self.root).fingerprint)

    def test_complete_fixture_is_ready(self):
        fixture(self.root)
        self.assertTrue(readiness(load_study(self.root))["class_ready"])

    def test_initial_code_must_match(self):
        runs, _, _ = fixture(self.root)
        runs[0]["baseline_sha256"] = "2" * 64
        write_jsonl(self.root / "runs.jsonl", runs)
        with self.assertRaises(ValueError):
            load_study(self.root)

    def test_metric_can_use_phase_measurements_without_assuming_missing_is_zero(self):
        _, phases, _ = fixture(self.root)
        metric = {
            "name": "phase share",
            "purpose": "fixture",
            "phase_inputs": {
                "reading_input": {"phase": "테스트용 구간", "measure": "input_tokens"}
            },
            "expression": "100 * reading_input / input_tokens",
            "aggregation": "mean",
            "unit": "%",
            "interpretation": "fixture",
        }
        self.assertEqual(
            [r["value"] for r in custom_metric(load_study(self.root), metric)], [50] * 4
        )
        phases[0]["input_tokens"] = None
        write_jsonl(self.root / "phases.jsonl", phases[0:3])
        rows = custom_metric(load_study(self.root), metric)
        self.assertIsNone(rows[0]["value"])
        self.assertIsNone(rows[3]["value"])
        self.assertEqual(rows[1]["value"], 50)


if __name__ == "__main__":
    unittest.main()
