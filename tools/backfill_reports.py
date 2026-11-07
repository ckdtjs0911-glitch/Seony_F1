"""Collect all finished report sessions in the rolling window, one meeting per batch."""
import argparse
import gzip
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

import requests
import weekend_report as report
from build_archive import build
from retention import first_year, prune


def run(reports, raw, missing_only=False):
    prune(reports, raw)
    sessions = report.load_json(reports / "catalog" / "sessions.json")
    now = datetime.now(timezone.utc)
    meetings = defaultdict(list)
    for session in sessions:
        if (
            session["year"] >= first_year()
            and report.stamp(session["date_end"]) < now
            and not session.get("is_cancelled")
        ):
            meetings[session["meeting_key"]].append(session)
    raw.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(raw / "manifest.sqlite")
    db.execute(
        "CREATE TABLE IF NOT EXISTS downloads (job TEXT PRIMARY KEY, status TEXT, records INTEGER, bytes INTEGER, sha256 TEXT)"
    )
    for index, (meeting, items) in enumerate(sorted(meetings.items()), 1):
        if all(
            (session["year"] < now.year or missing_only)
            and (
                reports
                / f"weekend-{meeting}"
                / "data"
                / f'{session["session_key"]}.json'
            ).exists()
            for session in items
        ):
            print(
                f"MEETING {index}/{len(meetings)}: {meeting} already archived",
                flush=True,
            )
            continue
        print(f"MEETING {index}/{len(meetings)}: {meeting}", flush=True)
        grouped = {s["session_key"]: {} for s in items}
        missing = []
        for endpoint in report.ENDPOINTS:
            try:
                values = report.fetch(endpoint, {"meeting_key": meeting})
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code != 404:
                    raise
                missing.append(endpoint)
                values = []
            for record in values:
                key = record.get("session_key")
                if key in grouped:
                    grouped[key].setdefault(endpoint, []).append(record)
            print(f"{meeting}/{endpoint}: {len(values)} records", flush=True)
        for session in items:
            key = session["session_key"]
            data = {e: grouped[key].get(e, []) for e in report.ENDPOINTS}
            if not any(data.values()):
                continue
            for endpoint, values in data.items():
                if endpoint in missing:
                    continue
                path = raw / str(key) / (endpoint + ".json.gz")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                with gzip.open(temporary, "wt", encoding="utf-8") as f:
                    json.dump(
                        {
                            "endpoint": endpoint,
                            "params": {"session_key": key},
                            "fetched_at": now.isoformat(),
                            "data": values,
                        },
                        f,
                        ensure_ascii=False,
                    )
                temporary.replace(path)
                content = path.read_bytes()
                db.execute(
                    "INSERT OR REPLACE INTO downloads VALUES (?,?,?,?,?)",
                    (
                        f"{key}/{endpoint}",
                        "complete" if values else "empty",
                        len(values),
                        len(content),
                        hashlib.sha256(content).hexdigest(),
                    ),
                )
            report.save_json(raw / str(key) / "session.json", session)
            status = (
                "보고서 데이터 수집 완료 / 텔레메트리는 별도 수집"
                if not missing
                else "부분 수집 · API 미제공: " + ", ".join(missing)
            )
            report.save_json(
                reports / f"weekend-{meeting}" / "data" / f"{key}.json",
                {
                    "session": session,
                    "status": status,
                    "fetched_at": now.isoformat(),
                    "data": data,
                },
            )
        db.commit()
        if index % 10 == 0:
            build(reports)
    db.close()
    build(reports)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-catalog", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_catalog:
        for endpoint in ("meetings", "sessions"):
            report.save_json(
                report.ROOT / "reports" / "catalog" / (endpoint + ".json"),
                report.fetch(endpoint, {}),
            )
    run(report.ROOT / "reports", report.ROOT.parent / "openf1-data", args.missing_only)
