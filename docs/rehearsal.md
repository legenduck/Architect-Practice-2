# 실습 2 전체 흐름 검증 기록

검증일: 2026-11-16. 원본 저장소에 대한 현재 계정의 쓰기 권한이 없어 `wonjaeL/Architect-Practice-2` 포크에서 실제 GitHub 제출을 검증했습니다. 원본 main은 변경하지 않았습니다.

## 실제 수강생 실행

Linux VM의 Python 3.10.12, 로그인한 Codex CLI와 Git을 사용했습니다. 샌드박스를 활성화한 상태로 진행했습니다.

| 단계 | 결과 |
|---|---|
| 새 clone와 개인 브랜치 등록 | 통과 |
| doctor | 자료·Codex 로그인·샌드박스 명령/저장·Git 작성자·원격 쓰기 연결 모두 PASS |
| 기본 보고서 생성 | 네 작업 방식의 성공률·환산 비용·구간 토큰·시간 표시 |
| Codex에 지표 작성 요청 | 실제 CLI가 docs/metric-design.md를 읽고 지표 파일 수정·계산 완료 |
| 첫 제출 | students/audit-e2e-01에 지표 정의와 결과 푸시 |
| 같은 내용 재제출 | 같은 커밋 유지, push 성공 |
| 새 clone에서 이어 하기 | 동일 번호로 등록 후 제출된 지표 정의 복원, doctor 통과 |
| 두 번째 참가자 제출 | students/audit-e2e-02에 다른 지표 제출 |
| 강사 재계산 | 두 참가자 모두 계산 확인, 수강생 계산값과 일치 |
| GitHub 자동 수집 | Actions 아티팩트 다운로드·SHA256·두 참가자의 값 확인 |
| Chromium 브라우저 | 보고서·지표값·네 시나리오 펼치기·명령/반환값·파일 링크 14개·390px 화면 확인, 페이지 오류 없음 |

첫 지표는 `100 * same_state_passed_rechecks / test_runs`입니다. 값은 순서대로 0%, 55.5556%, 0%, 0%입니다. 두 번째 지표 `100 * same_document_range_lookups / document_lookups`는 0%, 80%, 0%, 0%입니다.

[실제 두 참가자 제출의 자동 수집 실행](https://github.com/wonjaeL/Architect-Practice-2/actions/runs/43848305065)에서 `practice2-sharing` 아티팩트를 확인할 수 있습니다. 참가자 번호순으로 표시하며 품질 점수나 순위를 만들지 않습니다.

## 자동 테스트와 범위

[Linux·Windows·macOS / Python 3.10 검사](https://github.com/wonjaeL/Architect-Practice-2/actions/runs/43847848273)에서 각 37개 테스트와 자료 준비 검증이 통과했습니다. 테스트는 계산·누락값·해시·자료 식별값·제출·재제출·복원을 포함합니다. Windows 검증 중 발견한 테스트 파일의 인코딩과 읽기 전용 Git 객체 처리도 수정했습니다.

실제 Codex 로그인과 도구 실행을 포함한 수강생 리허설은 Linux VM에서 수행했습니다. Windows와 macOS 검사는 자동 테스트이며, 해당 OS의 실제 Codex 로그인·GUI 실행을 대신하지 않습니다.

현재 호스트는 bwrap의 사용자 네임스페이스 생성이 제한되어 있습니다. 로그인만으로는 발견되지 않아 doctor에 모델 호출 없는 샌드박스 실행 점검을 추가했습니다. 이 호스트에서 FAIL을 확인했고, 샌드박스가 정상 동작하는 VM에서는 PASS를 확인했습니다.

제공된 수업용 작업 로그는 계속 **재구성 자료**입니다. 이 문서의 실제 실행 검증은 도구와 수강생 흐름에 대한 것이며, 교육용 토큰·시간을 실측값으로 바꾸었다는 뜻은 아닙니다.
