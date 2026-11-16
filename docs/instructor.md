# 강사 준비와 제출 수집

## 수업 전

1. 이 변경을 교육용 저장소의 main에 반영한 뒤 clone 경로를 배포합니다.
2. 참가자마다 고유한 번호를 배정하고 GitHub collaborator 초대 수락, Git 로그인, Codex 로그인을 마치게 합니다.
3. GitHub Actions가 허용되어 있는지 확인합니다. `students/*` 개인 브랜치에 제출할 수 있어야 합니다.
4. 새 clone에서 `python lab.py doctor`, `python lab.py validate --require-ready`, `python lab.py analyze`를 실행합니다.
5. 서로 다른 참가자 번호 두 개로 제출하고 자동 수집의 공유 자료를 확인합니다.

`class_ready`는 공통 자료의 완결성입니다. 개인 컴퓨터의 설치·로그인·권한까지 포함한 점검은 `doctor`를 사용합니다. `--offline`은 GitHub 쓰기 연결을 점검하지 않습니다.

교육 자료는 재구성한 로그이며 토큰·시간은 모델값입니다. 실측 실행 성능이나 숨겨진 추론을 측정한 값으로 소개하지 않습니다. 단가 역시 제공 자료의 환산 기준이며 실제 청구액이 아닙니다.

## 제출 결과 확인

학생이 `python lab.py submit`을 실행하면 `students/<번호>` 브랜치가 갱신됩니다. **Actions → Collect student metrics**의 해당 실행에서 `practice2-sharing` 아티팩트를 받습니다.

- `sharing.md`: 참가자 번호순으로 지표 정의·해석·재계산 결과 표시
- `submissions.json`: 같은 결과의 구조화된 자료

자동 수집은 main의 코드와 공통 자료를 사용합니다. 학생의 계산 코드나 제출된 숫자를 실행·신뢰하지 않고, 지표 정의만 검증해서 다시 계산합니다. 잘못된 지표·자료 버전은 해당 참가자만 '확인 필요'로 표시하며 나머지 제출 수집은 계속합니다. 자동 순위는 만들지 않습니다.

Actions가 지연되거나 사용하지 않는 환경에서는 강사 clone의 main에서 직접 수집합니다.

```bash
git switch main
git pull --ff-only
python tools/collect_metrics.py
```

결과는 `output/sharing/`입니다. 최초 제출 전에는 '제출된 지표가 없습니다'라고 표시합니다. 가장 최근 Actions 실행이 실패했다면 이전 아티팩트를 최신 결과로 안내하지 않습니다.

## 별도 교육 저장소 또는 포크

강사가 지정한 저장소를 clone한 경우 최초 등록 시 주소를 지정합니다.

```bash
python lab.py enroll p01 --repository https://github.com/OWNER/Architect-Practice-2.git
python lab.py doctor
```

이후 명령은 저장된 주소를 사용합니다. 원본 저장소와 다른 origin을 자동으로 허용하지는 않습니다.

## 변경 검증

```bash
python -m unittest discover -s tests -q
```

실제 제공 로그 검증, 구간 합계·비용 계산, doctor의 실패 처리와 원격 무변경, 새 clone에서 등록·제출·재제출·강사 재계산·새 컴퓨터 복원까지 포함합니다. 로컬 Git 통합 테스트는 외부 GitHub나 모델을 호출하지 않습니다. GitHub Actions는 Linux·Windows·macOS의 Python 3.10에서 실행합니다.
