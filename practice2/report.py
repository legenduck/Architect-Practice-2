from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from .data import SCENARIOS, Study
from .metrics import custom_metric, readiness, summary


def text(value: object) -> str:
    return html.escape(str(value))


def number(value, percent=False) -> str:
    if value is None:
        return "미제공"
    if not percent and 0 < abs(value) < 0.0001:
        return f"{value:.3g}"
    return f"{value * 100:.1f}%" if percent else f"{value:,.4f}".rstrip("0").rstrip(".")


def table(headers: list[str], rows: list[list]) -> str:
    return (
        '<div class="scroll"><table><thead><tr>'
        + "".join("<th>" + text(x) + "</th>" for x in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + text(x) + "</td>" for x in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def bars(rows: list[dict], field: str, percent=False) -> str:
    maximum = max([r[field] for r in rows if r[field] is not None] + [1e-12])
    parts = []
    for row in rows:
        value = row[field]
        bar = (
            ""
            if value is None
            else '<span class="bar" style="width:'
            + str(value / maximum * 100)
            + '%"></span>'
        )
        parts.append(
            '<div class="barrow"><div>'
            + text(row["label"])
            + '</div><div class="track">'
            + bar
            + "</div><strong>"
            + text(number(value, percent))
            + "</strong></div>"
        )
    return "".join(parts)


def render(study: Study, metric: dict | None = None) -> str:
    state = readiness(study)
    rows = summary(study)
    if not study.runs:
        status = '<p class="notice">실행 기록이 아직 등록되지 않았습니다. 이 화면의 미제공 항목은 실제 데이터 등록 후 계산됩니다. 예시 숫자를 실측값으로 표시하지 않습니다.</p>'
    elif not state["class_ready"]:
        status = '<p class="notice">일부 자료가 부족합니다. 비용 단가, 구간 기록과 실행 조건을 확인하세요. 없는 값은 0으로 처리하지 않습니다.</p>'
    else:
        status = "<p>같은 실행 기록을 지표별로 비교합니다. 표시 순서는 이론 2의 낭비 유형과 기법 적용 사례 순서입니다.</p>"
    if study.runs and not state["all_tasks_successful"]:
        status += '<p class="notice">과제 성공률이 같다는 실습 도입 전제를 확인해야 합니다. 실패하거나 성공 여부가 미확인인 기록도 삭제하지 않고 포함합니다.</p>'
    body = "<h1>과정 지표로 Codex 작업 평가하기</h1>" + status
    body += (
        "<p>실행 기록 "
        + str(len(study.runs))
        + "개. 지표 계산에 사용한 자료 식별값: <code>"
        + study.fingerprint[:12]
        + "</code></p>"
    )
    body += (
        "<h2>과제 성공률</h2><p>공통 채점을 통과한 실행의 비율입니다. 결과물의 기능 검증에 사용하며, 작업에 든 자원까지 설명하지는 않습니다.</p>"
        + bars(rows, "task_success_rate", True)
    )
    currencies = sorted(
        {
            study.pricing.get("models", {})
            .get(r.get("model"), {})
            .get("currency", "미등록")
            for r in study.runs
        }
    )
    body += (
        "<h2>정답 1개당 비용</h2><p>전체 실행의 환산 비용 합계를 성공한 실행 수로 나눕니다. 성공률이 같아도 비용이 달라지는지 확인합니다. 사내 실제 청구액이 아닌 실습용 환산값입니다. 통화: "
        + text(", ".join(currencies) or "미등록")
        + "</p>"
        + bars(rows, "cost_per_success")
    )
    body += table(
        [
            "작업 방식",
            "기록 수",
            "과제 성공률",
            "정답 1개당 비용",
            "평균 실행 시간(초)",
        ],
        [
            [
                r["label"],
                r["runs"],
                number(r["task_success_rate"], True),
                number(r["cost_per_success"]),
                number(r["elapsed_seconds"]),
            ]
            for r in rows
        ],
    )
    body += "<h2>작업 구간별 토큰과 시간</h2><p>구간 구분과 자원 배분의 근거를 함께 확인합니다. 자원을 많이 쓴 구간에서도 필요한 검증과 불필요한 반복을 구분해야 합니다.</p>"
    if not study.phases:
        body += '<p class="notice">구간별 기록이 없습니다. 실행 총량만으로 문서 조회, 추론, 테스트 등의 사용량을 나누어 계산하지 않습니다.</p>'
    seen_scenarios = set()
    phase_names = sorted({p["phase"] for p in study.phases})
    for run in study.runs:
        phases = [p for p in study.phases if p["run_id"] == run["id"]]
        if not phases:
            continue
        opened = " open" if run["scenario"] not in seen_scenarios else ""
        seen_scenarios.add(run["scenario"])
        body += (
            "<details"
            + opened
            + "><summary>"
            + text(SCENARIOS[run["scenario"]])
            + " / "
            + text(run["id"])
            + "</summary>"
        )
        colors = ["#4169e1", "#6b8de8", "#95adee", "#bac9f4", "#dadde5"]
        for field, label in [
            ("input_tokens", "구간에 배분한 입력 토큰"),
            ("output_tokens", "구간에 배분한 출력 토큰"),
            ("elapsed_seconds", "구간에 배분한 시간(초)"),
        ]:
            total = run.get(field)
            known = [p for p in phases if p.get(field) is not None]
            if total is None or not known:
                continue
            body += (
                "<p>"
                + label
                + '</p><div style="display:flex;height:28px;background:#eee">'
            )
            for i, p in enumerate(known):
                width = p[field] / total * 100 if total else 0
                body += (
                    '<span title="'
                    + text(p["phase"] + ": " + number(p[field]))
                    + '" style="display:block;width:'
                    + str(width)
                    + "%;background:"
                    + colors[phase_names.index(p["phase"]) % len(colors)]
                    + '"></span>'
                )
            body += "</div>"
        body += (
            "<p>"
            + "".join(
                '<span style="display:inline-block;width:14px;height:14px;margin-right:6px;background:'
                + colors[phase_names.index(name) % len(colors)]
                + '"></span>'
                + text(name)
                + "　"
                for name in sorted({p["phase"] for p in phases})
            )
            + '<span style="background:#eee">미배분</span></p>'
        )
        cells = [
            [
                p["phase"],
                number(p.get("input_tokens")),
                number(p.get("output_tokens")),
                number(p.get("elapsed_seconds")),
                p["evidence"],
                p["attribution_method"],
            ]
            for p in phases
        ]
        remainders = []
        for field in ["input_tokens", "output_tokens", "elapsed_seconds"]:
            values = [p.get(field) for p in phases]
            total = run.get(field)
            remainders.append(
                number(max(0, total - sum(v for v in values if v is not None)))
                if total is not None and any(v is not None for v in values)
                else "미제공"
            )
        cells.append(
            [
                "미배분",
                *remainders,
                "실행 총량에서 배분된 값을 뺀 나머지",
                "특정 작업으로 추정하지 않음",
            ]
        )
        body += (
            table(
                [
                    "작업 구간",
                    "입력 토큰",
                    "출력 토큰",
                    "시간(초)",
                    "근거",
                    "배분 기준",
                ],
                cells,
            )
            + "</details>"
        )
    body += "<details><summary>실행 기록 확인</summary><p>아래 표는 완료된 명령과 이벤트를 추출한 자료입니다. 원본 로그에서는 명령 출력과 에이전트 메시지 등 기록된 내용을 확인할 수 있습니다.</p>"
    for run in study.runs:
        trace = study.traces.get(run["id"], [])
        if not trace:
            continue
        if run["id"] in study.raw_logs:
            body += (
                '<p><a href="records/'
                + text(run["id"])
                + '.jsonl">'
                + text(run["id"])
                + " 원본 로그 열기</a></p>"
            )
        body += (
            "<h3>"
            + text(run["id"])
            + "</h3>"
            + table(
                ["이벤트", "종류", "관측 시각", "명령", "종료 코드"],
                [
                    [
                        e.get("event_id", ""),
                        e.get("type", ""),
                        e.get("observed_at") or "미제공",
                        e.get("command", ""),
                        e.get("exit_code", ""),
                    ]
                    for e in trace
                ],
            )
        )
    body += "</details>"
    if metric:
        evaluated = custom_metric(study, metric)
        body += (
            "<h2>설계한 지표: "
            + text(metric["name"])
            + "</h2><p><b>평가 목적:</b> "
            + text(metric["purpose"])
            + "</p><p><b>계산 방법:</b> <code>"
            + text(metric["expression"])
            + "</code>, "
            + text(metric["aggregation"])
            + "</p><p><b>해석 기준:</b> "
            + text(metric["interpretation"])
            + "</p>"
        )
        body += table(
            ["작업 방식", "계산 결과", "단위", "계산 상태"],
            [
                [r["label"], number(r["value"]), r["unit"], r["reason"] or "계산 완료"]
                for r in evaluated
            ],
        )
        if metric.get("phase_inputs"):
            body += table(
                ["계산식의 이름", "선택한 작업 구간", "측정값"],
                [
                    [alias, item["phase"], item["measure"]]
                    for alias, item in metric["phase_inputs"].items()
                ],
            )
        body += "<p>지표값이 달라졌다는 사실만으로 지표가 타당하다고 판단하지 않습니다. 어떤 작업 차이를 설명하며 담당 업무에 왜 필요한지 실행 기록과 연결해 해석합니다.</p>"
    body += (
        "<details><summary>지표 설계에 사용할 측정값</summary>"
        + table(
            [
                "실행",
                "작업 방식",
                "입력 토큰",
                "출력 토큰",
                "LLM 호출",
                "도구 호출",
                "재시도",
            ],
            [
                [
                    r["id"],
                    SCENARIOS[r["scenario"]],
                    number(r.get("input_tokens")),
                    number(r.get("output_tokens")),
                    number(r.get("llm_calls")),
                    number(r.get("tool_calls")),
                    number(r.get("retries")),
                ]
                for r in study.runs
            ],
        )
        + "</details>"
    )
    body += (
        "<details><summary>단가와 자료 확인 상태</summary><pre>"
        + text(
            json.dumps(
                {"pricing": study.pricing, "readiness": state},
                ensure_ascii=False,
                indent=2,
            )
        )
        + "</pre></details>"
    )
    css = """.p2{font:18px/1.7 system-ui,sans-serif;max-width:1350px;margin:35px auto;padding:0 24px;color:#202329}.p2 h1{font-size:34px}.p2 h2{font-size:25px;margin-top:42px}.p2 h3{font-size:20px}.p2 table{border-collapse:collapse;width:100%;font-size:16px}.p2 td,.p2 th{text-align:left;padding:10px;border-bottom:1px solid #ddd}.p2 th{border-top:2px solid #222}.p2 .scroll{overflow-x:auto}.p2 .notice{background:#f4f5f7;border-left:4px solid #4169e1;padding:16px}.p2 .barrow{display:grid;grid-template-columns:310px 1fr 120px;gap:18px;align-items:center;margin:14px 0}.p2 .bar{display:block;background:#4169e1;height:26px}.p2 .track{width:100%}.p2 pre{white-space:pre-wrap;font-size:14px}.p2 details{margin-top:24px}.p2 code{background:#f2f3f5;padding:2px 5px}@media(max-width:750px){.p2 .barrow{grid-template-columns:1fr}.p2 h1{font-size:28px}}"""
    return (
        '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>실습 2 결과 비교</title><style>'
        + css
        + '</style><main class="p2">'
        + body
        + "</main></html>"
    )


def write_report(study: Study, output: Path, metric: dict | None = None) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    if study.raw_logs:
        records = output / "records"
        records.mkdir(exist_ok=True)
        for identifier, source in study.raw_logs.items():
            destination = records / f"{identifier}.jsonl"
            if source.resolve() != destination.resolve():
                shutil.copyfile(source, destination)
    path = output / "report.html"
    path.write_text(render(study, metric), encoding="utf-8")
    return path
