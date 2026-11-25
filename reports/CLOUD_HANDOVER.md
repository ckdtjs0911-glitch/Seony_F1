# Seony_F1 클라우드 작업 인계

## 1. 작업 시작

`ckdtjs0911-glitch/Seony_F1`만 사용한다. 최신 main을 확인하고 `AGENTS.md`, `CLAUDE.md`, `reports/AUTOMATION.md`를 읽는다.
다른 저장소의 환경이 선택돼 있다면 그 저장소는 변경하지 않는다. 로컬 채팅 전체가 자동 이전된 것으로 가정하지 않는다.
코드·설정·원본 데이터·보고서의 기준은 GitHub이며 이 문서는 2026년 11월 25일 인계 기준이다.
클라우드 채팅은 [Seony_F1 클라우드 관리 인계](https://chatgpt.com/local/6b06caa4-c074-83ec-9116-af2eb62d90b1)다. 기본 클라우드 환경의 `/workspace/Seony_F1`에 저장소를 체크아웃하고 인계 문서를 읽은 것을 확인했다. 기존 로컬 예약 `f1-11-28`은 중복 실행 방지를 위해 일시 중지했다.

## 2. 자동 실행

- GitHub Actions `F1 weekend reports`가 저장된 일정만 확인한다. 외부 자료는 생성 대상 세션이 있을 때 한 번 가져온다.
- 자동 생성 재개는 2026년 11월 28일 00:00 KST이며 `.github/report-pause.json`의 `resume_at`이 기준이다.
- KST 금~월에 실제 열린 FP1·FP2·FP3·퀄리파잉·레이스·스프린트 퀄리파잉·스프린트 레이스가 대상이다. 종료 후 3시간 이상 4시간 미만에 첫 자동 시도를 한다.
- `actual_date_end` 등 명시된 실제 종료가 예정 시각보다 우선한다. 취소·일정 없음·이미 처리·변경 없음이면 보고서를 만들거나 전달하지 않는다.
- `reports/catalog/report-attempts.json`이 세션별 시도 기록이다. 인증 오류·누락·실패를 수집 완료로 기록하지 않고 자동 재조회하지 않는다. 재시도는 사용자 요청으로 한다.
- 저장된 일정이 없으면 상시 API 탐색을 시작하지 않는다. 2027년 등 다음 시즌 일정 추가는 명시적인 작업으로 처리한다.
- 주간 backfill 예약·2시간/24시간 후 정정 재조회는 켜지 않는다. 로컬 예약 또는 이 채팅에서 별도의 상시 폴링·중복 생성 루프를 만들지 않는다.

## 3. 데이터와 Claude

- OpenF1가 원본이다. FastF1은 `vendor/Fast-F1` 고정 submodule 및 `tools/fastf1_source.py`를 사용한다.
- 공개 일정·결과 조회는 확인됐으나 FastF1 상세 타이밍 서버는 401 인증 대기 상태다. 결과만 조회한 것을 상세 랩·텔레메트리 연결 완료로 쓰지 않는다.
- GitHub Claude 작업에는 저장소 secret `CLAUDE_CODE_OAUTH_TOKEN`이 필요하다. 2026년 11월 25일 [클라우드 점검 45607843927](https://github.com/ckdtjs0911-glitch/Seony_F1/actions/runs/45607843927)에서 secret 등록과 GitHub 실행기의 실제 Claude 호출 성공을 확인했다. 앞선 점검 명령의 CLI 인수 오류는 수정했다. 연결 점검은 보고서 첨삭 완료를 뜻하지 않으며, 각 보고서의 실제 검토 기록은 따로 확인한다.
- 같은 점검에서 OpenF1 client ID·client secret은 미등록이었다. 공개 접근 가능 데이터는 기존 경로를 사용하고 인증이 필요한 자료의 401은 미완료로 표시한다. 기존 전체 lint의 형식 오류도 남아 있으며 이번 전환에서 전체 lint 통과를 주장하지 않는다.
- 기존 `claude-report-review.yml`의 review·rescue·검증을 유지한다. 실제 Claude 작업 기록 없이 첨삭 완료라고 쓰지 않는다. 토큰·인증 파일은 저장소나 로그에 남기지 않는다.
- F1 COSMOS는 https://f1cosmos.com/ko 를 참고하되 실제 확인한 세션·항목만 출처로 기록한다. 리플레이 접근 실패와 순위 교환/실제 추월의 차이를 명시한다.

## 4. 이미 구현한 보고서

- 브라질: `reports/weekend-1299/` (퀄리파잉 11408, 레이스 11412).
- 라스베이거스: `reports/weekend-1300/` (퀄리파잉 11416, 레이스 11420). FP1 11413은 누락 상태다.
- 가로 서킷·청록색 피트 참고선·원형 시간차, 지도 기본 4배속, 한국어 상황 카드 줄바꿈, SC/VSC 상태 구분.
- 퀄리파잉 Q1/Q2/Q3 선택 및 그 시점까지 완료된 유효 최고 랩. 레이스 전용 순위 흐름 MP4와 두 선수 선택 비교.
- 순위 영상 이름표는 오른쪽 끝에서 세로 이동하며 배경 상자가 없다. 앞차 간격은 s 단위이고 실제 추월 횟수로 세지 않는다. 영상 배속 0.25~2, 지도/비교 배속 1·4·8·16·32.
- 음소거 자동 재생·반복, 누락 DRS 항목 숨김, 모든 항목별 출처는 본문·부록 뒤 맨 아래에 모은다.
- 이번 클라우드 전환 자체로 기존 HTML을 재생성하지 않는다.

## 5. 결과 확인과 전달

- [GitHub 실행 기록](https://github.com/ckdtjs0911-glitch/Seony_F1/actions/workflows/weekend-report.yml)
- [올해 보고서](https://htmlpreview.github.io/?https://github.com/ckdtjs0911-glitch/Seony_F1/blob/main/reports/current-year.html)
- [누적 보고서](https://htmlpreview.github.io/?https://github.com/ckdtjs0911-glitch/Seony_F1/blob/main/reports/index.html)
- [원본 HTML과 세션별 보고서](https://github.com/ckdtjs0911-glitch/Seony_F1/tree/main/reports)

GitHub 실행 요약에는 새 보고서가 저장된 실행에만 공개 링크를 제공한다. 외부 HTML Preview 렌더링을 확인하지 않았다면 정상 표시를 보장하지 않는다.
기존 로컬 채팅에 HTML을 자동 첨부하는 경로는 없다. 클라우드 채팅 생성과 기존 채팅의 전체 기록 이전도 별개의 작업이다.

## 6. 새 클라우드 채팅의 첫 요청

> ckdtjs0911-glitch/Seony_F1만 사용하고 최신 main의 reports/CLOUD_HANDOVER.md와 AGENTS.md, CLAUDE.md를 읽어 이전 작업을 이어받아줘. 먼저 인계 내용을 확인하고 한국어 번호 목록으로 상태를 알려줘. 지금은 보고서를 새로 생성하거나 API를 조회하지 말고 GitHub Actions가 자동 생성을 담당하게 유지해줘. 보고서 변경은 실제 새 정보 또는 명시적인 요청이 있을 때만 진행해줘.
