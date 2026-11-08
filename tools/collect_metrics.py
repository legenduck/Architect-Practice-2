"""개인 브랜치의 지표 정의를 수집하고 같은 데이터로 계산한다. 학생 코드는 실행하지 않는다."""

from __future__ import annotations
import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from practice2.gitflow import git
from practice2.data import load_study
from practice2.metrics import custom_metric, readiness, validate_metric
from practice2.report import number


def md_text(value) -> str:
    value = html.escape(str(value)).replace("\n", " ").replace("\r", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", value)


def collect(root: Path, output: Path) -> list[dict]:
    if git(root, "branch", "--show-current").stdout.strip() != "main":
        raise ValueError("중앙 수집은 강사가 관리하는 main 브랜치에서 실행하세요.")
    git(
        root,
        "fetch",
        "--prune",
        "origin",
        "+refs/heads/students/*:refs/remotes/origin/students/*",
    )
    study = load_study(root / "data")
    state = readiness(study)
    records = []
    refs = git(
        root,
        "for-each-ref",
        "--format=%(refname) %(objectname)",
        "refs/remotes/origin/students/",
    ).stdout.splitlines()
    for line in refs:
        ref, commit = line.split()
        person = ref.removeprefix("refs/remotes/origin/students/")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", person):
            continue
        object_name = commit + ":submissions/metric.json"
        size = git(root, "cat-file", "-s", object_name, check=False)
        if size.returncode:
            continue
        record = {
            "participant": person,
            "commit": commit,
            "status": "확인 필요",
            "metric": None,
            "results": [],
        }
        try:
            if int(size.stdout) > 300_000:
                raise ValueError("제출 파일이 너무 큽니다.")
            payload = json.loads(git(root, "show", object_name).stdout)
            if not isinstance(payload, dict):
                raise ValueError("제출 파일은 JSON 객체여야 합니다.")
            if payload.get("participant") != person:
                raise ValueError("참가자 번호가 브랜치와 다릅니다.")
            metric = payload["metric"]
            validate_metric(metric)
            record["metric"] = metric
            if payload.get("dataset_sha256") != study.fingerprint:
                raise ValueError(
                    "데이터 버전이 다릅니다. 같은 자료로 다시 계산해야 합니다."
                )
            if not state["class_ready"]:
                raise ValueError("실제 실습 자료가 아직 준비되지 않았습니다.")
            values = custom_metric(study, metric)
            record["results"] = values
            if any(r["value"] is None for r in values):
                raise ValueError("계산할 수 없는 측정값이 포함되어 있습니다.")
            record["status"] = "계산 확인"
        except (ValueError, KeyError, TypeError) as error:
            record["message"] = str(error)
        records.append(record)
    output.mkdir(parents=True, exist_ok=True)
    (output / "submissions.json").write_text(
        json.dumps(records, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    md = [
        "# 실습 2 지표 공유",
        "",
        "참가자 번호순으로 표시합니다. 계산 확인은 지표의 타당성에 대한 점수가 아닙니다. 평가 목적과 해석 근거를 함께 검토합니다.",
        "",
    ]
    for record in records:
        metric = record["metric"] or {}
        md += [
            "## " + record["participant"],
            "",
            "**" + md_text(metric.get("name", "지표 미확인")) + "**",
            "",
            "계산 상태: " + record["status"],
            "",
            "평가 목적: " + md_text(metric.get("purpose", "")),
            "",
            "계산식: " + md_text(metric.get("expression", "")),
            "",
            "집계 방식: " + md_text(metric.get("aggregation", "")),
            "",
            "구간 측정값 연결: "
            + md_text(json.dumps(metric.get("phase_inputs", {}), ensure_ascii=False)),
            "",
            "해석 기준: " + md_text(metric.get("interpretation", "")),
            "",
            "| 작업 방식 | 계산값 | 단위 |",
            "|---|---:|---|",
        ]
        for row in record["results"]:
            value = number(row["value"])
            md.append(
                "| "
                + row["label"]
                + " | "
                + value
                + " | "
                + md_text(row["unit"])
                + " |"
            )
        if record.get("message"):
            md += ["", md_text(record["message"])]
        md.append("")
    if not records:
        md += ["제출된 지표가 없습니다."]
    (output / "sharing.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return records


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "output/sharing")
    a = p.parse_args()
    try:
        print("수집한 지표:", len(collect(ROOT, a.output)))
        print("공유 자료:", a.output / "sharing.md")
    except (OSError, ValueError) as error:
        p.exit(1, f"확인 필요: {error}\n")
