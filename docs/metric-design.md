# 지표 설계와 계산 형식

지표의 목적은 제공된 작업 방식의 차이를 평가하고, 담당 업무에 필요한 판단 근거를 만드는 것입니다. 계산 결과의 차이뿐 아니라 그 차이가 무엇을 의미하는지 설명해야 합니다.

## 설계할 내용

1. 담당 업무에서 확인할 내용을 정합니다. 예를 들어 작업 시간 제한, 불필요한 재시도, 성공한 결과를 얻는 데 드는 자원 등이 있습니다.
2. 해당 내용을 평가할 측정값과 계산 방법을 선택합니다.
3. 계산 결과를 어떻게 해석할지 정하고, 같은 실행 기록에 적용합니다.
4. 지표가 드러낸 차이와 설명하지 못하는 차이를 실행 기록에서 확인합니다.

수강생은 계산 코드를 직접 작성하지 않습니다. Codex에 평가 목적을 설명하고 `metrics/my_metric.json`을 작성하거나 수정하도록 요청합니다. 이 파일은 아래 형식의 지표 정의이며 임의의 Python 코드를 실행하지 않습니다.

## 지표 정의 파일

| 항목 | 작성할 내용 |
|---|---|
| name | 지표 이름 |
| purpose | 담당 업무에서 무엇을 평가하려는지 |
| expression | 실행별 측정값으로 계산할 산술식 또는 비교식 |
| aggregation | 작업 방식별로 실행 값을 집계하는 방법 |
| unit | 계산 결과의 단위 |
| interpretation | 수치로 어떤 판단을 할지 |

계산식에 사용할 수 있는 이름은 `input_tokens`, `cached_input_tokens`, `output_tokens`, `elapsed_seconds`, `llm_calls`, `tool_calls`, `retries`, `success`, `estimated_cost`입니다. 없는 값이 필요한 계산은 미제공으로 처리합니다.

산술 연산 `+`, `-`, `*`, `/`, 괄호, 비교 연산 `>`, `>=`, `<`, `<=`, `==`, `!=`, 논리 연산 `and`, `or`, `not`을 지원합니다. 함수 호출, 파일 접근, 시나리오 이름에 따른 점수 지정은 지원하지 않습니다.

| aggregation | 의미 |
|---|---|
| mean | 실행별 계산값의 평균 |
| median | 중앙값 |
| sum | 합계 |
| min / max | 최솟값 / 최댓값 |
| percentage | 비교식이 참인 실행의 비율. 단위는 % |
| per_success | 모든 실행의 계산값 합계를 성공한 실행 수로 나눈 값 |

## 형식 예시

아래 120초는 형식 설명용 값입니다. 실제 지표에서는 담당 업무의 기준에 맞는 값을 정합니다.

```json
{
  "name": "작업 시간 제한 초과 비율",
  "purpose": "정해진 시간 안에 완료되는 작업의 비율을 평가",
  "expression": "elapsed_seconds > 120",
  "aggregation": "percentage",
  "unit": "%",
  "interpretation": "시간 제한을 넘긴 실행이 얼마나 자주 발생하는지 확인"
}
```

이 지표는 시간 제한을 평가하는 예이며, 모든 종류의 낭비를 설명하는 정답 지표가 아닙니다. 여러 재료를 조합할 때도 계산식의 단위와 해석 기준을 함께 확인합니다.

## 작업 구간의 측정값 활용

구간별 기록이 제공되면 해당 구간의 값을 계산식에 연결할 수 있습니다. 아래는 '자료 확인' 구간에 배분된 입력 토큰이 전체 입력에서 차지하는 비율의 형식 예시입니다. `phase`는 로그의 activity와 일치해야 합니다. 제공 자료에는 `자료 확인`, `검증 준비`, `구현`, `금액 검증`, `검증`, `결과 정리`가 있습니다. 기존 data/ 형식에서는 phases.jsonl의 phase를 사용합니다.

```json
{
  "name": "문서 조회 구간의 입력 비율",
  "purpose": "입력 자원이 문서 조회 구간에 집중되는 정도 확인",
  "phase_inputs": {
    "reading_input": {"phase": "자료 확인", "measure": "input_tokens"}
  },
  "expression": "100 * reading_input / input_tokens",
  "aggregation": "mean",
  "unit": "%",
  "interpretation": "배분 근거와 실제 조회 내용을 함께 보고 비율 차이의 원인을 확인"
}
```

`measure`에는 `input_tokens`, `output_tokens`, `elapsed_seconds`를 사용할 수 있습니다. 한 실행에 같은 이름의 구간이 여러 개 있으면 합산합니다. 해당 구간이 없거나 값이 누락되면 0으로 간주하지 않고 미제공으로 처리합니다. 구간 입력은 그 문서 자체의 순수 토큰 수가 아니며, 높은 비율만으로 불필요한 조회라고 단정할 수 없습니다.

## Codex 요청 예시

> 담당 업무에서 평가할 내용은 [평가 목적]입니다. docs/metric-design.md의 형식과 log_pairs/README.md의 측정값 정의를 확인하고, 이 목적에 맞는 metrics/my_metric.json을 작성해 주세요. 계산식과 집계 방식이 무엇을 의미하는지도 설명해 주세요. 원본 데이터는 수정하지 마세요.

계산 결과를 확인한 뒤에는 해당 지표로 드러나지 않는 차이를 검토하고 필요하면 정의를 보완합니다. 어떤 작업 방식이 1위인지 정하는 대신, 지표가 업무 판단에 필요한 차이를 설명하는지 확인합니다.

## 제공 로그에서 추가로 사용할 재료

기본 명령은 `log_pairs/`를 검증한 뒤 집계합니다. 미리 만들어 둔 `materials.json`의 숫자를 그대로 신뢰하지 않습니다. 아래 이름도 expression에 사용할 수 있습니다.

| 이름 | 의미 |
|---|---|
| `first_input_tokens` | 첫 요청의 입력 토큰 |
| `reasoning_output_tokens` | 교육 자료의 가정에 따라 부여한 추론 출력 토큰. 실제 내부 추론 측정값 아님 |
| `test_runs` | 테스트 실행 횟수 |
| `same_state_passed_rechecks` | 코드·테스트·데이터·환경·검증 범위가 같고 직전 통과 근거가 있는 재검증 횟수 |
| `document_lookups` | 조회한 문서 대상 수. 한 호출이 여러 문서를 읽으면 각각 집계 |
| `same_document_range_lookups` | 동일 문서 버전의 동일 범위 재조회 수 |
| `model_seconds`, `tool_seconds` | 모델 구간·도구 구간의 시간 합. 요청 전체 시간과 중복 합산하지 않음 |
| `calculation_items` | 서로 다른 금액 검증 입력 수. 네 사례 모두 8개 |
| `calculator_executions` | 금액 검증 도구 실행 횟수 |
| `calculation_explanation_occurrences` | 금액 검증 메시지의 사례 ID 등장 횟수. 숨겨진 추론 횟수 아님 |
| `calculation_input_tokens`, `calculation_output_tokens` | 금액 검증 요청의 입력·출력 토큰 |
| `calculation_seconds`, `calculation_cost` | 금액 검증 요청의 전체 시간·환산 비용 |

현재 자료의 `retries`는 **미제공**입니다. 반복 테스트와 실패 재시도를 같은 값으로 취급하지 않습니다. 반복 검증 비율은 `100 * same_state_passed_rechecks / test_runs`처럼 정의할 수 있습니다. 반복 자체가 불필요했는지는 로그를 보고 별도로 판단합니다.

구간 값은 한 요청의 전체 usage와 시간을 해당 activity에 배분합니다. 해당 문서 자체의 순수 토큰 수가 아닙니다. 토큰·시간은 재구성 과정의 모델값이고, 비용은 자료에 명시된 단가로 환산한 교육용 값입니다.
