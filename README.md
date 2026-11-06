# OpenF1 API

## Seony_F1 주말 보고서 자동화

**프랙티스 1·2·3 + 퀄리파잉 + 레이스**, 모든 선수의 결과와 랩·타이어 데이터를
수집해 HTML 보고서를 생성합니다. [자동 실행과 사용 방법](reports/AUTOMATION.md)을 참고하세요.
GitHub Actions는 6시간마다 데이터를 갱신하며, 보고서와 원본 스냅샷을 저장합니다.

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
