"""Year-scoped race reference attachments, embedded for offline use."""
import base64
import json
from html import escape
from pathlib import Path

from race_starting_tyres import load_summaries, render_starting_tyres

ATTACHMENTS = Path(__file__).resolve().parents[1] / "reports" / "attachments"
ALLOWED = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def compound_card(session, item, heading):
    selected = next(
        (
            record
            for record in item.get("circuits", [])
            if record["circuit_key"] == session.get("circuit_key")
        ),
        None,
    )
    place = escape(
        session.get("location") or session.get("circuit_short_name") or "선택한 그랑프리"
    )
    card = (
        f'<article data-compound-selection="{session.get("circuit_key", "unknown")}">'
        + heading
        + f"<p>{place} · 선택한 대회 컴파운드</p>"
    )
    if selected is None:
        return card + "<p>제공된 참고자료에 이 대회의 컴파운드 조합이 없어 표시하지 않습니다.</p></article>"
    tiles = []
    for key, code, label, color in [
        ("hard", "H", "하드", "#f4f4f4"),
        ("medium", "M", "미디엄", "#ffdb34"),
        ("soft", "S", "소프트", "#ff4343"),
    ]:
        compound = escape(selected[key])
        tiles.append(
            f'<div style="background:{color};color:#0b1321;padding:16px 8px;border-radius:12px;text-align:center"><b>{label} · {code}</b><div style="font-size:28px;font-weight:800">{compound}</div></div>'
        )
    return (
        card
        + '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px">'
        + "".join(tiles)
        + "</div></article>"
    )


def render_race_attachments(snapshot, directory=None, starting_tyre_summaries=None):
    if snapshot["session"]["session_name"] != "Race":
        return ""
    directory = directory or ATTACHMENTS
    manifest = directory / "manifest.json"
    session = snapshot["session"]
    year = session.get("year") or int(session["date_start"][:4])
    items = [
        item
        for item in (
            json.loads(manifest.read_text(encoding="utf-8"))
            if manifest.exists()
            else []
        )
        if item["year"] == year
    ]
    cards = []
    summaries = (
        starting_tyre_summaries
        if starting_tyre_summaries is not None
        else load_summaries(directory.parent)
    )
    starting_card = render_starting_tyres(snapshot, summaries)
    has_starting_card = False
    for item in items:
        name = item["filename"]
        if Path(name).name != name:
            raise ValueError("Attachment filename must not contain a directory")
        path = directory / name
        heading = f'<h4>{escape(item["title"])}</h4><p class="meta">{year}년 · {escape(item.get("source", "참고자료"))}</p>'
        if item.get("kind") == "starting-tyres":
            cards.append(starting_card)
            has_starting_card = True
            continue
        if item.get("kind") == "compound-selection":
            cards.append(compound_card(session, item, heading))
            continue
        if not path.exists():
            cards.append("<article>" + heading + "<p>원본 파일 연결 대기</p></article>")
            continue
        if path.is_symlink() or path.suffix.lower() not in ALLOWED:
            raise ValueError("Unsupported attachment file")
        uri = (
            "data:"
            + ALLOWED[path.suffix.lower()]
            + ";base64,"
            + base64.b64encode(path.read_bytes()).decode()
        )
        cards.append(
            "<article>"
            + heading
            + f'<img src="{uri}" alt="{escape(item["title"])}" style="display:block;width:100%;height:auto;margin-top:16px"></article>'
        )
    if not has_starting_card:
        cards.append(starting_card)
    return (
        '<section id="race-tyre-attachments"><h3>그랑프리별 타이어 컴파운드와 스타트 타이어</h3><p class="meta">대회 컴파운드 조합은 사용자 제공 참고자료이며, 스타트 타이어는 저장된 OpenF1 레이스 기록에서 자동 집계합니다.</p><div class="race-reference-images">'
        + "".join(cards)
        + "</div></section>"
    )
