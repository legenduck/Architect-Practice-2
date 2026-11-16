"""Adapt validated paired records without copying or modifying the source dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from log_pairs.tools.analyze_pairs import analyze
from .data import SCENARIOS, Study, jsonl

PAIR_MEASURES = (
    "reasoning_output_tokens", "first_input_tokens", "test_runs",
    "same_state_passed_rechecks", "document_lookups", "same_document_range_lookups",
    "model_seconds", "tool_seconds", "calculation_items", "calculator_executions",
    "calculation_explanation_occurrences", "calculation_input_tokens",
    "calculation_output_tokens", "calculation_seconds", "calculation_cost",
)


def load_pairs(folder: Path) -> Study:
    try:
        manifest, rows, timelines = analyze(folder)
        if len(rows) != 4 or {r["scenario"] for r in rows} != set(SCENARIOS):
            raise ValueError("네 작업 방식이 각각 하나씩 필요합니다.")
        runs, phases, traces, raw_logs, models = [], [], {}, {}, set()
        for entry, row in zip(manifest["runs"], rows):
            identifier = row["run_id"]
            code = jsonl(folder / entry["codex"])
            harness = jsonl(folder / entry["harness"])
            model = code[0]["model"]
            models.add(model)
            runs.append({
                **row, "id": identifier, "model": model,
                "task_sha256": manifest["task_sha256"],
                "baseline_sha256": manifest["baseline_sha256"],
                # Rechecks are not retries. No retry definition is supplied.
                "retries": None,
            })
            raw_logs[identifier] = folder / entry["codex"]
            traces[identifier] = []
            for step in timelines[row["scenario"]]:
                phases.append({
                    "run_id": identifier, "id": step["request_id"],
                    "phase": step["activity"],
                    "input_tokens": step["usage"]["input_tokens"],
                    "output_tokens": step["usage"]["output_tokens"],
                    "elapsed_seconds": (step["end_ms"] - step["start_ms"]) / 1000,
                    "evidence": f"{entry['codex']} / {entry['harness']} / {step['request_id']}",
                    "attribution_method": "같은 request_id의 usage와 요청 전체 시간. 모델·도구 시간을 다시 더하지 않음. 재구성 자료.",
                })
                for tool in step["tools"]:
                    traces[identifier].append({
                        "event_id": tool["call"]["event_id"],
                        "type": tool["observation"]["operation"],
                        "observed_at": f"상대 {tool['observation']['start_ms'] / 1000:.3f}초 (모델값)",
                        "command": tool["call"]["arguments"].get("cmd", json.dumps(tool["call"]["arguments"], ensure_ascii=False)),
                        "exit_code": tool["result"]["exit_code"],
                    })
            if hashlib.sha256((folder / "task.md").read_bytes()).hexdigest() != manifest["task_sha256"]:
                raise ValueError("과제 요청문 식별값이 다릅니다.")
            initial = jsonl(folder / manifest["runs"][0]["harness"])[0]["initial_state"]
            if any(harness[0]["initial_state"][key] != initial[key]
                   for key in ("code_version", "tests_version", "data_version")):
                raise ValueError("초기 코드·테스트·데이터 상태가 다릅니다.")
        if len(models) != 1:
            raise ValueError("모델이 다른 기록이 섞여 있습니다.")
        digest = hashlib.sha256()
        paths = [folder / name for name in ("manifest.json", "task.md", "calculation_cases.json")]
        for directory in ("cases", "states", "objects", "grading"):
            paths.extend(p for p in (folder / directory).rglob("*") if p.is_file())
        for path in sorted(paths):
            digest.update(path.relative_to(folder).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
        provenance = {
            **manifest["provenance"], "dataset_id": manifest["dataset_id"],
            "usage_basis": manifest["usage_model"]["basis"],
            "time_basis": manifest["time_model"]["basis"],
        }
        return Study(runs, phases, {"models": {next(iter(models)): manifest["pricing"]}},
                     digest.hexdigest(), [], traces, raw_logs, provenance, folder)
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"로그 자료 형식을 확인하세요: {error}") from error
