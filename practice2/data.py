from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

SCENARIOS = {
    "context_overload": "입력 컨텍스트 과다",
    "repeated_work": "중복 전송과 재계산",
    "reasoning_reliance": "LLM 추론에 대한 과도한 의존",
    "reference": "기법 적용 사례",
}
MEASURES = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "elapsed_seconds",
    "llm_calls",
    "tool_calls",
    "retries",
)
COUNTS = set(MEASURES) - {"elapsed_seconds"}


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path.name} {number}행: JSON 형식 오류") from error
        if not isinstance(row, dict):
            raise ValueError(f"{path.name} {number}행: 객체 형식이 필요합니다.")
        result.append(row)
    return result


def numeric(value: object, name: str, integer: bool = False) -> None:
    if value is None:
        return
    if (
        type(value) not in (int, float)
        or abs(value) > 1e18
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name}: 0 이상의 유한한 숫자 또는 null이 필요합니다.")
    if integer and type(value) is not int:
        raise ValueError(f"{name}: 정수가 필요합니다.")


@dataclass
class Study:
    runs: list[dict]
    phases: list[dict]
    pricing: dict
    fingerprint: str
    notes: list[str]
    traces: dict[str, list[dict]] = dataclass_field(default_factory=dict)
    raw_logs: dict[str, Path] = dataclass_field(default_factory=dict)


def load_study(folder: Path) -> Study:
    runs = jsonl(folder / "runs.jsonl")
    phases = jsonl(folder / "phases.jsonl")
    pricing = (
        json.loads((folder / "pricing.json").read_text(encoding="utf-8"))
        if (folder / "pricing.json").exists()
        else {"models": {}}
    )
    if not isinstance(pricing, dict) or not isinstance(pricing.get("models", {}), dict):
        raise ValueError("단가 파일의 models는 객체 형식이어야 합니다.")
    ids = set()
    models = set()
    tasks = set()
    baselines = set()
    notes = []
    for run in runs:
        identifier = run.get("id")
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}", identifier)
            or identifier in ids
        ):
            raise ValueError("실행 ID가 없거나 중복되었습니다.")
        ids.add(identifier)
        if not isinstance(run.get("scenario"), str) or run["scenario"] not in SCENARIOS:
            raise ValueError(f"{identifier}: 작업 방식 이름을 확인하세요.")
        if run.get("success") is not None and type(run["success"]) is not bool:
            raise ValueError(
                f"{identifier}: success는 true, false 또는 null이어야 합니다."
            )
        for field in MEASURES:
            numeric(run.get(field), f"{identifier}.{field}", field in COUNTS)
        if (
            run.get("input_tokens") is not None
            and run.get("cached_input_tokens") is not None
            and run["cached_input_tokens"] > run["input_tokens"]
        ):
            raise ValueError(f"{identifier}: 캐시 입력이 전체 입력보다 큽니다.")
        if run.get("model") and not isinstance(run["model"], str):
            raise ValueError("모델 이름은 문자열이어야 합니다.")
        if run.get("task_sha256") and not isinstance(run["task_sha256"], str):
            raise ValueError("과제 식별값은 문자열이어야 합니다.")
        if run.get("model"):
            models.add(run["model"])
        else:
            notes.append(f"{identifier}: 모델 정보 미확인")
        if run.get("task_sha256"):
            tasks.add(run["task_sha256"])
        else:
            notes.append(f"{identifier}: 과제 요청문 식별값 미확인")
        if isinstance(run.get("baseline_sha256"), str) and run["baseline_sha256"]:
            baselines.add(run["baseline_sha256"])
        else:
            notes.append(f"{identifier}: 초기 코드 식별값 미확인")
        if run.get("comparison_valid") is False:
            notes.append(f"{identifier}: 원본 실행에서 비교 조건 위반으로 표시된 기록")
    if len(models) > 1:
        raise ValueError(
            "모델이 다른 실행 기록이 섞여 있습니다. 같은 모델의 기록으로 구성하세요."
        )
    if len(tasks) > 1:
        raise ValueError("과제가 다른 실행 기록이 섞여 있습니다.")
    if len(baselines) > 1:
        raise ValueError("초기 코드가 다른 실행 기록이 섞여 있습니다.")
    phase_ids = set()
    by_run = {r["id"]: r for r in runs}
    sums = {}
    for phase in phases:
        if not isinstance(phase.get("run_id"), str) or phase["run_id"] not in ids:
            raise ValueError("구간 기록이 가리키는 실행이 없습니다.")
        if not isinstance(phase.get("id"), str) or not phase["id"]:
            raise ValueError("구간 ID는 문자열이어야 합니다.")
        key = (phase["run_id"], phase.get("id"))
        if not phase.get("id") or key in phase_ids:
            raise ValueError("구간 ID가 없거나 중복되었습니다.")
        phase_ids.add(key)
        if any(
            not isinstance(phase.get(k), str) or not phase[k].strip()
            for k in ["id", "phase", "evidence", "attribution_method"]
        ):
            raise ValueError("구간 이름, 근거와 배분 기준이 필요합니다.")
        for field in ["input_tokens", "output_tokens", "elapsed_seconds"]:
            value = phase.get(field)
            numeric(value, f"구간 {key}.{field}", field != "elapsed_seconds")
            if value is not None:
                sums[(phase["run_id"], field)] = (
                    sums.get((phase["run_id"], field), 0) + value
                )
    for (identifier, field), value in sums.items():
        total = by_run[identifier].get(field)
        if total is not None and value > total + 1e-6:
            raise ValueError(
                f"{identifier}: {field}의 구간 합계가 실행 총량보다 큽니다. 중복 배분을 확인하세요."
            )
    for model, rates in pricing.get("models", {}).items():
        if not isinstance(rates, dict):
            raise ValueError("모델별 단가 형식을 확인하세요.")
        for field in [
            "input_per_million",
            "cached_input_per_million",
            "output_per_million",
        ]:
            numeric(rates.get(field), f"{model}.{field}")
        if (
            not rates.get("source")
            or not rates.get("as_of")
            or not rates.get("currency")
        ):
            raise ValueError("단가에는 출처, 기준일과 통화가 필요합니다.")
    h = hashlib.sha256()
    for name in ["runs.jsonl", "phases.jsonl", "pricing.json"]:
        h.update(name.encode())
        h.update((folder / name).read_bytes() if (folder / name).exists() else b"")
    traces = {}
    raw_logs = {}
    for identifier in sorted(ids):
        trace_path = folder / "traces" / f"{identifier}.jsonl"
        traces[identifier] = jsonl(trace_path)
        h.update(identifier.encode())
        if trace_path.exists():
            h.update(trace_path.read_bytes())
        raw_path = folder / "raw" / f"{identifier}.jsonl"
        h.update(b"raw-log")
        if raw_path.is_file() and raw_path.stat().st_size:
            raw_logs[identifier] = raw_path
            h.update(raw_path.read_bytes())
    return Study(runs, phases, pricing, h.hexdigest(), notes, traces, raw_logs)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows
        ),
        encoding="utf-8",
    )
