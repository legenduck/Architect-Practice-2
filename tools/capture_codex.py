"""실습 1의 codex_command 앞에 연결하는 관측 시각 기록기.

사용 예: ["python", "/path/to/capture_codex.py", "codex"]
CLI JSONL은 그대로 전달하고, -C로 지정한 작업 폴더의 상위에
events-timed.jsonl을 기록한다. 관측 시각은 모델 내부 추론 시간이 아니다.
"""

from __future__ import annotations
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    command = sys.argv[1:]
    if not command:
        raise SystemExit("실행할 Codex 명령을 지정하세요.")
    if "--version" in command or "-C" not in command:
        return subprocess.run(command, check=False).returncode
    position = command.index("-C")
    if position + 1 >= len(command):
        raise SystemExit("-C 작업 폴더가 없습니다.")
    workspace = Path(command[position + 1]).resolve()
    if not workspace.is_dir():
        raise SystemExit("작업 폴더가 없습니다.")
    target = workspace.parent / "events-timed.jsonl"
    if target.exists():
        raise SystemExit("기존 관측 기록을 덮어쓰지 않습니다.")
    started = time.monotonic()
    # Inherit stdin and stderr. The parent harness controls timeout and the
    # process group; no new session is created here.
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    with target.open("w", encoding="utf-8") as log:
        for index, line in enumerate(process.stdout, 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"unparsed_line": line.rstrip("\n")}
            record = {
                "sequence": index,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "observed_elapsed_seconds": time.monotonic() - started,
                "event": event,
            }
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()
            sys.stdout.write(line)
            sys.stdout.flush()
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
