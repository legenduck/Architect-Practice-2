from __future__ import annotations

import ast
import math
import operator
import re
import statistics

from .data import MEASURES, SCENARIOS, Study


def estimated_cost(run: dict, pricing: dict) -> float | None:
    rates = pricing.get("models", {}).get(run.get("model"), {})
    inp, out = run.get("input_tokens"), run.get("output_tokens")
    ip, op = rates.get("input_per_million"), rates.get("output_per_million")
    if None in (inp, out, ip, op):
        return None
    cached = run.get("cached_input_tokens")
    cp = rates.get("cached_input_per_million")
    if cached is None:
        if cp is None or cp != ip:
            return None
        # Equal rates make the split algebraically irrelevant, not observed zero.
        cached = 0
    if cached and cp is None:
        return None
    if cp is None:
        cp = 0  # Only reachable when the observed cached input is zero.
    return ((inp - cached) * ip + cached * cp + out * op) / 1_000_000


def full_mean(values: list) -> float | None:
    return (
        statistics.mean(values)
        if values and all(v is not None for v in values)
        else None
    )


def summary(study: Study) -> list[dict]:
    rows = []
    for key, label in SCENARIOS.items():
        runs = [r for r in study.runs if r["scenario"] == key]
        known = all(r.get("success") is not None for r in runs)
        successes = sum(r.get("success") is True for r in runs)
        costs = [estimated_cost(r, study.pricing) for r in runs]
        cost_per_success = (
            sum(costs) / successes
            if runs and known and successes and all(c is not None for c in costs)
            else None
        )
        rows.append(
            {
                "scenario": key,
                "label": label,
                "runs": len(runs),
                "successful_runs": successes if known and runs else None,
                "task_success_rate": successes / len(runs) if runs and known else None,
                "cost_per_success": cost_per_success,
                **{
                    field: full_mean([r.get(field) for r in runs]) for field in MEASURES
                },
            }
        )
    return rows


def readiness(study: Study) -> dict:
    rows = summary(study)
    present = all(r["runs"] for r in rows)
    outcomes = present and all(r["task_success_rate"] is not None for r in rows)
    costs = outcomes and all(r["cost_per_success"] is not None for r in rows)
    phases = bool(study.runs) and all(
        any(
            p["run_id"] == r["id"]
            and p.get("input_tokens") is not None
            and p.get("elapsed_seconds") is not None
            for p in study.phases
        )
        for r in study.runs
    )
    all_passed = outcomes and all(r["task_success_rate"] == 1 for r in rows)
    core = bool(study.runs) and all(
        all(
            r.get(k) is not None
            for k in ("input_tokens", "output_tokens", "elapsed_seconds")
        )
        for r in study.runs
    )
    traces = bool(study.runs) and all(study.traces.get(r["id"]) for r in study.runs)
    raw_logs = bool(study.runs) and all(r["id"] in study.raw_logs for r in study.runs)
    return {
        "run_count": len(study.runs),
        "four_scenarios": present,
        "outcomes_available": outcomes,
        "cost_available": costs,
        "phase_records_available": phases,
        "all_tasks_successful": all_passed,
        "core_measurements_available": core,
        "trace_records_available": bool(traces),
        "raw_logs_available": raw_logs,
        "class_ready": bool(
            all_passed
            and core
            and costs
            and phases
            and traces
            and raw_logs
            and not study.notes
        ),
        "notes": study.notes,
    }


FIELDS = set(MEASURES) | {"success", "estimated_cost"}
PHASE_MEASURES = {"input_tokens", "output_tokens", "elapsed_seconds"}
OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
COMPARE = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def validate_metric(metric: dict) -> ast.Expression:
    if not isinstance(metric, dict):
        raise ValueError("지표 정의는 JSON 객체 하나로 작성하세요.")
    for key in [
        "name",
        "purpose",
        "expression",
        "aggregation",
        "unit",
        "interpretation",
    ]:
        if not isinstance(metric.get(key), str) or not metric[key].strip():
            raise ValueError(f"지표 정의의 {key}를 작성하세요.")
    if metric["aggregation"] not in [
        "mean",
        "median",
        "sum",
        "min",
        "max",
        "percentage",
        "per_success",
    ]:
        raise ValueError("지원하지 않는 집계 방식입니다.")
    phase_inputs = metric.get("phase_inputs", {})
    if not isinstance(phase_inputs, dict) or len(phase_inputs) > 16:
        raise ValueError(
            "phase_inputs는 구간 측정값 이름을 최대 16개 연결하는 객체입니다."
        )
    for alias, selection in phase_inputs.items():
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", alias)
            or alias in FIELDS
            or not isinstance(selection, dict)
            or not isinstance(selection.get("phase"), str)
            or not selection["phase"].strip()
            or not isinstance(selection.get("measure"), str)
            or selection["measure"] not in PHASE_MEASURES
        ):
            raise ValueError("구간 측정값의 별칭, phase와 measure를 확인하세요.")
    expression = metric["expression"]
    if len(expression) > 500:
        raise ValueError("계산식은 500자 이내로 작성하세요.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ValueError("계산식 문법을 확인하세요.") from error
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Name,
        ast.Constant,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.UAdd,
        ast.USub,
        ast.Not,
        ast.Compare,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Eq,
        ast.NotEq,
        ast.BoolOp,
        ast.And,
        ast.Or,
    )
    nodes = list(ast.walk(tree))
    if len(nodes) > 100 or any(not isinstance(n, allowed) for n in nodes):
        raise ValueError("측정값의 산술식과 비교식만 사용할 수 있습니다.")
    names = [n.id for n in nodes if isinstance(n, ast.Name)]
    if not names or any(n not in FIELDS | set(phase_inputs) for n in names):
        raise ValueError("계산식에 제공된 측정값 이름을 사용하세요.")
    for node in nodes:
        if isinstance(node, ast.Constant) and (
            type(node.value) not in (int, float, bool)
            or abs(node.value) > 1e12
            or not math.isfinite(node.value)
        ):
            raise ValueError("계산식의 상수는 유한한 숫자여야 합니다.")
    if metric["aggregation"] == "percentage" and metric["unit"] != "%":
        raise ValueError("percentage의 단위는 %로 지정하세요.")
    return tree


def evaluate_node(node: ast.AST, row: dict):
    if isinstance(node, ast.Expression):
        return evaluate_node(node.body, row)
    if isinstance(node, ast.Name):
        value = row.get(node.id)
        if value is None:
            raise ValueError(node.id + " 값이 없습니다.")
        return value
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        return OPS[type(node.op)](
            evaluate_node(node.left, row), evaluate_node(node.right, row)
        )
    if isinstance(node, ast.UnaryOp):
        value = evaluate_node(node.operand, row)
        return (
            -value
            if isinstance(node.op, ast.USub)
            else (+value if isinstance(node.op, ast.UAdd) else not value)
        )
    if isinstance(node, ast.BoolOp):
        values = [evaluate_node(v, row) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = evaluate_node(node.left, row)
        for op, right_node in zip(node.ops, node.comparators):
            right = evaluate_node(right_node, row)
            if not COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    raise ValueError("지원하지 않는 계산식입니다.")


def custom_metric(study: Study, metric: dict) -> list[dict]:
    tree = validate_metric(metric)
    result = []
    for key, label in SCENARIOS.items():
        runs = [r for r in study.runs if r["scenario"] == key]
        value = None
        reason = "실행 기록 없음"
        try:
            values = [
                evaluate_node(
                    tree,
                    {
                        **r,
                        "estimated_cost": estimated_cost(r, study.pricing),
                        **phase_values(study, r["id"], metric.get("phase_inputs", {})),
                    },
                )
                for r in runs
            ]
            if values:
                kind = metric["aggregation"]
                if kind == "percentage":
                    if any(type(v) is not bool for v in values):
                        raise ValueError("percentage에는 비교식이 필요합니다.")
                    value = 100 * sum(values) / len(values)
                elif kind == "per_success":
                    if any(r.get("success") is None for r in runs):
                        raise ValueError("과제 성공 여부가 미확인입니다.")
                    count = sum(r["success"] for r in runs)
                    if not count:
                        raise ValueError("성공한 실행이 없습니다.")
                    value = sum(values) / count
                else:
                    value = {
                        "mean": statistics.mean,
                        "median": statistics.median,
                        "sum": sum,
                        "min": min,
                        "max": max,
                    }[kind](values)
                if not math.isfinite(value):
                    raise ValueError("계산 결과가 유한하지 않습니다.")
                reason = ""
        except (ValueError, ZeroDivisionError, OverflowError, TypeError) as error:
            reason = str(error)
            value = None
        result.append(
            {
                "scenario": key,
                "label": label,
                "value": value,
                "unit": metric["unit"],
                "reason": reason,
            }
        )
    return result


def phase_values(study: Study, run_id: str, selections: dict) -> dict:
    """Explicitly selected phases only. Missing phases/measurements stay unknown."""
    values = {}
    for alias, selection in selections.items():
        measured = [
            p.get(selection["measure"])
            for p in study.phases
            if p["run_id"] == run_id and p["phase"] == selection["phase"]
        ]
        values[alias] = (
            sum(measured) if measured and all(v is not None for v in measured) else None
        )
    return values
