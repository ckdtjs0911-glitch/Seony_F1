"""Year-scoped race reference attachments, embedded for offline use."""
import base64
import json
from html import escape
from pathlib import Path

ATTACHMENTS = Path(__file__).resolve().parents[1] / "reports" / "attachments"
ALLOWED = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def render_race_attachments(snapshot, directory=None):
    if snapshot["session"]["session_name"] != "Race":
        return ""
    directory = directory or ATTACHMENTS
    manifest = directory / "manifest.json"
    if not manifest.exists():
        return ""
    session = snapshot["session"]
    year = session.get("year") or int(session["date_start"][:4])
    items = [
        item
        for item in json.loads(manifest.read_text(encoding="utf-8"))
        if item["year"] == year
    ]
    if not items:
        return ""
    cards = []
    for item in items:
        name = item["filename"]
        if Path(name).name != name:
            raise ValueError("Attachment filename must not contain a directory")
        path = directory / name
        heading = f'<h4>{escape(item["title"])}</h4><p class="meta">{year}년 · {escape(item.get("source", "참고자료"))}</p>'
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
    return (
        '<section id="race-tyre-attachments"><h3>그랑프리별 타이어 컴파운드와 스타트 타이어</h3><p class="meta">해당 연도의 사용자 제공 참고자료입니다. 이미지의 수치와 설명은 OpenF1 계산값과 구분합니다.</p><div class="race-reference-images">'
        + "".join(cards)
        + "</div></section>"
    )
