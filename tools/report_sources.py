"""Collect per-item source notes and render them once at the end of a report.

Body sections keep interpretation caveats; URLs, collection times and library
versions are gathered here, only for items that were actually rendered.
"""
from datetime import datetime, timezone
from html import escape

ANCHOR = "report-sources"


def when(value):
    """Format an ISO timestamp as 'YYYY-MM-DD HH:MM UTC' (escaped)."""
    if not value:
        return "미제공"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return escape(str(value))
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def link(url, text):
    return f'<a href="{escape(str(url), quote=True)}">{escape(str(text))}</a>'


def openf1(endpoint, key):
    return link(f"https://api.openf1.org/v1/{endpoint}?session_key={key}", endpoint)


def map_credit(reference):
    """OpenStreetMap/ODbL and outline credit for a displayed pit-lane reference line."""
    if not reference or not reference.get("segments"):
        return []
    parts = [
        link(
            reference.get("license") or "https://www.openstreetmap.org/copyright",
            reference.get("attribution") or "© OpenStreetMap contributors · ODbL 1.0",
        )
    ]
    ways = reference.get("source") or []
    if ways:
        parts.append(
            "피트 경로 "
            + " · ".join(link(url, "OSM way " + str(url).rsplit("/", 1)[-1]) for url in ways)
        )
    if reference.get("outline_source"):
        parts.append(
            "정합 기준 " + link(reference["outline_source"], "bacinger/f1-circuits") + " · MIT"
        )
    return ["피트레인 지도 참고선: " + " · ".join(parts)]


def render_sources(groups):
    """groups: [(session label, [(item name, [entry html, ...]), ...]), ...]"""
    blocks = []
    for label, items in groups:
        items = [(name, entries) for name, entries in items if entries]
        if not items:
            continue
        rows = "".join(
            f"<li><b>{escape(name)}</b><ul>"
            + "".join(f"<li>{entry}</li>" for entry in entries)
            + "</ul></li>"
            for name, entries in items
        )
        blocks.append(f'<h3 data-source-session="{escape(label, quote=True)}">{escape(label)}</h3><ul>{rows}</ul>')
    return (
        f'<section id="{ANCHOR}" style="scroll-margin-top:24px"><h2>항목별 출처</h2>'
        '<p class="meta">본문에 표시된 항목의 자료만 세션·항목별로 모았습니다. 해석에 필요한 주의사항은 각 항목 본문에 있습니다. 시각은 UTC입니다.</p>'
        + ("".join(blocks) or "<p>표시된 데이터 항목이 없어 출처가 없습니다.</p>")
        + "<p>이 HTML 파일 하나로 인터넷 연결 없이 표·검색·차트를 사용할 수 있습니다. 위 링크는 원본 확인용입니다.</p></section>"
    )
