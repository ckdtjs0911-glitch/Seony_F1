# F1 주말 보고서 자동화

대상: **Practice 1 / Practice 2 / Practice 3 / Qualifying / Race**.
각 세션에서 전체 선수의 결과, 랩 기록, 타이어 스틴트, 피트 진입을 수집합니다.
스프린트는 대상에 포함하지 않으며 개최되지 않은 세션은 API 목록 없음으로 표시합니다.

## GitHub Actions

`.github/workflows/weekend-report.yml`이 기본 브랜치에 반영되면 매일 한국 시간
**00:17 / 06:17 / 12:17 / 18:17**에 최신 시작된 주말을 조회합니다.
GitHub 예약 실행은 지연될 수 있습니다. 세션 예정 종료 후 30분부터 수집하며,
첫 성공 후에도 재조회하여 늦은 결과 및 삭제 랩 데이터를 갱신합니다.

GitHub → Actions → **F1 weekend reports** → **Run workflow**로 수동 실행할 수 있습니다.
특정 주말은 `meeting`에 OpenF1 meeting_key를 입력합니다. 멕시코 2026은 `1298`입니다.

출력: `reports/weekend-<meeting_key>/weekend-report.html` 및 `data/<session_key>.json`.
성공하면 봇이 결과를 저장소에 커밋합니다. 실행 결과 파일은 Actions artifact로도
30일간 보관합니다. 웹사이트 배포나 환경 게시는 수행하지 않습니다.

처음에는 저장소의 Actions가 활성화되어 있어야 합니다. 저장소 정책에서 Actions의
콘텐츠 쓰기를 제한하면 자동 커밋은 실패하지만 artifact는 다운로드할 수 있습니다.
포크 저장소는 예약 워크플로 활성화가 필요할 수 있습니다.

## 인증과 실패 처리

과거 데이터는 보통 인증 없이 조회할 수 있지만, 라이브 세션 진행 중에는 과거 데이터까지
인증이 요구될 수 있습니다. 이 경우 실패를 기록하고 기존 성공 스냅샷을 유지하며
다음 예약 실행에서 다시 시도합니다. 429 및 일시적인 서버 오류는 실행 중에도 재시도합니다.

OpenF1 구독 인증을 사용할 경우 저장소 Actions secrets에 `OPENF1_CLIENT_ID`와
`OPENF1_CLIENT_SECRET`을 설정합니다. 값은 파일이나 커밋에 넣지 않습니다.
정상 세션은 수집하되 일부 세션이 실패하면 실행은 실패로 표시하고 해당 실행의
artifact에 부분 결과를 남깁니다. 부분 결과는 저장소에 자동 커밋하지 않습니다.

## 로컬 실행

```bash
python -m venv .venv
.venv/bin/pip install requests==2.32.4
.venv/bin/python tools/weekend_report.py
.venv/bin/python tools/weekend_report.py --meeting 1298
.venv/bin/python tools/weekend_report.py --offline reports/weekend-1298
.venv/bin/python -m unittest discover -s tools -p 'test_weekend_report.py'
```

퀄리파잉 단계별 기록은 API duration 배열 기준입니다. 단계 자료가 없는 경우 추정하지
않습니다. 롱런 참고 중앙값은 연료·SC·트래픽을 보정하지 않으며 표본 수를 병기합니다.
공식 판정 및 FIA 문서와의 별도 대조는 하지 않습니다.

현재 제공된 멕시코 예시에는 이전에 수집한 레이스 22명만 포함되어 있습니다.
FP1·FP2·FP3·퀄리파잉은 API 라이브 접근 제한 해제 후 온라인 수집이 필요합니다.
