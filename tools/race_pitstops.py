"""Race pit entries grouped by team and driver; stationary and lane times stay distinct."""
from collections import defaultdict
from datetime import timedelta
from html import escape
from zoneinfo import ZoneInfo

from race_events import parse_time


def duration(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return f"{value:.3f}초"
    return "미제공"


def render_pitstops(snapshot, rows):
    if snapshot["session"]["session_name"] != "Race":
        return ""
    data = snapshot.get("data", {})
    timed = [lap for lap in data.get("laps", []) if parse_time(lap.get("date_start"))]
    start = min((parse_time(lap["date_start"]) for lap in timed), default=None)
    end = max(
        (
            parse_time(lap["date_start"])
            + timedelta(seconds=lap.get("lap_duration") or 0)
            for lap in timed
        ),
        default=None,
    )
    grouped = defaultdict(list)
    excluded = 0
    for event in data.get("pit", []):
        when = parse_time(event.get("date"))
        if when and start and end and not start <= when <= end:
            excluded += 1
            continue
        grouped[event["driver_number"]].append(event)
    drivers = {row["number"]: row for row in rows}
    for number in grouped:
        drivers.setdefault(
            number,
            {
                "number": number,
                "name": f"Driver {number}",
                "team": "팀 미제공",
                "position": None,
            },
        )
    teams = defaultdict(list)
    for driver in drivers.values():
        teams[driver["team"]].append(driver)
    parts = []
    for team, members in sorted(teams.items()):
        panels = []
        for driver in sorted(
            members, key=lambda row: (row.get("position") or 999, row["number"])
        ):
            number = driver["number"]
            events = sorted(
                grouped[number],
                key=lambda event: (
                    event.get("date") or "9999",
                    event.get("lap_number") or 0,
                ),
            )
            heading = f'<h4>#{number} {escape(driver["name"])}</h4>'
            search = escape((driver["name"] + " " + team).lower())
            panel = (
                f'<article data-pit-driver="{number}" data-search="{search}">' + heading
            )
            if not events:
                panel += '<p class="meta">수집된 레이스 시간 범위에서 확인된 피트 기록 없음</p>'
            else:
                panel += '<div class="scroll"><table><thead><tr><th>기록 번호</th><th>랩</th><th>기록 시각 (한국 시간)</th><th>정차 시간</th><th>피트 레인 통과 시간</th></tr></thead><tbody>'
                for index, event in enumerate(events, 1):
                    when = parse_time(event.get("date"))
                    clock = (
                        when.astimezone(ZoneInfo("Asia/Seoul")).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if when
                        else "시각 미제공 · 레이스 범위 미확인"
                    )
                    lane = event.get("lane_duration")
                    lane_text = duration(lane)
                    if lane is None and event.get("pit_duration") is not None:
                        lane_text = (
                            duration(event["pit_duration"]) + " (기존 pit_duration)"
                        )
                    panel += f'<tr><td>{index}</td><td>{event.get("lap_number") if event.get("lap_number") is not None else "미제공"}</td><td>{clock}</td><td>{duration(event.get("stop_duration"))}</td><td>{lane_text}</td></tr>'
                panel += "</tbody></table></div>"
            panels.append(panel + "</article>")
        parts.append(
            f'<details open data-pit-team="{escape(team)}"><summary>{escape(team)} · {len(members)}명</summary>'
            + "".join(panels)
            + "</details>"
        )
    note = f" 관측 레이스 시간 범위 밖의 이벤트 {excluded}건은 제외했습니다." if excluded else ""
    if not start or not end:
        note += " 레이스 랩 시각이 없어 이벤트 시간 범위를 검증할 수 없습니다."
    return (
        '<section id="race-pit-stops" style="scroll-margin-top:24px"><h2>팀·선수별 피트스탑 기록</h2>'
        '<p class="meta">피트 기록의 랩과 한국 시간을 표시합니다. 시각은 API 이벤트 기록 시각이며 정확한 진입·출구 시각은 추정하지 않습니다. 정차 시간은 stop_duration, 레인 통과 시간은 lane_duration 기준입니다. '
        "기존 pit_duration만 있는 경우 출처 필드명을 붙입니다. 서로 대체하거나 정차 시간을 추정하지 않습니다. 레인 시간에는 대기·경기 중단 등의 영향이 포함될 수 있어 타이어 교체 작업 시간과 같지 않습니다. "
        "피트 진입 기록은 타이어 교체 횟수와 다를 수 있고, 기록 없음은 실제 무정차를 단정하지 않습니다."
        + note
        + "</p>"
        + "".join(parts)
        + "</section>"
    )
