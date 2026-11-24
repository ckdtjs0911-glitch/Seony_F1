# OpenF1 API

## 보고서 보조 참고 자료: Fast-F1

[theOehrly/Fast-F1](https://github.com/theOehrly/Fast-F1) 소스를
`vendor/Fast-F1` Git submodule로 연결했습니다. 원본의 문서·예제·MIT 라이선스를
유지하며, 랩·섹터·타이어·텔레메트리 분석을 위한 보조 자료로 참고합니다.
실제 데이터 사용 기준은 `AGENTS.md`의 보고서 참고 자료 규칙을 따릅니다.
이 연결만으로 자동 수집이 실행되거나 기존 보고서 데이터가 바뀌지는 않습니다.

소스를 함께 내려받으려면:

```bash
git clone --recurse-submodules https://github.com/ckdtjs0911-glitch/Seony_F1.git
```

기존 작업 폴더에서는 `git submodule update --init --recursive`로 준비할 수 있습니다.

## Seony_F1 주말 보고서 자동화

**프랙티스 1·2·3 + 퀄리파잉 + 레이스 + 스프린트 세션**, 모든 선수의 결과와 랩·타이어 데이터를
수집해 HTML 보고서를 생성합니다. [자동 실행과 사용 방법](reports/AUTOMATION.md)을 참고하세요.
GitHub Actions는 세션 종료 여부를 15분마다 확인하고, 각 세션의 예정 종료 1시간 후부터
보고서와 원본 스냅샷을 저장합니다. 세션이 없는 날과 데이터에 변경이 없을 때는 보고서를 갱신하지 않습니다.

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

레이스 보고서에 OpenF1 차량 데이터 비교(32초)와 전체 선수 랩별 순위 흐름(30초)을 내장합니다.
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
