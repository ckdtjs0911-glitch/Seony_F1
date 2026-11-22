"""Run reports only when a completed session needs collection or correction."""
import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

from weekend_report import ROOT, SESSION_NAMES, fetch, load_json, stamp


def session_catalog(reports, now):
    try:
        return fetch("sessions", {"year": now.year})
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 401:
            raise
        # A year-wide query can include live sessions. Cached metadata is only
        # used to schedule historical collection, never as newly collected data.
        path = reports / "catalog" / "sessions.json"
        if not path.exists():
            raise
        print("OpenF1 authentication restriction: using saved session schedule.")
        return load_json(path)


def due_meeting(sessions, reports, now):
    due = []
    for session in sessions:
        if session.get("session_name") not in SESSION_NAMES or session.get("is_cancelled"):
            continue
        end = stamp(session["date_end"])
        # Process only in the first hour after the requested one-hour delay.
        if not end + timedelta(hours=1) <= now < end + timedelta(hours=2):
            continue
        path = reports / f"weekend-{session['meeting_key']}" / "data" / f"{session['session_key']}.json"
        try:
            snapshot = load_json(path)
            collected = stamp(snapshot["fetched_at"])
            complete = all(snapshot.get("data", {}).get(k) for k in ("drivers", "laps", "session_result"))
        except (OSError, ValueError, KeyError, TypeError):
            collected, complete = None, False
        target = end + timedelta(hours=1)
        if not complete or collected is None or collected < target:
            due.append(session)
    return min(due, key=lambda s: stamp(s["date_end"]))["meeting_key"] if due else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=ROOT / "reports")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--meeting", type=int)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    meeting = args.meeting if args.manual else due_meeting(session_catalog(args.reports, now), args.reports, now)
    run = args.manual or meeting is not None
    output = f"run={'true' if run else 'false'}\nmeeting={meeting or ''}\n"
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()
