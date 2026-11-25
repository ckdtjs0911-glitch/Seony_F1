# OpenF1 API

## 보고서 보조 참고 자료: Fast-F1

[theOehrly/Fast-F1](https://github.com/theOehrly/Fast-F1) 소스를
`vendor/Fast-F1` Git submodule로 연결했습니다. 원본의 문서·예제·MIT 라이선스를
유지하며, 랩·섹터·타이어·텔레메트리 분석을 위한 보조 자료로 참고합니다.
실제 데이터 사용 기준은 `AGENTS.md`의 보고서 참고 자료 규칙을 따릅니다.
실제 연결 도구는 `tools/fastf1_source.py`입니다. 새 세션 보고서 생성 시 일정·공개 결과를
조회하고, 접근 가능한 경우 랩·텔레메트리를 수집·대조합니다. 상세 서버가 401을 반환하면
인증 대기로 구분하고 기존 OpenF1 기록을 보존합니다. F1 TV 인증 없이 결과만 조회한 상태를
랩·텔레메트리 연결 완료로 표시하지 않습니다.

```bash
python -m pip install ./vendor/Fast-F1
python tools/fastf1_source.py --snapshot reports/weekend-1300/data/11420.json
```

계정 인증은 운영자가 별도로 구성한 뒤 `--authenticated`로 사용합니다. 암호·토큰은 저장소에
넣지 않습니다. 상세 응답 캐시는 Git에서 제외된 `.cache/fastf1/`에 보관합니다.

소스를 함께 내려받으려면:

```bash
git clone --recurse-submodules https://github.com/ckdtjs0911-glitch/Seony_F1.git
```

기존 작업 폴더에서는 `git submodule update --init --recursive`로 준비할 수 있습니다.

## Seony_F1 주말 보고서 자동화

**프랙티스 1·2·3 + 퀄리파잉 + 레이스 + 스프린트 세션**, 모든 선수의 결과와 랩·타이어 데이터를
수집해 HTML 보고서를 생성합니다. [자동 실행과 사용 방법](reports/AUTOMATION.md)을 참고하세요.
GitHub Actions는 한국 시간 금~월에만 저장된 일정을 확인하고(외부 API 호출 없음), 각 세션 종료 3시간 후
한 번만 해당 세션 자료를 조회해 보고서와 원본 스냅샷을 저장합니다. 실패 재시도는 수동 실행으로 합니다. 세션이 없는 날과 데이터에 변경이 없을 때는 보고서를 갱신하지 않습니다.

**OpenF1** is a free and open-source API that offers real-time and historical Formula 1 data.<br />
Whether you're a developer, data analyst, or F1 enthusiast, OpenF1 provides comprehensive
access to lap timings, car telemetry, driver information, race control messages, and more.

Explore the data through JSON or CSV formats to build dashboards, analyze races, or
integrate F1 data into your projects.

For full API documentation, visit [openf1.org](https://openf1.org).

## Key Features

- **Real-Time Data**: Stay updated with live lap times, speeds, and driver positioning.
- **Historical Data**: Analyze past races, compare performance over seasons, and dive deep into race strategy.
- **Car Telemetry**: Access in-depth car data, including throttle, brake, DRS, and gear information.
- **Driver Information**: Get details on F1 drivers, including team affiliations and performance metrics.

## Example Usage

Here’s a quick example of how to fetch lap data for a specific driver using the API:

```bash
curl "https://api.openf1.org/v1/laps?session_key=9161&driver_number=63&lap_number=8"
```

For more detailed examples and documentation, visit the [API Documentation](https://openf1.org).

## Running the project locally

1. Install and start [MongoDB Community Server](https://www.mongodb.com/try/download/community) v7 or v8

2. Install pip>=23 and python>=3.10

3. Install the OpenF1 python package

```bash
git clone git@github.com:br-g/openf1.git
pip install -e openf1
```

4. Configure the MongoDB connection

Set the **MONGO_CONNECTION_STRING** environment variable to connect to your local MongoDB instance:

```bash
export MONGO_CONNECTION_STRING="mongodb://localhost:27017"
```

5. Run the project

- Fetch and ingest scraped data: [services/f1_scraping/](src/openf1/services/f1_scraping/README.md)
- Fetch and ingest live timing data: [services/ingestor_livetiming/](src/openf1/services/ingestor_livetiming/README.md)
- Start and query the API: [services/query_api/](src/openf1/services/query_api/README.md)

## Supporting OpenF1

If you find this project useful, consider supporting its long-term sustainability:

<div>
  <a href="https://www.buymeacoffee.com/openf1" target="_blank" style="text-decoration:none; border:none;">
    <img src="https://storage.googleapis.com/openf1-public/images/bmec_button.png" alt="Buy Me A Coffee" height="32" style="border:none; vertical-align:middle;">
  </a>
  &nbsp;
  <a href="https://github.com/sponsors/br-g" style="text-decoration:none; border:none;">
    <img src="https://img.shields.io/badge/Sponsor-%E2%9D%A4-brightgreen" alt="Sponsor me" height="32" style="border:none; vertical-align:middle;">
  </a>
</div>

## Disclaimer

OpenF1 is an unofficial project and is not affiliated with Formula 1 companies.
All F1-related trademarks are owned by Formula One Licensing B.V.

## Seony_F1: hosted OpenF1 API connection

Fetch historical lap data directly from the hosted API using the existing Python client.
No local MongoDB server or API key is required for this example.

```bash
python -m venv .venv
.venv/bin/pip install requests==2.32.4
.venv/bin/python fetch_laps.py --session 9161 --lap 8
```

All drivers are included by default. Add `--driver 63` to select one driver.
The command prints the API response as JSON and exits with an error if the request fails.
Requests time out after 30 seconds. Live data requires the appropriate OpenF1 subscription
and credentials; existing `OPENF1_CLIENT_ID` and `OPENF1_CLIENT_SECRET` bindings are supported.

## 데이터 비교 영상

지도와 차량 비교는 기본 4배속입니다. 브라질·라스베가스 일반 퀄리파잉에도 단계별 위치
재생을 제공하며 Q1·Q2·Q3를 선택할 수 있습니다. 단계 1위와의 최고 랩 차이를 표시하고,
레이스의 앞차 주행 간격과 구분합니다. 레이스 상황은 원문 대신 한국어 타임라인 카드로 표시합니다.

현재 라스베가스와 브라질 레이스에 적용합니다. 재생 속도는 1·4·8·16·32배속이며,
순위 흐름 MP4는 별도로 0.25~2배속(0.25 간격)을 선택합니다. 이름표의 배경 상자는 없습니다.
지도 옆 간격은 원형으로 표시합니다. 순위 영상 이름표는 그래프 오른쪽 끝에서 움직입니다.
피트 기록이 있는 랩은 PIT LAP으로 강조하며, 별도 피트 경로가 확인되지 않으면 그리지 않습니다.

두 선수 비교와 순위 MP4는 레이스에만 표시합니다. 선수 두 명과 공통 랩을 선택하면 같은 UTC 시각의 차량 데이터를
음소거 자동 재생합니다. 재생·일시정지·탐색·1/4/8/16/32배속을 지원하며 모든 자료는 HTML 안에
포함됩니다. DRS 누락 항목은 숨깁니다. 순위 흐름 영상의 이름표는 순위 변화에 따라 이동합니다.

레이스 보고서에 시간별 가로형 서킷·간격 보기와 앞차 간격(s)을 담은 순위 흐름(30초)을 내장합니다.
그 아래에는 두 선수를 선택하는 차량 비교 재생이 있으며 고정 1·2위 비교 MP4는 표시하지 않습니다.
HTML 파일 하나로 영상 재생과 MP4 다운로드가 가능합니다. 원본 응답과 출처는 해당 주말의
`media/`에 보관합니다. 방송 영상은 사용하지 않습니다.

```bash
python -m pip install -r tools/video-requirements.txt
python tools/report_video.py --snapshot reports/weekend-1300/data/11420.json
```

동기화는 같은 UTC 시각에 가장 최근 관측된 차량 샘플을 사용하며, 1초 넘는 공백은 미제공입니다.
브레이크는 사용 여부이고 압력이 아닙니다. 랩 차트는 우승자의 각 랩 완료 시각의 순위를
표시하며 피트·리타이어 등을 포함하므로 실제 추월 횟수로 해석하지 않습니다.
같은 원본과 생성기 버전이면 다시 생성하지 않습니다. `--offline`은 저장 원본으로만 실행합니다.
