# F1 주말 보고서 자동화

대상: **Practice 1 / Practice 2 / Practice 3 / Qualifying / Race**.
각 세션에서 전체 선수의 결과, 랩 기록, 타이어 스틴트, 피트 진입을 수집합니다.
스프린트는 대상에 포함하지 않으며, 열리지 않은 세션은 '일정 없음 / API 목록에 없음'으로 표시합니다.

## GitHub Actions

`.github/workflows/weekend-report.yml`이 기본 브랜치에 반영되면 6시간마다
(UTC **00:17 / 06:17 / 12:17 / 18:17**, 한국 시간 **03:17 / 09:17 / 15:17 / 21:17**)
가장 최근에 시작된 주말을 조회합니다. GitHub 예약 실행은 지연될 수 있습니다.
각 세션은 예정 종료 30분 후부터 수집하며, 첫 수집에 성공한 뒤에도 다시 조회해
늦게 들어온 결과와 삭제된 랩 데이터를 갱신합니다.

GitHub → Actions → **F1 weekend reports** → **Run workflow**로 수동 실행할 수 있습니다.
특정 주말을 수집하려면 `meeting`에 OpenF1 meeting_key를 입력합니다. 멕시코 2026은 `1298`입니다.

출력: `reports/weekend-<meeting_key>/weekend-report.html`과 `data/<session_key>.json`.
수집에 성공하면 봇이 결과를 저장소에 커밋합니다. 실행 결과 파일은 Actions artifact로도
30일간 보관합니다. 웹사이트 배포나 외부 게시는 하지 않습니다.

처음 사용할 때는 저장소의 Actions가 활성화되어 있어야 합니다. 저장소 정책에서 Actions의
콘텐츠 쓰기 권한을 제한하면 자동 커밋은 실패하지만 artifact는 내려받을 수 있습니다.
포크한 저장소에서는 예약 워크플로를 따로 활성화해야 할 수 있습니다.

## 인증과 실패 처리

과거 데이터는 보통 인증 없이 조회할 수 있지만, 라이브 세션이 진행되는 동안에는 과거 데이터에도
인증을 요구할 수 있습니다. 이 경우 실패를 기록하고 마지막으로 성공한 스냅샷을 유지한 채
다음 예약 실행에서 다시 시도합니다. 429와 일시적인 서버 오류는 같은 실행 안에서도 재시도합니다.

OpenF1 구독 인증을 사용하려면 저장소 Actions secrets에 `OPENF1_CLIENT_ID`와
`OPENF1_CLIENT_SECRET`을 설정합니다. 이 값은 파일이나 커밋에 넣지 않습니다.
일부 세션만 실패하면 정상 세션은 수집하되 실행 자체는 실패로 표시하고, 해당 실행의
artifact에 부분 결과를 남깁니다. 부분 결과는 저장소에 자동 커밋하지 않습니다.

## 로컬 실행

macOS / Linux:

```bash
python -m venv .venv
.venv/bin/pip install requests==2.32.4
.venv/bin/python tools/weekend_report.py
.venv/bin/python tools/weekend_report.py --meeting 1298
.venv/bin/python tools/weekend_report.py --offline reports/weekend-1298
.venv/bin/python -m unittest discover -s tools -p 'test_weekend_report.py'
```

Windows (PowerShell)에서는 `.venv/bin/` 대신 `.venv\Scripts\`를 사용합니다.

```powershell
python -m venv .venv
.venv\Scripts\pip install requests==2.32.4
.venv\Scripts\python tools\weekend_report.py --offline reports\weekend-1298
.venv\Scripts\python -m unittest discover -s tools -p "test_weekend_report.py"
```

`--offline`은 네트워크 없이 `data/` 폴더의 스냅샷만으로 보고서를 다시 만듭니다.

## 보고서 UI

- 세션별 결과표는 10명씩 나눠 보여 주며, 이전/다음 버튼과 구간 버튼으로 이동합니다.
- 검색은 전체 선수를 대상으로 하며, 인쇄할 때는 모든 선수를 표시합니다.
- 랩타임·섹터 차트는 FP1/FP2/FP3/퀄리파잉/레이스 탭과 드라이버 선택으로 탐색합니다.
- 점에 마우스를 올리거나 터치하거나 키보드로 포커스를 주면 0.001초 단위 시간이 표시됩니다.
- 섹터 1·2·3은 차트를 따로 제공하며, 누락된 값은 0초로 대체하지 않습니다.
- 차트 스타일과 스크립트는 `tools/report_charts.css`, `tools/report_charts.js`에 있으며, 보고서를 만들 때 HTML 안에 포함됩니다.

## 해석 기준

퀄리파잉 단계별 기록은 API의 duration 배열을 기준으로 하며, 단계 자료가 없으면 추정하지
않습니다. 롱런 참고 중앙값은 연료·SC·트래픽을 보정하지 않으며 표본 수를 함께 표시합니다.
공식 판정이나 FIA 문서와 별도로 대조하지 않습니다.

현재 저장된 멕시코 예시(`weekend-1298`)에는 이전에 수집한 레이스 22명 데이터만 있습니다.
FP1·FP2·FP3·퀄리파잉은 API 라이브 접근 제한이 풀린 뒤 온라인으로 수집해야 합니다.

## 자동 AI 교차 첨삭

두 API 키가 모두 설정된 경우 새 데이터를 수집한 뒤 **Codex 초안 → Claude 첨삭 → Codex 최종 검증**을 순서대로
API로 실행합니다. Windows에서 로그인한 Claude Code 프로그램을 원격 실행하는 방식은
아니며, 구독 로그인과 별도의 OpenAI·Anthropic API 과금이 적용됩니다.

저장소 Settings → Secrets and variables → Actions → **New repository secret**에 등록:

- `OPENAI_API_KEY`: OpenAI API 키
- `ANTHROPIC_API_KEY`: Anthropic API 키

키 값은 채팅·코드·커밋에 넣지 않습니다. 현재 클라우드 환경이 아닌 **GitHub 저장소의
Actions secrets**에 설정해야 예약 작업에서 사용할 수 있습니다.
모델은 기본 `gpt-5.1-codex`, `claude-sonnet-4-5`를 사용하며, 계정에서 접근 가능한 모델로
바꾸려면 Actions variables에 `REPORT_CODEX_MODEL`, `REPORT_CLAUDE_MODEL`을 설정합니다.
키가 없으면 AI 첨삭을 건너뛰고 기본 보고서를 정상 저장합니다. 인증 오류·API 한도·모델 거부·
출력 검증 실패 시에도 첨삭 전 기본 보고서를 저장하고 상태를 명시합니다. 키를 추가하면
다음 실행부터 AI 첨삭이 적용됩니다. OpenF1 수집 자체가 실패한 경우에는 기존 보고서를 유지합니다.

AI는 원본에서 계산한 사실 문장의 표현을 작성·첨삭하며, 수치와 선수명은 보호 토큰으로
유지한 뒤 코드가 삽입합니다. 표·차트·데이터 계산 코드 자체를 AI가 자동 수정하지 않습니다.
Claude의 구조·UI 검토 의견은 `editorial-review.json`에 남기고, 코드 수정이 필요한 사항은
별도 개발 검토 대상으로 유지합니다. 교차 검토는 공식 기록 확인을 대신하지 않습니다.

수집 결과는 먼저 `.report-staging/`에서 생성됩니다. AI 첨삭이 성공하면 첨삭본을,
키가 없거나 AI 첨삭이 실패하면 기본 보고서를 `reports/`로 옮겨 자동 커밋합니다.
실패한 AI 문장은 반영하지 않으며, `editorial-review.json`과 HTML에 미첨삭 상태를 기록합니다.
예약 실행은 `--optional` 모드이며, 옵션 없이 직접 실행하면 기존의 엄격 검증 모드를 사용할 수 있습니다.
동일한 데이터·세션 상태·생성 코드·모델의 승인 기록이 있으면 재사용하여 중복 API 호출을 줄입니다.
새 데이터마다 보통 API 세 번을 호출합니다. 원본 전체 랩 배열 대신 요약 사실만 전송합니다.
각 단계의 출력·모델·검토 시각을 해당 주말의 `editorial-review.json`에 보관합니다.

로컬 검증:

```bash
.venv/bin/python -m unittest discover -s tools -p 'test_*.py'
```

## 사용 타이어와 선수별 한줄 평

랩타임 및 섹터 차트의 점은 사용 타이어 색상으로 표시합니다: H 하드(흰색),
M 미디엄(노란색), S 소프트(빨간색), I 인터미디어트(초록색), W 웨트(파란색).
툴팁에는 정확한 시간과 타이어 코드·이름을 함께 표시합니다. 삭제 랩은 빨간 테두리입니다.
타이어는 stints의 명시된 lap_start/lap_end 범위에 연결합니다. 서로 다른 타이어 범위가
겹치거나 경계·정보가 불명확하면 미확인으로 표시하며, 섹터별로 타이어를 따로 추정하지 않습니다.

선수별 한줄 평은 각 세션의 전체 선수에게 관측 최속·기록 수·API 결과 등의 사실로
생성합니다. 주관적인 실력 평가나 원인 추정은 하지 않습니다. 별도 표에서 10명씩
페이지를 넘기며 전체 검색·인쇄에도 포함됩니다. API 키 없이 생성됩니다.

## 한글 검색

전체 표 검색에서 팀·선수의 주요 한글 표기를 영문 이름으로 연결합니다.
예: `멕라렌`/`맥라렌` → McLaren, `노리스` → Norris,
`키미 안토렐리`/`안토넬리` → Kimi Antonelli, `아이작하자` → Isack Hadjar.
현재 보고서 선수 전체의 성씨와 주요 이름 변형을 지원하며 영문·띄어쓰기 없는 검색도 유지합니다.
이는 등록된 별칭 검색으로, 임의의 모든 오타를 자동 교정하는 기능은 아닙니다.

랩타임·섹터 분석의 검색창도 같은 한글·영문 별칭을 지원합니다. 현재 세션의 선수 목록만
필터링하고 세션을 바꿔도 검색어를 유지하며, 상단 전체 표 검색과는 독립적으로 동작합니다.
