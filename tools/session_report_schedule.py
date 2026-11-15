"""Run reports only when a completed session needs collection or correction."""
import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weekend_report import ROOT, SESSION_NAMES, fetch, load_json, stamp


def due_meeting(sessions, reports, now):
    due = []
    for session in sessions:
        if session.get("session_name") not in SESSION_NAMES or session.get("is_cancelled"):
            continue
        end = stamp(session["date_end"])
        # Allow API publication time and retry failures for a week.
        if not end + timedelta(minutes=30) <= now <= end + timedelta(days=7):
            continue
        path = reports / f"weekend-{session['meeting_key']}" / "data" / f"{session['session_key']}.json"
        try:
            snapshot = load_json(path)
            collected = stamp(snapshot["fetched_at"])
            complete = all(snapshot.get("data", {}).get(k) for k in ("drivers", "laps", "session_result"))
        except (OSError, ValueError, KeyError, TypeError):
            collected, complete = None, False
        checkpoints = [end + timedelta(minutes=30), end + timedelta(hours=2), end + timedelta(hours=24)]
        target = max(t for t in checkpoints if t <= now)
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
    meeting = args.meeting if args.manual else due_meeting(fetch("sessions", {"year": now.year}), args.reports, now)
    run = args.manual or meeting is not None
    output = f"run={'true' if run else 'false'}\nmeeting={meeting or ''}\n"
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()
