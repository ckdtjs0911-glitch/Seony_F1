"""Decide from local files only whether a finished session needs its one automatic report.

Automatic runs apply only on Friday-Monday in Korea Standard Time, to sessions whose
end is 3-4 hours ago and that have no recorded automatic attempt. This gate never
calls an external API; the collector fetches only the sessions it prints.
"""
import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import report_attempts
from weekend_report import ROOT, SESSION_NAMES, load_json, stamp

KST = timezone(timedelta(hours=9))
DELAY = timedelta(hours=3)
WINDOW = timedelta(hours=1)
AUTOMATIC_WEEKDAYS = (4, 5, 6, 0)  # Friday, Saturday, Sunday, Monday in KST


def session_catalog(reports):
    """Saved schedule only: catalog/sessions.json, then newer weekend-*/sessions.json."""
    sessions = {}
    paths = [Path(reports) / "catalog" / "sessions.json"]
    paths += sorted(Path(reports).glob("weekend-*/sessions.json"))
    for path in paths:
        try:
            value = load_json(path)
        except (OSError, ValueError):
            continue
        for session in value if isinstance(value, list) else []:
            if isinstance(session, dict) and session.get("session_key") is not None:
                sessions[session["session_key"]] = session
    return list(sessions.values())


def automatic_day(now):
    return now.astimezone(KST).weekday() in AUTOMATIC_WEEKDAYS


def session_end(session, attempt=None):
    """An explicit actual end (session metadata or a recorded later end) beats the scheduled end."""
    for value in (
        (attempt or {}).get("actual_end"),
        session.get("actual_date_end"),
    ):
        if value:
            return stamp(value)
    return stamp(session["date_end"])


def processed(session, reports, end):
    path = Path(reports) / f"weekend-{session['meeting_key']}" / "data" / f"{session['session_key']}.json"
    try:
        snapshot = load_json(path)
        collected = stamp(snapshot["fetched_at"])
        complete = all(snapshot.get("data", {}).get(k) for k in ("drivers", "laps", "session_result"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    return complete and collected >= end + DELAY


def due_sessions(sessions, reports, now):
    """Sessions of the earliest due meeting, 3-4 h after their end, not yet attempted."""
    if not automatic_day(now):
        return None, []
    attempts = report_attempts.load(reports)
    due = []
    for session in sessions:
        if session.get("session_name") not in SESSION_NAMES or session.get("is_cancelled"):
            continue
        attempt = attempts.get(str(session.get("session_key")))
        if attempt and attempt.get("status") != "deferred_end_later":
            continue
        try:
            end = session_end(session, attempt)
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if not end + DELAY <= now < end + DELAY + WINDOW:
            continue
        if processed(session, reports, end):
            continue
        due.append((end, session))
    if not due:
        return None, []
    meeting = min(due, key=lambda item: item[0])[1]["meeting_key"]
    keys = sorted(s["session_key"] for _, s in due if s["meeting_key"] == meeting)
    return meeting, keys


def due_meeting(sessions, reports, now):
    return due_sessions(sessions, reports, now)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=ROOT / "reports")
    parser.add_argument("--manual", action="store_true", help="Explicit user request; no weekday or window limit")
    parser.add_argument("--meeting", type=int)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.manual:
        meeting, keys = args.meeting, []
    else:
        meeting, keys = due_sessions(session_catalog(args.reports), args.reports, now)
    run = args.manual or meeting is not None
    output = (
        f"run={'true' if run else 'false'}\nmeeting={meeting or ''}\n"
        f"sessions={','.join(str(k) for k in keys)}\n"
    )
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()
