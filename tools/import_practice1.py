"""실습 1 실행 폴더를 실습 2의 측정값 표로 변환한다. 원본 내용은 덮어쓰지 않는다."""

from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from practice2.data import SCENARIOS, load_study, write_jsonl, jsonl


def convert(folder: Path, scenario: str, grade_file: Path | None = None) -> dict:
    source = folder / "summary.json"
    raw = source.read_bytes()
    record = json.loads(raw)
    usage = record.get("usage", {})
    grade = record.get("grade", {})
    if grade_file:
        grade = json.loads(grade_file.read_text(encoding="utf-8"))
        if grade.get("run_id") and grade["run_id"] != record["id"]:
            raise ValueError("채점 결과의 실행 ID가 다릅니다.")
        if grade.get("source_sha256") and grade["source_sha256"] != record.get(
            "source_sha256"
        ):
            raise ValueError("채점 결과의 소스와 실행 기록이 다릅니다.")
    status = grade.get("status")
    success = True if status == "passed" else False if status == "failed" else None
    observed_tools = None
    log = folder / "events.jsonl"
    if log.exists():
        ids = set()
        for item in jsonl(log):
            event = item.get("item", {})
            if (
                item.get("type") == "item.completed"
                and event.get("type")
                in ("command_execution", "mcp_tool_call", "web_search", "file_change")
                and event.get("id")
            ):
                ids.add(event["id"])
        observed_tools = len(ids) if ids else None
    conditions = record.get("conditions", {})
    return {
        "id": record["id"],
        "scenario": scenario,
        "model": conditions.get("model"),
        "task_sha256": conditions.get("request_sha256"),
        "baseline_sha256": conditions.get("baseline_sha256"),
        "comparison_valid": record.get("comparison_valid"),
        "success": success,
        "input_tokens": usage.get("input_tokens"),
        "cached_input_tokens": usage.get("cached_input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "elapsed_seconds": record.get("elapsed_seconds"),
        "llm_calls": len(usage.get("calls", []))
        if usage.get("call_detail") == "rollout.token_count.reconciled"
        else None,
        "tool_calls": observed_tools,
        "retries": None,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "measurement_notes": {
            "tool_calls": "기록된 완료 도구 항목 수. 내부 하위 호출 수와 다를 수 있음",
            "retries": "실습 1 기본 기록으로는 재시도 의미를 확정할 수 없어 미제공",
        },
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run", type=Path)
    p.add_argument("--scenario", choices=SCENARIOS, required=True)
    p.add_argument("--data", type=Path, default=ROOT / "data")
    p.add_argument("--grade", type=Path, help="별도로 보관한 실습 1 채점 결과")
    p.add_argument(
        "--include-raw-log",
        action="store_true",
        help="배포할 내용을 검토한 events.jsonl 원본도 복사",
    )
    a = p.parse_args()
    run = convert(a.run, a.scenario, a.grade)
    events_path = a.run / "events.jsonl"
    if a.include_raw_log and not events_path.is_file():
        p.error("원본 events.jsonl이 없습니다.")
    rows = jsonl(a.data / "runs.jsonl")
    if any(r["id"] == run["id"] for r in rows):
        p.error("같은 실행 ID가 이미 있습니다.")
    a.data.mkdir(parents=True, exist_ok=True)
    temporary = a.data / "runs.jsonl.tmp"
    write_jsonl(temporary, rows + [run])
    # Validate before replacing the class dataset.
    import tempfile, shutil

    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        for name in ["phases.jsonl", "pricing.json"]:
            if (a.data / name).exists():
                shutil.copyfile(a.data / name, work / name)
        shutil.copyfile(temporary, work / "runs.jsonl")
        load_study(work)
    timed = {
        r.get("sequence"): r.get("observed_at")
        for r in jsonl(a.run / "events-timed.jsonl")
    }
    traces = []
    for index, event in enumerate(jsonl(a.run / "events.jsonl"), 1):
        item = event.get("item", {})
        if event.get("type") not in ("item.completed", "turn.completed", "turn.failed"):
            continue
        trace = {
            "event_id": f"event-{index}",
            "type": item.get("type", event.get("type")),
            "observed_at": timed.get(index),
        }
        for field in ["id", "command", "exit_code", "status", "tool"]:
            if field in item:
                trace[field] = item[field]
        if isinstance(trace.get("command"), str):
            trace["command"] = trace["command"].replace(
                str((a.run / "workspace").resolve()), "."
            )
        output = item.get("aggregated_output")
        if isinstance(output, str):
            trace["output_bytes"] = len(output.encode())
            trace["output_sha256"] = hashlib.sha256(output.encode()).hexdigest()
        traces.append(trace)
    write_jsonl(a.data / "traces" / f"{run['id']}.jsonl", traces)
    manifest_path = a.data / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {"schema_version": 1}
    )
    temporary.replace(a.data / "runs.jsonl")
    if a.include_raw_log:
        raw_folder = a.data / "raw"
        raw_folder.mkdir(exist_ok=True)
        shutil.copyfile(events_path, raw_folder / f"{run['id']}.jsonl")
    manifest.update(
        status="records_added_needs_validation",
        run_count=len(rows) + 1,
        description="실행 기록이 등록되었습니다. 단가와 구간 측정 자료를 확인해야 합니다.",
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("등록:", run["id"], SCENARIOS[a.scenario])
    print("구간별 기록과 재시도 횟수는 원본 근거에 따라 별도로 등록해야 합니다.")


if __name__ == "__main__":
    main()
