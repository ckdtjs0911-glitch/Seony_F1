"""Per-session record of automatic report attempts (one automatic attempt per session).

Only ``collected`` (and committed) and ``unchanged`` are successful outcomes. Every other status
still blocks automatic retries; further attempts need an explicit manual request.
``deferred_end_later`` keeps the later actual end so the gate waits for it.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

SUCCESS = ("collected", "unchanged")
AUTH_PENDING = ("auth_restricted", "fastf1_provisional")
NAME = Path("catalog") / "report-attempts.json"


def path_for(reports):
    return Path(reports) / NAME


def load(reports):
    try:
        value = json.loads(path_for(reports).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def record(reports, session, status, now=None, actual_end=None, auth_retry=False):
    """Write the attempt immediately so a later crash still keeps it."""
    now = now or datetime.now(timezone.utc)
    attempts = load(reports)
    key = str(session["session_key"])
    entry = attempts.get(key, {})
    entry.setdefault("first_attempt_at", now.isoformat())
    entry.update(
        meeting_key=session.get("meeting_key"),
        session_name=session.get("session_name"),
        status=status,
        completed=status in SUCCESS,
        updated_at=now.isoformat(),
    )
    if auth_retry:
        entry.setdefault("auth_retry_at", now.isoformat())
    if actual_end is not None:
        entry["actual_end"] = actual_end.isoformat()
    attempts[key] = entry
    target = path_for(reports)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(attempts, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return entry


def merge(base, ours, unpublished=()):
    """Combine two attempt files, keeping the most recently updated entry per session.

    ``unpublished`` session keys had their data discarded (state-only save), so a
    ``collected`` outcome is downgraded: it must not count as completed.
    """
    merged = dict(base)
    for key, entry in ours.items():
        current = merged.get(key)
        if current is None or str(entry.get("updated_at", "")) >= str(current.get("updated_at", "")):
            merged[key] = entry
    for key in {str(k) for k in unpublished}:
        entry = merged.get(key)
        if entry and entry.get("status") == "collected":
            merged[key] = dict(entry, status="not_published", completed=False)
    return merged


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Merge attempt records before a state-only commit.")
    parser.add_argument("--merge", nargs=2, type=Path, metavar=("BASE", "OURS"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unpublished", default="", help="Comma-separated session keys whose collected data was not committed")
    args = parser.parse_args()
    values = []
    for path in args.merge:
        try:
            values.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            values.append({})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    unpublished = [x.strip() for x in args.unpublished.split(",") if x.strip()]
    args.output.write_text(json.dumps(merge(*values, unpublished=unpublished), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
