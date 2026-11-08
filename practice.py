"""실습 2: 기록 확인, 지표 계산과 설계 결과 내보내기."""

from __future__ import annotations
import argparse
import csv
import json
import shutil
from pathlib import Path

from practice2.data import load_study
from practice2.metrics import readiness, summary, custom_metric
from practice2.report import write_report

ROOT = Path(__file__).resolve().parent


def export(study, output, metric=None):
    output.mkdir(parents=True, exist_ok=True)
    records = summary(study)
    with (output / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    values = custom_metric(study, metric) if metric else None
    result = {
        "dataset_sha256": study.fingerprint,
        "readiness": readiness(study),
        "summary": records,
        "metric": metric,
        "metric_results": values,
    }
    (output / "evaluation.json").write_text(
        json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    return write_report(study, output, metric)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--metric", type=Path)
    analyze.add_argument("--output", type=Path, default=ROOT / "output")
    validate = sub.add_parser("validate")
    validate.add_argument("--require-ready", action="store_true")
    create = sub.add_parser("new-metric")
    create.add_argument("--path", type=Path, default=ROOT / "metrics/my_metric.json")
    enroll = sub.add_parser("enroll")
    enroll.add_argument("participant")
    submit = sub.add_parser("submit")
    submit.add_argument("--metric", type=Path, default=ROOT / "metrics/my_metric.json")
    args = parser.parse_args()
    try:
        if args.command == "enroll":
            from practice2.gitflow import REPOSITORY, enroll

            cfg = {"repository": REPOSITORY, "participant": args.participant}
            print("실습 브랜치:", enroll(ROOT, cfg, args.participant))
            return
        if args.command == "new-metric":
            if args.path.exists():
                raise ValueError("기존 지표 파일은 덮어쓰지 않습니다.")
            args.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "metrics/template.json", args.path)
            print("지표 정의 파일:", args.path)
            return
        study = load_study(args.data)
        state = readiness(study)
        if args.command == "submit":
            from practice2.gitflow import push_metric

            if not state["class_ready"]:
                raise ValueError(
                    "실제 실습 자료가 준비되지 않았습니다. 데이터 등록 후 제출하세요."
                )
            metric = json.loads(args.metric.read_text(encoding="utf-8"))
            values = custom_metric(study, metric)
            if any(r["value"] is None for r in values):
                raise ValueError(
                    "계산되지 않는 항목이 있습니다. 지표 정의와 측정값을 확인하세요."
                )
            cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            payload = {
                "participant": cfg["participant"],
                "dataset_sha256": study.fingerprint,
                "metric": metric,
                "results": values,
            }
            print("제출 완료:", push_metric(ROOT, cfg, payload))
            return
        if args.command in (None, "status", "validate"):
            print(json.dumps(state, ensure_ascii=False, indent=2))
            if (
                args.command == "validate"
                and args.require_ready
                and not state["class_ready"]
            ):
                raise SystemExit(1)
        else:
            metric = (
                json.loads(args.metric.read_text(encoding="utf-8"))
                if args.metric
                else None
            )
            print("결과 화면:", export(study, args.output, metric))
            if not study.runs:
                print("실제 실행 기록 미등록. 데이터 등록 후 값이 계산됩니다.")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"확인 필요: {error}\n")


if __name__ == "__main__":
    main()
