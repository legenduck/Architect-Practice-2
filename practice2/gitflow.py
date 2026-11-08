"""GitHub branch submission. No model API or GitHub API token is needed here."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .storage import write_json

REPOSITORY = "https://github.com/legenduck/Architect-Practice-2.git"
BRANCH_PREFIX = "students/"


def participant(value: str) -> str:
    identifier = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", identifier):
        raise ValueError("참가자 번호는 p01처럼 영문 소문자와 숫자로 입력하세요.")
    return identifier


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if check and done.returncode:
        raise ValueError("Git 명령을 완료하지 못했습니다.\n" + done.stderr.strip())
    return done


def canonical(url: str) -> str:
    value = url.strip().rstrip("/")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1]
    parts = urlparse(value)
    if parts.scheme in ("https", "http") and (parts.username or parts.password):
        raise ValueError(
            "저장소 주소에 인증 정보를 넣지 마세요. Git 로그인 도구를 사용하세요."
        )
    return value.removesuffix(".git").lower()


def verify_remote(root: Path, repository: str) -> None:
    actual = git(root, "remote", "get-url", "origin").stdout.strip()
    if canonical(actual) != canonical(repository):
        raise ValueError(
            "origin이 교육용 저장소와 다릅니다. 연구원에게 확인을 요청하세요."
        )


def enroll(root: Path, cfg: dict, identifier: str) -> str:
    identifier = participant(identifier)
    verify_remote(root, cfg.get("repository", REPOSITORY))
    branch = BRANCH_PREFIX + identifier
    current = git(root, "branch", "--show-current").stdout.strip()
    if current != branch:
        if git(root, "status", "--porcelain").stdout.strip():
            raise ValueError(
                "저장소에 변경사항이 있습니다. 내용을 보존한 채 연구원에게 브랜치 전환을 요청하세요."
            )
        git(root, "fetch", "origin")
        if (
            git(
                root,
                "show-ref",
                "--verify",
                "--quiet",
                "refs/heads/" + branch,
                check=False,
            ).returncode
            == 0
        ):
            git(root, "switch", branch)
        elif (
            git(
                root,
                "show-ref",
                "--verify",
                "--quiet",
                "refs/remotes/origin/" + branch,
                check=False,
            ).returncode
            == 0
        ):
            git(root, "switch", "--track", "-c", branch, "origin/" + branch)
        else:
            git(root, "switch", "-c", branch, "origin/main")
    cfg.update(participant=identifier, repository=cfg.get("repository", REPOSITORY))
    write_json(root / "config.json", cfg)
    return branch


def submission_branch(root: Path, cfg: dict) -> str:
    verify_remote(root, cfg.get("repository", REPOSITORY))
    identifier = participant(cfg["participant"])
    branch = BRANCH_PREFIX + identifier
    if git(root, "branch", "--show-current").stdout.strip() != branch:
        raise ValueError(
            f"먼저 python lab.py enroll {identifier}로 개인 브랜치를 선택하세요. main에는 제출하지 않습니다."
        )
    return branch


def push_metric(root: Path, cfg: dict, payload: dict) -> dict:
    branch = submission_branch(root, cfg)
    relative = "submissions/metric.json"
    staged = git(root, "diff", "--cached", "--name-only", "-z").stdout.split("\0")
    if any(p and p != relative for p in staged):
        raise ValueError(
            "다른 파일이 커밋 대상으로 지정되어 있습니다. 먼저 확인하세요."
        )
    write_json(root / relative, payload)
    git(root, "add", "--", relative)
    if git(root, "diff", "--cached", "--quiet", "--", relative, check=False).returncode:
        git(root, "commit", "-m", "Submit Practice 2 metric definition and results")
    git(root, "push", "-u", "origin", "HEAD:refs/heads/" + branch)
    return {"branch": branch, "commit": git(root, "rev-parse", "HEAD").stdout.strip()}
