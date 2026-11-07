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
