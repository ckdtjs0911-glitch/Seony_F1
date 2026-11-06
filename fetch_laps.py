"""Fetch OpenF1 lap data: python fetch_laps.py --session 9161 --lap 8."""

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from openf1.util import openf1_client  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="OpenF1 랩 데이터 조회 (기본: 모든 드라이버)")
    parser.add_argument("--session", type=int, default=9161)
    parser.add_argument("--lap", type=int, default=8)
    parser.add_argument("--driver", type=int, help="생략하면 모든 드라이버 조회")
    args = parser.parse_args()
    params = {"session_key": args.session, "lap_number": args.lap}
    if args.driver is not None:
        params["driver_number"] = args.driver
    try:
        data = openf1_client.get("v1/laps", params=params)
    except (requests.RequestException, ValueError) as exc:
        print(f"OpenF1 조회 실패: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
