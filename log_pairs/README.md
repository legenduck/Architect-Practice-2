# 실습 2 작업 기록

`index.html`을 브라우저에서 열어 네 작업 방식을 비교합니다. 각 사례에서 `codex.jsonl`과 `harness.jsonl`을 함께 확인할 수 있습니다.

자료는 재구성한 교육용 로그이며 토큰·시간은 모델값입니다. 실제 서버 사용량·소요 시간·청구액이 아닙니다. 지표 설계와 제출은 저장소 루트의 [실습 안내](../README.md)에 따라 `python lab.py doctor`부터 진행합니다.

| 폴더 | 작업 방식 |
|---|---|
| cases/context_overload | 입력 컨텍스트 과다 |
| cases/repeated_work | 중복 전송과 재계산 |
| cases/reasoning_reliance | LLM 직접 계산 |
| cases/reference | 기법 적용 사례 |

## 두 로그 연결하기

| 항목 | 의미 |
|---|---|
| run_id | 한 실행 기록을 식별하는 값 |
| request_id | 한 모델 요청을 연결하는 값 |
| call_id | 한 도구 호출과 결과를 연결하는 값 |
| event_id | 개별 기록의 식별값 |
| call_event_id / result_event_id | 수집 기록이 가리키는 Codex 호출과 결과의 event_id |

`codex.jsonl`에는 모델 메시지, 도구 명령과 반환값, 요청별 사용량이 있습니다. `harness.jsonl`에는 상대 시각과 작업 전후 상태, 조회 대상과 검증 조건이 있습니다. 이 실습에서 사용할 공통 이벤트 형식이며 파일마다 첫 행에 형식과 출처 정보가 있습니다.

## 상태와 사용량 읽기

- `code_version`은 소스 코드, `tests_version`은 테스트 코드, `data_version`은 입력 데이터의 내용 식별값입니다. 작업 전후 값을 비교합니다.
- `state_id`는 `states/`의 파일 상태 목록을 가리킵니다. 파일 내용은 `objects/`에서 해당 해시의 파일로 확인합니다.
- `start_ms`, `end_ms`는 실행 시작부터의 상대 시각입니다. 요청 시간 안에 모델 처리와 도구 처리 시간이 들어 있으므로 세 값을 모두 더하지 않습니다.
- `input_tokens`에는 `cached_input_tokens`가 포함됩니다. `output_tokens`에는 `reasoning_output_tokens`가 포함됩니다.
- 같은 검증 대상이라도 코드, 테스트, 데이터 또는 환경이 달라졌는지 함께 확인합니다.

검증 실행 자체는 보통 코드를 바꾸지 않습니다. 재검증을 평가할 때는 앞선 검증의 대상 버전과 현재 검증의 대상 버전을 비교합니다.

## 지표 설계에 사용할 자료

`materials.json`은 두 로그를 연결해 집계한 재료입니다. 재조회와 같은 상태의 재검증 횟수, 금액 검증 구간의 사용량 등을 확인할 수 있습니다. 항목의 집계 기준도 이 파일에 있습니다. 이러한 횟수 자체가 낭비 여부에 대한 판정은 아닙니다.

집계와 연결 관계를 다시 확인하려면 이 README가 있는 폴더에서 실행합니다. Python 3.10 이상이며 추가 패키지는 필요하지 않습니다.

```bash
python analyze.py
```

`grading/`에는 참조한 최종 코드의 독립 채점 결과가 있습니다. `calculation_cases.json`에는 네 방식에서 비교하는 동일한 금액 검증 입력과 결과가 있습니다. 기록의 출처, 재구성 방식, 토큰 및 시간 구성 기준과 채점 근거의 범위는 `manifest.json`에 정리되어 있습니다.
