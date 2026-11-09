"""Starting compounds from lap-one stints, with DNS and uncertainty kept separate."""

import json
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from html import escape
from pathlib import Path

from race_pitstops import compound_badge

TYRES = {
    "SOFT": ("S", "소프트", "#ff4343"),
    "MEDIUM": ("M", "미디엄", "#ffdb34"),
    "HARD": ("H", "하드", "#f4f4f4"),
    "INTERMEDIATE": ("I", "인터미디어트", "#52d983"),
    "WET": ("W", "웨트", "#58a6ff"),
    "UNKNOWN": ("?", "타이어 미확인", "#9aacc1"),
}


def year_of(session):
    return int(session.get("year") or session["date_start"][:4])


def summarize_start(snapshot):
    session = snapshot["session"]
    data = snapshot.get("data", {})
    drivers = {x["driver_number"]: x for x in data.get("drivers", [])}
    results = {x["driver_number"]: x for x in data.get("session_result", [])}
    evidence = set()
    for lap in data.get("laps", []):
        number = lap.get("lap_number")
        if isinstance(number, int) and (
            number > 1
            or number == 1
            and any(
                isinstance(lap.get(key), (int, float)) and lap[key] > 0
                for key in (
                    "lap_duration",
                    "duration_sector_1",
                    "duration_sector_2",
                    "duration_sector_3",
                )
            )
        ):
            evidence.add(lap["driver_number"])
    for number, result in results.items():
        laps = result.get("number_of_laps")
        if (isinstance(laps, (int, float)) and laps > 0) or result.get("dnf"):
            evidence.add(number)
    stints = data.get("stints", [])
    numbers = (
        set(drivers) | set(results) | evidence | {x["driver_number"] for x in stints}
    )
    rows, counts = [], Counter()
    dns = unconfirmed = 0
    for number in sorted(numbers):
        result = results.get(number, {})
        driver = drivers.get(number, {})
        compound = "UNKNOWN"
        if result.get("dns"):
            status = "DNS · 미출발"
            dns += 1
        elif number not in evidence:
            status = "출발 여부 미확인"
            unconfirmed += 1
        else:
            candidates = {
                str(s.get("compound") or "UNKNOWN").upper()
                for s in stints
                if s.get("driver_number") == number
                and s.get("lap_start") == 1
                and isinstance(s.get("lap_end"), int)
                and s["lap_end"] >= 1
            }
            if len(candidates) == 1:
                value = candidates.pop()
                compound = value if value in TYRES else "UNKNOWN"
            counts[compound] += 1
            status = "출발 확인"
        rows.append(
            {
                "number": number,
                "name": driver.get("full_name", f"Driver {number}"),
                "team": driver.get("team_name", "팀 미제공"),
                "compound": compound,
                "status": status,
            }
        )
    return {
        "session": session,
        "counts": dict(counts),
        "starters": sum(counts.values()),
        "dns": dns,
        "unconfirmed": unconfirmed,
        "rows": rows,
        "fetched_at": snapshot.get("fetched_at"),
        "has_data": bool(data.get("session_result") or data.get("laps")),
    }


def summaries_for(snapshots, sessions=()):
    items = {
        s["session_key"]: summarize_start({"session": s})
        for s in sessions
        if s.get("session_name") == "Race"
    }
    for snapshot in snapshots:
        if snapshot["session"].get("session_name") == "Race":
            items[snapshot["session"]["session_key"]] = summarize_start(snapshot)
    return items


@lru_cache(maxsize=4)
def cached_summaries(signature, catalog_signature):
    snapshots = [
        json.loads(Path(name).read_text(encoding="utf-8")) for name, _, _ in signature
    ]
    snapshots = [
        s
        for s in snapshots
        if isinstance(s, dict) and isinstance(s.get("session"), dict)
    ]
    catalog = (
        json.loads(Path(catalog_signature[0]).read_text(encoding="utf-8"))
        if catalog_signature
        else []
    )
    return summaries_for(snapshots, catalog)


def load_summaries(root):
    paths = sorted(root.glob("weekend-*/data/*.json"))
    signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    path = root / "catalog" / "sessions.json"
    catalog = (
        (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        if path.exists()
        else ()
    )
    return cached_summaries(signature, catalog)


def render_starting_tyres(snapshot, summaries):
    current = summarize_start(snapshot)
    records = dict(summaries)
    records[snapshot["session"]["session_key"]] = current
    year = year_of(snapshot["session"])
    selected = sorted(
        [s for s in records.values() if year_of(s["session"]) == year],
        key=lambda s: (s["session"].get("date_start", ""), s["session"]["session_key"]),
    )
    lines = []
    for record in selected:
        session = record["session"]
        name = (
            escape(
                " · ".join(
                    dict.fromkeys(
                        filter(
                            None,
                            [
                                session.get("country_name"),
                                session.get("location")
                                or session.get("circuit_short_name"),
                            ],
                        )
                    )
                )
            )
            or "대회"
        )
        key = session["session_key"]
        selected_label = (
            " · 선택한 대회" if key == snapshot["session"]["session_key"] else ""
        )
        if record["has_data"]:
            pieces = []
            for compound, (code, label, color) in TYRES.items():
                count = record["counts"].get(compound, 0)
                if count:
                    pieces.append(
                        f'<span style="flex:{count};min-width:36px;background:{color};color:#0b1321;'
                        f'text-align:center;padding:6px 3px;font-weight:800" title="{label} {count}명">{code} {count}</span>'
                    )
            bars = (
                '<div style="display:flex;gap:2px;border-radius:6px;overflow:hidden">'
                + "".join(pieces)
                + "</div>"
                if pieces
                else "출발 자료 미확인"
            )
            state = f'DNS {record["dns"]}명'
            if record["unconfirmed"]:
                state += f' · 출발 여부 미확인 {record["unconfirmed"]}명'
            total = str(record["starters"])
        else:
            bars, total = "—", "—"
            if session.get("is_cancelled"):
                state = "취소"
            else:
                start = datetime.fromisoformat(
                    session["date_start"].replace("Z", "+00:00")
                )
                state = "레이스 전" if start > datetime.now(timezone.utc) else "원본 수집 대기"
        lines.append(
            f'<tr data-start-session="{escape(str(key), quote=True)}"><td><b>{name}{selected_label}</b><small>{escape(session.get("date_start", "")[:10])}</small></td>'
            f'<td>{total}</td><td style="min-width:260px">{bars}</td><td>{state}</td></tr>'
        )
    legend = " · ".join(compound_badge(c) for c in TYRES if c != "UNKNOWN")
    details = []
    for row in current["rows"]:
        tyre = compound_badge(row["compound"]) if row["status"] == "출발 확인" else "—"
        details.append(
            f'<tr><td>#{escape(str(row["number"]))} {escape(row["name"])}</td><td>{escape(row["team"])}</td><td>{tyre}</td><td>{row["status"]}</td></tr>'
        )
    return (
        '<article data-starting-tyres="openf1"><h4>그랑프리별 스타트 타이어</h4>'
        f'<p class="meta">{year}년 · 저장된 OpenF1 레이스 원본에서 자동 집계 · 최초 L1을 포함하는 스틴트 기준입니다. '
        "DNS는 출발 인원에서 제외합니다. 타이어 정보가 없거나 충돌하면 미확인으로 표시하며, 재출발·후속 교체는 합산하지 않습니다.</p>"
        f'<p>{legend} · ? 미확인</p><div class="scroll"><table><thead><tr><th>그랑프리</th><th>출발 인원</th><th>스타트 타이어 · 명</th><th>출발 상태</th></tr></thead><tbody>'
        + "".join(lines)
        + '</tbody></table></div><div class="starting-tyre-drivers"><h5>선택한 대회 · 선수별 스타트 타이어</h5>'
        '<div class="scroll"><table><thead><tr><th>드라이버</th><th>팀</th><th>스타트 타이어</th><th>상태</th></tr></thead><tbody>'
        + "".join(details)
        + '</tbody></table></div></div><p class="meta">선택한 레이스 수집 시각: '
        + escape(snapshot.get("fetched_at") or "미제공")
        + "</p></article>"
    )
