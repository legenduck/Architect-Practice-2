# 실습 2: 과정 지표로 Codex 작업 평가하기

같은 쿠폰 기능 과제의 네 작업 방식을 비교하고, 담당 업무에 맞는 평가 지표를 설계합니다. 성공률 → 정답 1개당 비용 → 작업 구간별 토큰·시간 → 직접 설계한 지표 순서로 살펴봅니다.

제공 자료는 **재구성한 교육용 로그**입니다. 최종 코드에는 독립 채점 근거가 있지만, 전체 작업 경로를 새로 실행한 기록은 아닙니다. 토큰과 시간은 계산·가정한 값이며 실제 서버 사용량·소요 시간·청구액이 아닙니다. [자료 생성 기준](log_pairs/manifest.json)을 함께 제공합니다.

## 시작하기

Python 3.10 이상, Git, 로그인한 Codex CLI를 준비합니다. GitHub collaborator 초대를 수락하고 Git 로그인을 마쳐 둡니다. 분석·계산 도구에는 추가 패키지나 API 키가 필요하지 않습니다.

```bash
git clone https://github.com/legenduck/Architect-Practice-2.git
cd Architect-Practice-2
python lab.py doctor
python lab.py enroll p01
python lab.py analyze
```

`p01`은 배정받은 참가자 번호로 바꿉니다. macOS/Linux에서 필요한 경우 `python3`, Windows에서 `py`를 사용합니다.

`doctor`는 자료의 연결·해시·집계, Codex 로그인·샌드박스 실행, Git 작성자와 제출 연결을 확인합니다. 실패한 항목에는 해결 방법이 표시됩니다. 원격 브랜치를 만들거나 모델을 호출하지 않습니다. 인터넷 없이 자료만 확인하려면 `python lab.py doctor --offline`을 사용할 수 있지만, 제출 연결은 온라인 doctor에서 확인해야 합니다.

생성된 **`output/report.html`을 브라우저로 엽니다.** 화면 안의 작업 기록 링크에서 메시지·명령·반환값까지 확인할 수 있습니다. 모든 명령은 기본적으로 제공된 `log_pairs/`를 읽습니다.

## 지표 설계와 적용

```bash
python lab.py new-metric
codex
```

Codex에 평가 목적을 설명하고 `metrics/my_metric.json`을 작성하도록 요청합니다. 예를 들어:

> 같은 코드·테스트·데이터·환경에서 이미 통과한 검증을 반복한 비율을 살펴보고 싶습니다. docs/metric-design.md를 읽고 이 목적에 맞게 metrics/my_metric.json을 수정해 주세요. 반복이 필요했는지는 수치만으로 단정하지 말고 해석의 한계에 적어 주세요. 원본 자료는 수정하지 마세요.

Codex를 종료한 뒤 적용합니다.

```bash
python lab.py analyze --metric metrics/my_metric.json
```

`output/report.html`을 새로 열어 네 작업 방식의 차이와 계산 근거를 확인합니다. 지표를 고치면 같은 명령으로 다시 계산할 수 있습니다. 기존 지표 파일이 있으면 `new-metric`을 다시 실행하지 않습니다.

## 제출과 공유

```bash
python lab.py submit
```

개인 `students/p01` 브랜치에 `submissions/metric.json`만 커밋하고 푸시합니다. 지표 정의·계산 결과·자료 식별값이 함께 제출됩니다. 수정 후 같은 명령으로 재제출할 수 있습니다.

강사 측 자동 수집은 공통 자료로 다시 계산하고 GitHub Actions의 **Collect student metrics → practice2-sharing**에 공유 자료를 남깁니다. 참가자 번호순으로 표시하며 자동 순위를 매기지 않습니다.

공유할 내용은 평가 목적, 계산 방법, 드러난 작업 차이, 해석의 한계입니다. 공개 저장소에는 실습용 기준만 작성하고 회사 기밀 자료를 넣지 않습니다.

## 안내

- [처음부터 제출까지 수강생 시나리오](docs/student-workflow.md)
- [지표 설계 형식·사용 가능한 측정값](docs/metric-design.md)
- [두 로그의 구조와 읽는 방법](log_pairs/README.md)
- [강사 준비·제출 수집](docs/instructor.md)
- [수강생용 슬라이드](slides/practice2-student.html)
- [강의용 슬라이드](slides/practice2-presenter.html)

15:30–16:30에는 비교·지표 설계·적용을 진행하며 **16:25까지 제출**합니다. 16:30–17:00에는 결과와 해석을 공유합니다.

<details>
<summary>기존 data/ 형식으로 수집한 자료 사용</summary>

기존 형식은 `python lab.py --data data analyze`처럼 자료 위치를 명시합니다. 현재 `data/`는 비어 있으며 기본 실습에 사용하지 않습니다. 형식 설명은 [data/README.md](data/README.md)를 참고하세요.

`python log_pairs/analyze.py`로 제공 로그의 미리보기와 집계 재료만 다시 생성할 수도 있습니다. 일반 실습은 위의 `lab.py` 흐름 하나로 진행합니다.

</details>
