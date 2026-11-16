"""Readiness checks; no login, model request, commit, or remote branch creation."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

from .data import load_study
from .gitflow import REPOSITORY, git, participant, verify_remote
from .metrics import readiness


def diagnose(root: Path, data: Path, offline: bool = False) -> dict:
    checks = []

    def record(name, ok, detail, fix=""):
        checks.append({"name": name, "status": "PASS" if ok else "FAIL",
                       "detail": detail, "fix": "" if ok else fix})

    record("Python", sys.version_info >= (3, 10), sys.version.split()[0], "Python 3.10 이상을 설치하세요.")
    try:
        with tempfile.TemporaryFile(dir=root) as handle:
            handle.write(b"practice2-doctor")
        record("파일 저장", True, "실습 폴더에 결과 저장 가능")
    except OSError:
        record("파일 저장", False, "실습 폴더에 쓸 수 없음", "쓰기 가능한 폴더에 다시 clone하세요.")

    dataset = None
    try:
        study = load_study(data)
        dataset = readiness(study)
        record("실습 자료", dataset["class_ready"],
               f"{dataset['run_count']}개 기록 / {dataset['dataset_kind']}",
               "git pull --ff-only 후 다시 실행하세요. 자료를 수정했다면 강사에게 확인하세요.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        record("실습 자료", False, str(error), "실습 자료 파일과 버전을 확인하세요.")

    codex = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex:
        record("Codex 로그인", False, "Codex CLI를 찾을 수 없음", "실습 1에서 사용한 Codex CLI 설치와 로그인을 완료하세요.")
    else:
        try:
            result = subprocess.run([codex, "login", "status"], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=15)
            record("Codex 로그인", result.returncode == 0,
                   "로그인 확인" if result.returncode == 0 else "로그인 확인 실패",
                   "codex login 후 다시 실행하세요.")
            help_result = subprocess.run([codex, "sandbox", "--help"], capture_output=True,
                                         text=True, encoding="utf-8", errors="replace", timeout=15)
            platform = "windows" if sys.platform == "win32" else ("macos" if sys.platform == "darwin" else "linux")
            # Older CLI releases used platform subcommands; newer ones select the host automatically.
            platform_args = [platform] if any(line.strip().startswith(platform + " ") for line in help_result.stdout.splitlines()) else []
            probe = subprocess.run(
                [codex, "sandbox", *platform_args, "-c", 'sandbox_mode="workspace-write"', "--", sys.executable,
                 "-c", "import tempfile; f=tempfile.TemporaryFile(dir='.'); f.write(b'doctor'); f.close()"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            )
            record("Codex 실행 환경", probe.returncode == 0,
                   "샌드박스 내 명령·파일 저장 확인" if probe.returncode == 0 else "샌드박스에서 명령을 실행하지 못함",
                   "Codex 터미널 실행과 OS 샌드박스 설정을 강사에게 확인하세요. 제한된 서버·컨테이너라면 준비된 실습 PC/VM을 사용하세요.")
        except (OSError, subprocess.TimeoutExpired):
            record("Codex 로그인", False, "Codex 실행 실패 또는 시간 초과", "터미널에서 codex login status를 확인하세요.")

    try:
        version = git(root, "--version", timeout=15).stdout.strip()
        actual_root = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if actual_root != root.resolve():
            raise ValueError("실습 저장소의 루트가 아닙니다.")
        record("Git", True, version)
        identity = all(git(root, "config", "--get", key, check=False).stdout.strip()
                       for key in ("user.name", "user.email"))
        record("Git 작성자", identity, "이름·이메일 설정 확인" if identity else "이름 또는 이메일 미설정",
               'git config user.name "이름" 및 git config user.email "이메일"을 설정하세요.')
        cfg_path = root / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        verify_remote(root, cfg.get("repository", REPOSITORY))
        record("제출 저장소", True, "origin 확인")
        if cfg.get("participant"):
            branch = "students/" + participant(cfg["participant"])
            current = git(root, "branch", "--show-current").stdout.strip()
            record("개인 브랜치", current == branch, current,
                   f"python lab.py enroll {cfg['participant']}로 개인 브랜치를 선택하세요.")
        else:
            branch = "students/doctor-" + uuid.uuid4().hex[:12]
        if offline:
            checks.append({"name": "GitHub 쓰기 연결", "status": "SKIP",
                           "detail": "오프라인 점검에서는 생략", "fix": "제출 전 python lab.py doctor를 실행하세요."})
        else:
            result = git(root, "push", "--dry-run", "--porcelain", "origin",
                         "HEAD:refs/heads/" + branch, check=False, timeout=30)
            record("GitHub 쓰기 연결", result.returncode == 0,
                   "push --dry-run 성공 (원격 변경 없음)" if result.returncode == 0 else "push --dry-run 실패",
                   "GitHub Git 로그인과 collaborator 초대 수락을 확인하세요. 기존 개인 브랜치라면 원격 변경도 확인하세요.")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        record("Git 제출 준비", False, "Git 설정·연결을 확인하지 못했습니다.",
               "git status, origin 주소, config.json을 확인하세요. 네트워크 점검은 30초 후 종료됩니다.")

    local_ready = all(c["status"] != "FAIL" for c in checks)
    return {"ready": local_ready and not offline, "local_ready": local_ready,
            "offline": offline, "dataset": dataset, "checks": checks}


def print_diagnosis(result: dict) -> None:
    for check in result["checks"]:
        print(f"[{check['status']}] {check['name']}: {check['detail']}")
        if check["fix"]:
            print("       " + check["fix"])
    if result["ready"]:
        print("실습 준비 완료. python lab.py analyze로 시작하세요.")
    elif result["offline"] and result["local_ready"]:
        print("로컬 준비 완료. GitHub 제출 연결은 아직 확인하지 않았습니다.")
    else:
        print("확인 필요 항목을 해결한 뒤 doctor를 다시 실행하세요.")
