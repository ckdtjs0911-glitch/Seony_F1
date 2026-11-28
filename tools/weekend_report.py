"""Collect and render a complete OpenF1 weekend. Run with --help for options."""

import argparse
import html
import json
import re
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from race_events import render_race_events
from race_attachments import render_race_attachments
from race_pitstops import render_pitstops
from race_overtakes import render_overtakes
from report_video import render_section as render_video_section
from qualifying_replay import render_qualifying
from fastf1_source import render_source as render_fastf1_source
import report_attempts
import report_sources

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openf1.util import openf1_client  # noqa: E402

SESSION_NAMES = ("Practice 1", "Practice 2", "Practice 3", "Sprint Qualifying", "Sprint", "Qualifying", "Race")
LABELS = dict(zip(SESSION_NAMES, ("프랙티스 1", "프랙티스 2", "프랙티스 3", "스프린트 퀄리파잉", "스프린트 레이스", "퀄리파잉", "레이스")))
ENDPOINTS = ("drivers", "session_result", "laps", "stints", "pit", "race_control")
RETRY_STATUS = (429, 500, 502, 503, 504)
ROOT = Path(__file__).resolve().parents[1]
ENCODING = "utf-8"
REPORT_DELAY = timedelta(hours=3)


SPRINT_SESSIONS = {"Sprint", "Sprint Qualifying"}


def weekend_session_names(sessions):
    sprint_weekend = any(session.get("session_name") in SPRINT_SESSIONS for session in sessions)
    excluded = {"Practice 2", "Practice 3"} if sprint_weekend else SPRINT_SESSIONS
    return tuple(name for name in SESSION_NAMES if name not in excluded)


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch(endpoint, params):
    for attempt in range(4):
        try:
            value = openf1_client.get("v1/" + endpoint, params=params)
            if not isinstance(value, list):
                raise ValueError(f"{endpoint}: expected an array")
            time.sleep(0.4)
            return value
        except requests.HTTPError as exc:
            response = exc.response
            if response is None or response.status_code not in RETRY_STATUS:
                raise
            if attempt == 3:
                raise
            delay = response.headers.get("Retry-After", "")
            time.sleep(min(60, int(delay)) if delay.isdigit() else 2 ** (attempt + 1))
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def load_json(path):
    return json.loads(path.read_text(encoding=ENCODING))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding=ENCODING
    )
    temporary.replace(path)


def seconds(value):
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        return "—"
    minutes, millis = divmod(round(value * 1000), 60000)
    return f"{minutes}:{millis / 1000:06.3f}"


def esc(value):
    return html.escape(str(value))


def display_time(value):
    """Format an ISO timestamp as 'YYYY-MM-DD HH:MM UTC'; keep other text as is."""
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = stamp(str(value))
        except ValueError:
            return str(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def anchor(name):
    return name.replace(" ", "-")


def deleted_laps(messages, laps):
    deleted = set()
    for message in messages:
        match = re.search(
            r"CAR (\d+).*TIME (\d+):(\d+\.\d+).*DELETED.*LAP (\d+)", message.get("message") or ""
        )
        if match:
            driver, minutes, seconds, lap_number = match.groups()
            driver, lap_number = int(driver), int(lap_number)
            duration = int(minutes) * 60 + float(seconds)
            candidates = {
                lap["lap_number"]
                for lap in laps
                if lap.get("driver_number") == driver
                and lap.get("lap_number") in (lap_number, lap_number - 1)
                and isinstance(lap.get("lap_duration"), (int, float))
                and abs(lap["lap_duration"] - duration) < 0.0011
            }
            if len(candidates) == 1:
                deleted.add((driver, candidates.pop()))
    return deleted


def numeric_position(value):
    if isinstance(value, bool):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return (
        numeric
        if str(value) in (str(numeric), f"{numeric}.0") and numeric > 0
        else None
    )


def result_status(result):
    if result.get("dsq"):
        return "DSQ"
    if result.get("dns"):
        return "DNS"
    if result.get("dnf"):
        return "DNF"
    if (
        result
        and result.get("position") is not None
        and numeric_position(result["position"]) is None
    ):
        return f"API 분류 {result['position']}"
    return "기록 있음" if result else "결과 대기"


def qualifying_phase(q):
    if q[2] is not None:
        return "Q3 기록"
    if q[1] is not None:
        return "Q2 기록 / Q3 없음"
    if q[0] is not None:
        return "Q1 기록 / Q2 없음"
    return "단계 자료 없음"


def format_gap(gap):
    if isinstance(gap, list):
        return " / ".join(str(x) if x is not None else "—" for x in gap)
    if isinstance(gap, (float, int)) and not isinstance(gap, bool):
        return f"+{gap:.3f}s"
    return "—" if gap is None else gap


def tyre_for_lap(stints, lap_number):
    """Only explicit, unambiguous stint ranges establish a lap's tyre."""
    compounds = {
        str(stint.get("compound") or "UNKNOWN").upper()
        for stint in stints
        if isinstance(stint.get("lap_start"), int)
        and isinstance(stint.get("lap_end"), int)
        and stint["lap_start"] <= lap_number <= stint["lap_end"]
    }
    return compounds.pop() if len(compounds) == 1 else "UNKNOWN"


def render_verdicts(name, rows):
    available = [row["fastest"] for row in rows if row["fastest"] is not None]
    best = min(available) if available else None
    lines = []
    for row in rows:
        if row["status"] in ("DNF", "DNS", "DSQ"):
            text = f"{row['status']}로 기록됐으며, 완료 랩은 {row['completed'] if row['completed'] is not None else '미확인'}랩입니다."
        elif row["fastest"] is None:
            text = "유효한 관측 랩타임이 없어 페이스 평가는 보류합니다."
        elif name == "Race":
            rank = (
                f"API 결과 P{row['position']}"
                if row["position"] is not None
                else "API 순위 미제공"
            )
            text = f"{rank} · 관측 최속 {seconds(row['fastest'])}"
            if row["pits"] is not None:
                text += f", 피트 레인 진입 {row['pits']}회가 기록됐습니다."
        else:
            delta = row["fastest"] - best
            assessment = "관측 최속 기준 선두" if delta == 0 else f"세션 관측 최속보다 {delta:.3f}초 느림"
            caveat = (
                " 단계(Q1~Q3)·타이어·주행 조건이 다른 기록을 함께 비교한 값이라 공식 순위와 다를 수 있습니다."
                if name in ("Qualifying", "Sprint Qualifying")
                else ""
            )
            text = f"{assessment} · 최속 {seconds(row['fastest'])}, {row['records']}개 랩 기록으로 비교한 결과입니다.{caveat}"
        rank = row["position"] if row["position"] is not None else "—"
        search = esc((row["name"] + " " + row["team"]).lower())
        lines.append(
            f'<tr data-search="{search}"><td>{rank}</td><td><b>#{row["number"]} {esc(row["name"])}</b><small>{esc(row["team"])}</small></td><td class="verdict-text">{esc(text)}</td></tr>'
        )
    return (
        '<h3>선수별 한 줄 평</h3><p class="meta">관측 기록에 근거한 자동 요약입니다. 연료량·타이어·트래픽을 보정한 실력 평가는 아닙니다. 10명씩 넘겨 볼 수 있습니다.</p>'
        '<div class="scroll result-table driver-verdict-table"><table><thead><tr><th>API 순위</th><th>드라이버 / 팀</th><th>기록 기반 한 줄 평</th></tr></thead><tbody>'
        + "".join(lines)
        + "</tbody></table></div>"
    )


def qualifying_windows(snapshot):
    if (
        snapshot["session"].get("session_type") != "Qualifying"
        and snapshot["session"]["session_name"] not in ("Qualifying", "Sprint Qualifying")
    ):
        return []
    controls = snapshot.get("data", {}).get("race_control", [])
    windows = []
    for phase in (1, 2, 3):
        starts = [
            stamp(r["date"])
            for r in controls
            if r.get("qualifying_phase") == phase
            and r.get("message") == "SESSION STARTED"
            and r.get("date")
        ]
        if not starts:
            continue
        start = min(starts)
        next_starts = [
            stamp(r["date"])
            for r in controls
            if r.get("qualifying_phase") in range(phase + 1, 4)
            and r.get("message") == "SESSION STARTED"
            and r.get("date")
        ]
        finishes = [
            stamp(r["date"])
            for r in controls
            if r.get("qualifying_phase") == phase
            and r.get("message") == "SESSION FINISHED"
            and r.get("date")
        ]
        end = min(next_starts) if next_starts else max(finishes) if finishes else None
        if end and end > start:
            windows.append((phase, start, end))
    return windows


def lap_qualifying_phase(lap, windows):
    if lap.get("qualifying_phase") in (1, 2, 3):
        return lap["qualifying_phase"]
    if not lap.get("date_start"):
        return None
    moment = stamp(lap["date_start"])
    return next((phase for phase, start, end in windows if start <= moment < end), None)


def summarize(snapshot):
    data = snapshot["data"]
    phase_windows = qualifying_windows(snapshot)
    drivers = {x["driver_number"]: x for x in data.get("drivers", [])}
    results = {x["driver_number"]: x for x in data.get("session_result", [])}
    all_laps = data.get("laps", [])
    numbers = set(drivers) | set(results) | {x["driver_number"] for x in all_laps}
    deleted = deleted_laps(data.get("race_control", []), data.get("laps", []))
    starts = [stamp(x["date_start"]) for x in all_laps if x.get("date_start")]
    start = min(starts) if starts else None
    ends = [
        stamp(x["date_start"]) + timedelta(seconds=x.get("lap_duration") or 0)
        for x in all_laps
        if x.get("date_start")
    ]
    end = max(ends) if ends else None
    rows = []
    for number in numbers:
        driver = drivers.get(number, {})
        result = results.get(number, {})
        laps = sorted(
            [x for x in all_laps if x["driver_number"] == number],
            key=lambda x: x["lap_number"],
        )
        pits = [
            x
            for x in data.get("pit", [])
            if x["driver_number"] == number
            and start
            and end
            and x.get("date")
            and start <= stamp(x["date"]) <= end
        ]
        pit_laps = {x["lap_number"] for x in pits}
        valid = [
            x
            for x in laps
            if isinstance(x.get("lap_duration"), (float, int))
            and x["lap_duration"] > 0
            and (number, x["lap_number"]) not in deleted
        ]
        clean = [
            x
            for x in valid
            if x["lap_number"] > 1
            and not x.get("is_pit_out_lap")
            and x["lap_number"] not in pit_laps
        ]
        by_compound = []
        stints = sorted(
            [x for x in data.get("stints", []) if x["driver_number"] == number],
            key=lambda x: x["stint_number"],
        )
        for stint in stints:
            first = stint.get("lap_start")
            last = stint.get("lap_end") or -1
            samples = [
                x["lap_duration"]
                for x in clean
                if first is not None and first <= x["lap_number"] <= last
            ]
            by_compound.append(
                dict(
                    stint,
                    sample_count=len(samples),
                    median=statistics.median(samples) if samples else None,
                )
            )
        fastest = min(valid, key=lambda x: x["lap_duration"]) if valid else None
        durations = result.get("duration")
        rows.append(
            {
                "number": number,
                "name": driver.get("full_name", f"Driver {number}"),
                "team": driver.get("team_name", "팀 정보 없음"),
                "position": numeric_position(result.get("position")),
                "classification": result.get("position"),
                "status": result_status(result),
                "completed": result.get("number_of_laps"),
                "points": result.get("points"),
                "gap": result.get("gap_to_leader"),
                "duration": durations,
                "q": (durations + [None] * 3)[:3]
                if isinstance(durations, list)
                else [None] * 3,
                "fastest": fastest["lap_duration"] if fastest else None,
                "median": statistics.median(x["lap_duration"] for x in clean)
                if clean
                else None,
                "samples": len(clean),
                "pits": None if snapshot.get("data_source") == "fastf1" else len(pits),
                "records": len(laps),
                "stints": by_compound,
                "laps": [
                    {
                        "lap": x["lap_number"],
                        "time": x.get("lap_duration"),
                        "s1": x.get("duration_sector_1"),
                        "s2": x.get("duration_sector_2"),
                        "s3": x.get("duration_sector_3"),
                        "tyre": tyre_for_lap(stints, x["lap_number"]),
                        "phase": lap_qualifying_phase(x, phase_windows),
                        "deleted": (number, x["lap_number"]) in deleted,
                    }
                    for x in laps
                ],
            }
        )
    rows.sort(
        key=lambda x: (
            x["position"] is None,
            x["position"] or 999,
            x["fastest"] or float("inf"),
            x["number"],
        )
    )
    return rows


def or_dash(value):
    return "—" if value is None else value


def render_table(name, rows):
    bests = [r["fastest"] for r in rows if r["fastest"] is not None]
    best = min(bests) if bests else None
    head = (
        "<th>Q1</th><th>Q2</th><th>Q3</th><th>기록 단계</th>"
        if name in ("Qualifying", "Sprint Qualifying")
        else "<th>관측 최속</th><th>최속 대비</th>"
    )
    records = []
    for row in rows:
        if name in ("Qualifying", "Sprint Qualifying"):
            q = row["q"]
            extra = "".join(f"<td>{seconds(v)}</td>" for v in q)
            extra += f"<td>{qualifying_phase(q)}</td>"
        else:
            delta = (
                f'+{row["fastest"] - best:.3f}s'
                if row["fastest"] is not None and best is not None
                else "—"
            )
            extra = f'<td>{seconds(row["fastest"])}</td><td>{delta}</td>'
        search = esc((row["name"] + " " + row["team"]).lower())
        records.append(
            f'<tr data-search="{search}">'
            f'<td>{or_dash(row["position"])}</td>'
            f'<td><b>#{row["number"]} {esc(row["name"])}</b>'
            f'<small>{esc(row["team"])}</small></td>'
            f'<td>{esc(row["status"])}</td>{extra}'
            f'<td>{seconds(row["median"])}<small>표본 {row["samples"]}랩</small></td>'
            f'<td>{or_dash(row["completed"])} / {row["records"]}</td>'
            f'<td>{esc(format_gap(row["gap"]))}</td>'
            f'<td>{or_dash(row["points"])}</td>'
            f'<td>{or_dash(row["pits"])}</td></tr>'
        )
    return (
        '<div class="scroll result-table"><table><thead><tr><th>API 순위</th><th>드라이버 / 팀</th>'
        f"<th>상태</th>{head}<th>랩 중앙값</th><th>완료 / 기록 랩</th>"
        "<th>API 선두 격차</th><th>점수</th><th>피트 진입</th></tr></thead>"
        f'<tbody>{"".join(records)}</tbody></table></div>'
    )


def render_beginner_notes(name, rows):
    """Explain this session's observed records without inventing causes."""
    facts = []
    if name.startswith("Practice"):
        meaning = "프랙티스는 차량과 타이어를 시험하고 주행을 준비하는 연습 세션입니다. 한 바퀴를 도는 시간인 랩타임은 짧을수록 빠릅니다. 연습 순위가 결승 출발 순서나 우승을 뜻하지는 않습니다."
        timed = [r for r in rows if isinstance(r.get("fastest"), (int, float)) and r["fastest"] > 0]
        if timed:
            leader = min(timed, key=lambda r: r["fastest"])
            facts.append(f'이번 세션의 관측 최속은 {leader["name"]}의 {seconds(leader["fastest"])}입니다. 삭제가 확인된 랩을 제외한 관측 기록 기준이며 API 순위와 다를 수 있습니다.')
        limit = "선수마다 연료량, 타이어, 주행 시점과 연습 목적이 다릅니다. 최속 한 바퀴만으로 결승에서 누가 더 빠를지 단정할 수 없습니다."
    elif name in ("Qualifying", "Sprint Qualifying"):
        meaning = "퀄리파잉은 결승 출발 순서를 정하기 위한 예선입니다. Q1·Q2·Q3는 예선의 단계이며, 각 칸은 API가 제공한 해당 단계의 기록입니다. 단계가 다르면 노면과 날씨도 달라질 수 있습니다."
        leader = next((r for r in rows if r.get("position") == 1), None)
        if leader:
            facts.append(f'API 예선 결과 1위는 {leader["name"]}입니다. 그리드 페널티 등이 적용된 실제 결승 출발 위치는 별도로 확인해야 합니다.')
        for index in range(3):
            timed = [r for r in rows if isinstance(r["q"][index], (int, float)) and r["q"][index] > 0]
            if timed:
                best = min(timed, key=lambda r: r["q"][index])
                facts.append(f'Q{index + 1} 제공 기록 중 최속: {best["name"]} · {seconds(best["q"][index])}.')
        limit = "Q1~Q3 전체에서 가장 짧은 시간과 최종 예선 1위는 다를 수 있습니다. 같은 단계끼리 비교하고, 빈 칸만으로 탈락·미출전·기록 삭제를 단정하지 마세요."
    else:
        meaning = "레이스는 실제 결승입니다. 최종 순위와 한 바퀴 최속 기록은 다른 지표입니다. 한 바퀴가 빨라도 전체 주행 결과에서 앞선다는 뜻은 아닙니다."
        leader = next((r for r in rows if r.get("position") == 1), None)
        if leader:
            facts.append(f'API 결승 결과 1위는 {leader["name"]}입니다.')
            if leader.get("completed") is not None:
                facts.append(f'이 선수의 결과상 완료 랩 수는 {leader["completed"]}랩입니다.')
        limit = "격차가 초 단위이면 선두와의 시간 차이이며, +1 LAP은 한 바퀴 뒤라는 뜻입니다. DNF는 리타이어, DNS는 미출발, DSQ는 실격입니다. 피트·날씨·사고가 결과의 원인이었는지는 관련 기록을 따로 확인해야 합니다."
    guide = "섹터는 한 바퀴를 나눈 구간입니다. 랩 중앙값은 비교 대상 랩들을 시간순이 아닌 기록 크기순으로 세웠을 때 가운데 값으로, 한 번의 최속 기록과 다릅니다. H·M·S는 하드·미디엄·소프트, I·W는 인터미디어트·웨트 타이어입니다. 타이어가 다른 기록은 조건을 함께 보세요."
    facts_html = "".join(f"<li>{esc(text)}</li>" for text in facts)
    return (
        '<article class="beginner-notes"><h3>입문자를 위한 기록 설명</h3>'
        f'<h4>이 세션은 무엇을 보는 경기인가요?</h4><p>{esc(meaning)}</p>'
        f'<h4>이번 세션에서 확인된 기록</h4><ul>{facts_html or "<li>설명할 유효 기록이 아직 없습니다.</li>"}</ul>'
        f'<h4>표와 차트 읽는 법</h4><p>{esc(guide)}</p>'
        f'<h4>해석할 때 주의할 점</h4><p>{esc(limit)}</p></article>'
    )


def render_stints(rows):
    cards = []
    for row in rows:
        items = "".join(
            f'<li>{esc(s.get("compound") or "UNKNOWN")} '
            f'L{or_dash(s.get("lap_start"))}–{s.get("lap_end") or "?"} · '
            f'중앙값 {seconds(s["median"])} · 표본 {s["sample_count"]}랩</li>'
            for s in row["stints"]
        )
        cards.append(
            f'<article><h3>#{row["number"]} {esc(row["name"])}</h3>'
            f'<ul>{items or "<li>스틴트 데이터 없음</li>"}</ul></article>'
        )
    return (
        "<details><summary>전체 선수 타이어 스틴트 · 롱런 참고 지표</summary>"
        f'<div class="cards">{"".join(cards)}</div></details>'
    )


STYLE = """html{color-scheme:dark}body{background:#0b1321;color:#edf4fc;font:15px/1.7 system-ui,sans-serif;margin:0}main{max-width:1500px;margin:auto;padding:36px 22px}h1{font-size:clamp(28px,5vw,40px);line-height:1.25}h2{margin-top:48px;border-top:2px solid #335170;padding-top:22px}p,small{color:#b7c9df}small{display:block}a{color:#6deac9}.eyebrow{letter-spacing:2px;color:#6deac9;font-size:13px}.meta{font-size:13px}.notice{padding:16px;background:#342b20;border-left:3px solid #f1c472}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px;font-variant-numeric:tabular-nums}th,td{padding:11px;border-bottom:1px solid #314158;text-align:left}tbody tr:hover{background:#13203a}th,article{background:#152339}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px}article{padding:16px;border-radius:10px}article ul{padding-left:18px;margin:0}input,select,button{background:#152339;color:white;border:1px solid #46617d;padding:10px;margin:6px 6px 6px 0;font:inherit;border-radius:6px}input{min-width:260px}button{cursor:pointer}svg{width:100%;min-width:650px;background:#152339}svg text{fill:#b7c9df;font-size:13px}details{margin:20px 0}summary{cursor:pointer;color:#6deac9}@media print{html{color-scheme:light}body{background:white;color:black}small,p{color:#333}button,input,select{display:none}th,article,svg{background:#eee}svg text{fill:#333}.scroll{overflow:visible}table{font-size:8px;white-space:normal}article{break-inside:avoid}a{color:#15584a}}"""

METHODOLOGY = (
    "순위·완료 랩·점수·격차는 session_result 원본 값입니다. API가 순위를 제공하지 않으면 임의로 순위를 매기지 않습니다.",
    "퀄리파잉 Q1/Q2/Q3 기록은 API의 duration 배열만 사용합니다. 특정 단계 기록이 비어 있다는 이유만으로 탈락을 단정하지 않으며, 미진출·미출전·기록 삭제를 구분하려면 공식 판정과 대조해야 합니다.",
    "관측 최속은 양수 랩타임 중 race_control에서 삭제가 확인된 랩을 제외한 최솟값입니다. 공식 유효 랩 판정과 다를 수 있습니다.",
    "랩 중앙값과 스틴트 중앙값은 1랩, 피트 아웃 랩, 피트 진입 랩, 삭제 확인 랩, 시간이 누락된 랩을 제외하고 계산합니다. 연료량·트래픽·SC·VSC·트랙 변화는 보정하지 않으므로 순수 페이스나 롱런 우열을 단정할 수 없습니다. 스틴트별 표본 수를 함께 표시합니다.",
    "피트 진입 수는 관측된 랩의 시간 범위 안에서만 집계하며, 타이어 교체 횟수나 실제 정차 시간을 뜻하지 않습니다.",
    "공식 완료 랩(session_result)과 관측 랩 기록 수(laps)는 따로 집계합니다. 누락된 값은 0초나 0랩으로 바꾸지 않습니다.",
    "일반 주말에는 프랙티스 1·2·3을, 스프린트 주말에는 프랙티스 1과 스프린트 퀄리파잉·스프린트 레이스를 표시합니다.",
    "원본 데이터와 수집 시각은 세션별 JSON 스냅샷에 보존합니다. 자동 생성은 세션 종료 3시간 후 한 번만 조회하며, 접근이 막히거나 자료가 없으면 기존 스냅샷을 유지하고 자동으로 다시 조회하지 않습니다.",
)

CHART_CSS = ROOT / "tools" / "report_charts.css"
CHART_JS = ROOT / "tools" / "report_charts.js"

CHART_SECTION = """<section id="lap-sector-analysis" class="chart-workspace" style="scroll-margin-top:24px"><div class="chart-kicker">SESSION TELEMETRY</div><h2>랩타임 &amp; 섹터 분석</h2><div id="session-tabs" class="session-tabs" role="tablist" aria-label="세션 선택"></div><div id="chart-panel" role="tabpanel"><div class="chart-toolbar"><label for="chart-search">선수 / 팀 검색</label><input id="chart-search" type="search" placeholder="예: 노리스, 멕라렌, McLaren" aria-label="차트 선수 또는 팀 검색"><select id="chart-driver" aria-label="드라이버 선택"></select><span id="chart-search-status" class="meta" role="status" aria-live="polite"></span><label id="qualifying-phase-control" hidden>퀄리파잉 구간<select id="qualifying-phase" aria-label="퀄리파잉 구간"><option value="all">전체</option><option value="1">Q1</option><option value="2">Q2</option><option value="3">Q3</option><option value="unknown">미구분</option></select></label></div><p id="qualifying-record" class="meta" hidden></p><p id="chart-summary" class="chart-caption"></p><article class="chart-card"><h3>랩타임 <small>점에 마우스를 올리거나 터치하면 0.001초 단위 기록이 표시됩니다</small></h3><div class="scroll"><svg id="chart-time" viewBox="0 0 1100 320" role="img" aria-label="랩타임 차트"></svg></div></article><h3 class="sector-heading">섹터별 선수 시간</h3><p class="sector-hint">같은 세션·드라이버의 섹터 1·2·3 기록입니다. 기록이 없는 랩 앞뒤는 선으로 잇지 않습니다. 타이어는 스틴트의 명시된 랩 범위로 연결하며, 범위가 겹치거나 없으면 미확인입니다.</p><article class="chart-card"><h3>섹터 1</h3><div class="scroll"><svg id="chart-s1" viewBox="0 0 1100 320" role="img" aria-label="섹터 1 차트"></svg></div></article><article class="chart-card"><h3>섹터 2</h3><div class="scroll"><svg id="chart-s2" viewBox="0 0 1100 320" role="img" aria-label="섹터 2 차트"></svg></div></article><article class="chart-card"><h3>섹터 3</h3><div class="scroll"><svg id="chart-s3" viewBox="0 0 1100 320" role="img" aria-label="섹터 3 차트"></svg></div></article></div><p class="chart-caption">점 색상은 사용 타이어를 나타내며, 빨간 테두리는 삭제가 확인된 랩입니다 · 키보드 Tab으로 점을 선택할 수 있습니다 · 느린 랩도 생략하지 않고 표시합니다</p></section><div id="chart-tooltip" class="chart-tooltip" role="status" aria-live="polite" hidden></div>"""


def item_sources(item, events_html, video_html, qualifying_html, fastf1_html, appendix):
    """Per-item sources for one session, limited to sections that were rendered."""
    from report_sources import link, openf1, when
    from report_video import ROOT as video_root, video_sources
    from race_gaps import gap_sources
    from compare_player import player_sources
    from qualifying_replay import qualifying_sources
    from fastf1_source import fastf1_sources
    from race_overtakes import overtake_sources
    from race_attachments import attachment_sources
    session = item["session"]
    key = session.get("session_key", "")
    media = video_root / "reports" / f'weekend-{session.get("meeting_key")}' / "media"
    base = [
        "OpenF1 " + " · ".join(openf1(e, key) for e in ENDPOINTS) + f" · 수집 {when(item.get('fetched_at'))}"
    ]
    if item.get("data_source") == "fastf1":
        return [("임시 보고서 · 세션 결과 및 랩 기록", [
            link(item["fastf1_source_url"], "FastF1 원자료"),
            f"FastF1 {esc(item['fastf1_version'])} · 수집 {when(item.get('fetched_at'))}",
        ])]
    if session.get("meeting_key"):
        base.append(link(f'https://api.openf1.org/v1/sessions?meeting_key={session["meeting_key"]}', "OpenF1 주말 세션 목록"))
    found = [("기록 설명 · 결과 표 · 선수별 한 줄 평 · 타이어 스틴트 · 랩타임 & 섹터 분석", base)]
    if 'id="race-incidents"' in events_html:
        found.append(("레이스 주요 상황 · 리타이어", [f"OpenF1 {openf1('race_control', key)} · {openf1('session_result', key)} (보고서 스냅샷)"]))
    if 'id="race-gap-replay"' in video_html:
        found.append(("시간별 레이스 위치 · 앞차와 간격", gap_sources(item, media)))
    if 'id="rank-flow-video"' in video_html:
        found.append(("레이스 순위 흐름 MP4", video_sources(item, media)))
    if 'id="driver-replay"' in video_html:
        found.append(("두 선수 선택 · 차량 데이터 비교", player_sources(item, media)))
    if 'class="qualifying-replay"' in qualifying_html:
        found.append(("시간별 서킷 위치 · 유효 랩 · 타이어", qualifying_sources(item)))
    if fastf1_html:
        found.append(("FastF1 보조 데이터", fastf1_sources(item)))
    if appendix.get("pit"):
        found.append(("팀·선수별 피트스탑 기록", [f"OpenF1 {openf1('pit', key)} · {openf1('stints', key)} (보고서 스냅샷)"]))
    if appendix.get("tyres"):
        found.extend(attachment_sources(item, appendix["tyres"]))
    if appendix.get("overtakes"):
        found.append(("오버테이크 · 선수별 순위 교환 기록", overtake_sources(item)))
    return found


def render(snapshots, output, now=None, starting_tyre_summaries=None):
    now = now or datetime.now(timezone.utc)
    sections, chart_data, summary = [], [], []
    race_appendix = ""
    overtake_appendix = ""
    source_groups = []
    for item in snapshots:
        session = item["session"]
        name = session["session_name"]
        label = LABELS.get(name, name)
        data = item.get("data", {})
        rows = summarize(item) if data else []
        count = f"{len(rows)}명" if rows else "데이터 없음"
        summary.append(
            f'<li><a href="#{anchor(name)}">{label}</a> · {count} · {esc(item["status"])}</li>'
        )
        body = (
            f'<h2 id="{anchor(name)}">{label}</h2>'
            f'<p class="meta">{esc(item["status"])} · session_key {esc(session.get("session_key", "—"))}</p>'
        )
        if item.get("error"):
            body += (
                f'<p class="notice">이번 갱신에 실패했습니다({esc(item["error"])}). '
                "이전에 성공한 스냅샷이 있으면 그 데이터를 표시합니다.</p>"
            )
        if not rows:
            sections.append(
                body + "<p>아직 수집된 데이터가 없습니다. 세션이 열리지 않았거나 데이터 제공을 기다리는 중입니다.</p>"
            )
            continue
        body += (
            render_beginner_notes(name, rows)
            + render_table(name, rows) + render_verdicts(name, rows) + render_stints(rows)
        )
        provisional = item.get("data_source") == "fastf1"
        events_html = "" if provisional else render_race_events(item, rows)
        video_html = "" if provisional else render_video_section(item)
        qualifying_html = "" if provisional else render_qualifying(item)
        fastf1_html = "" if provisional else render_fastf1_source(item)
        body += events_html + video_html + qualifying_html + fastf1_html
        appendix = {}
        if name == "Race" and not provisional:
            appendix["pit"] = render_pitstops(item, rows)
            appendix["tyres"] = render_race_attachments(
                item, starting_tyre_summaries=starting_tyre_summaries
            )
            appendix["overtakes"] = overtake_appendix = render_overtakes(item)
            race_appendix = appendix["pit"] + appendix["tyres"]
        source_groups.append(
            (label, item_sources(item, events_html, video_html, qualifying_html, fastf1_html, appendix))
        )
        chart_data.extend(dict(row, session=label) for row in rows)
        sections.append(body)
    location = next(
        (
            x["session"].get("location")
            for x in snapshots
            if x["session"].get("location")
        ),
        "Grand Prix",
    )
    meeting = next(
        (
            s["session"].get("meeting_key")
            for s in snapshots
            if s["session"].get("meeting_key")
        ),
        "",
    )
    race_shortcut = (
        '<li><a href="#race-incidents">레이스 주요 상황 · 리타이어</a></li><li><a href="#race-pit-stops">팀·선수별 피트스탑 기록</a></li>'
        if race_appendix
        else ""
    )
    if 'id="race-tyre-attachments"' in race_appendix:
        race_shortcut += (
            '<li><a href="#race-tyre-attachments">그랑프리별 타이어 컴파운드와 스타트 타이어</a></li>'
        )

    if len(snapshots) == 1:
        only = LABELS.get(snapshots[0]["session"]["session_name"], snapshots[0]["session"]["session_name"])
        heading, coverage = f"{only} 보고서", f"{only} 단일 세션 보고서"
    else:
        heading = "주말 전체 선수 보고서"
        coverage = " · ".join(LABELS.get(item["session"]["session_name"], item["session"]["session_name"]) for item in snapshots)
    safe_json = json.dumps(chart_data, ensure_ascii=False).replace("</", "<\\/")
    methodology = "".join(f"<li>{text}</li>" for text in METHODOLOGY)
    chart_css = CHART_CSS.read_text(encoding=ENCODING)
    chart_js = CHART_JS.read_text(encoding=ENCODING).replace("REPORT_ROWS", safe_json)
    source_notice = ("OpenF1 자료와 FastF1 임시 자료를 사용합니다. 세션별 출처와 수집 상태를 확인할 수 있습니다."
        if any(item.get("data_source") == "fastf1" for item in snapshots) else "OpenF1 API 데이터로 만든 보고서입니다.")
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(location)} · F1 {esc(heading)}</title>
<style>{STYLE}</style></head><body>
<main><header><p class="eyebrow">SEONY F1 / WEEKEND REPORT</p><h1>{esc(location)} · {esc(heading)}</h1><p>{esc(coverage)}<br>생성 시각 {display_time(now)} · 출처는 맨 아래 <a href="#{report_sources.ANCHOR}">항목별 출처</a></p><button type="button" onclick="document.querySelectorAll('details').forEach(d=>d.open=true);window.print()">인쇄 / PDF 저장</button></header>
<p class="notice">{source_notice} FIA 공식 결과와 별도로 대조하지 않았습니다. 데이터 대기·누락·갱신 실패는 구분해 표시합니다. 각 세션의 선수 목록은 drivers·session_result·laps 응답에 나온 선수를 모두 합친 것입니다. 일정에 따라 아직 열리지 않은 세션이 있을 수 있습니다.</p>
<ul>{"".join(summary)}{race_shortcut}<li><a href="#lap-sector-analysis">랩타임 &amp; 섹터 분석</a> · 세션별 랩·섹터·타이어 차트</li><li><a href="#{report_sources.ANCHOR}">항목별 출처</a></li></ul><input id="search" type="search" placeholder="선수 / 팀 검색 (예: 노리스, 멕라렌)" aria-label="선수 또는 팀 검색">{"".join(sections)}
{CHART_SECTION}
<h2>지표 해석과 한계</h2><ul>{methodology}</ul>{race_appendix}{overtake_appendix}{report_sources.render_sources(source_groups)}</main>
<style>{chart_css}</style><script>{chart_js}</script></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding=ENCODING)


def session_end(session):
    """An explicit actual end beats the scheduled end."""
    return stamp(session.get("actual_date_end") or session["date_end"])


def collect(meeting_key=None, output_root=None, targets=None, now=None, allow_fastf1=False):
    """Collect a weekend. ``targets`` (automatic runs) limits API calls to those
    session keys; other sessions keep their cached snapshots."""
    now = now or datetime.now(timezone.utc)
    reports = output_root or ROOT / "reports"
    if targets is not None:
        targets = {int(key) for key in targets}
        for key in sorted(targets):
            # Record before any request so a crash cannot cause a repeated automatic query.
            report_attempts.record(reports, {"session_key": key, "meeting_key": meeting_key}, "started", now)
    try:
        sessions = fetch(
            "sessions", {"meeting_key": meeting_key} if meeting_key else {"year": now.year}
        )
    except requests.HTTPError as exc:
        catalog = reports / "catalog" / "sessions.json"
        if exc.response is None or exc.response.status_code != 401 or not catalog.exists():
            raise
        sessions = load_json(catalog)
        print("OpenF1 authentication restriction: using saved session metadata.")
    if meeting_key is None:
        past = [
            s
            for s in sessions
            if stamp(s["date_start"]) <= now and s["session_name"] in SESSION_NAMES
        ]
        if not past:
            raise ValueError("No started weekend available for the current year")
        meeting_key = max(past, key=lambda s: stamp(s["date_start"]))["meeting_key"]
    sessions = [s for s in sessions if s["meeting_key"] == meeting_key]
    directory = reports / f"weekend-{meeting_key}"
    save_json(directory / "sessions.json", sessions)
    snapshots, errors = [], []
    changed = not (directory / "weekend-report.html").exists()
    fetched_any = False
    auth_blocked = False
    for name in weekend_session_names(sessions):
        candidates = [s for s in sessions if s["session_name"] == name]
        if not candidates:
            snapshots.append(
                {
                    "session": {"session_name": name, "meeting_key": meeting_key},
                    "status": "일정 없음 / API 목록에 없음",
                    "data": {},
                }
            )
            continue
        session = max(candidates, key=lambda s: stamp(s["date_start"]))
        path = directory / "data" / f'{session["session_key"]}.json'
        previous = load_json(path) if path.exists() else None
        if session.get("is_cancelled"):
            snapshots.append({"session": session, "status": "취소", "data": {}})
            continue
        end = session_end(session)
        if targets is not None and session["session_key"] not in targets:
            snapshots.append(
                previous
                or {
                    "session": session,
                    "status": "수집 대기 (세션 종료 3시간 후 시작)"
                    if now < end + REPORT_DELAY
                    else "미수집 / 자동 대상 아님 (수동 요청 시 수집)",
                    "data": {},
                }
            )
            continue
        if now < end + REPORT_DELAY:
            if targets is not None:
                # The confirmed end is later than the schedule used by the gate.
                report_attempts.record(reports, session, "deferred_end_later", now, actual_end=end)
            snapshots.append(
                previous
                or {
                    "session": session,
                    "status": "수집 대기 (세션 종료 3시간 후 시작)",
                    "data": {},
                }
            )
            continue

        def attempt(status, session=session):
            if targets is not None:
                report_attempts.record(reports, session, status, now)

        attempt("started")
        try:
            data = {
                endpoint: fetch(endpoint, {"session_key": session["session_key"]})
                for endpoint in ENDPOINTS
            }
            if previous and "overtakes" in previous.get("data", {}):
                data["overtakes"] = previous["data"]["overtakes"]
            if not data["drivers"] or not data["laps"] or not data["session_result"]:
                raise ValueError(
                    "Required driver, lap or result data not available yet"
                )
            snapshot = {
                "session": session,
                "status": "수집 완료 (OpenF1 기준)",
                "fetched_at": now.isoformat(),
                "data": data,
            }
            new = (previous is None or previous.get("data_source") == "fastf1"
                   or previous.get("data") != data or previous.get("session") != session)
            changed = changed or new
            fetched_any = True
            save_json(path, snapshot)
            attempt("collected" if new else "unchanged")
        except (requests.RequestException, ValueError) as exc:
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 401:
                attempt("auth_restricted")
                if not allow_fastf1:
                    raise
                auth_blocked = True
                fallback = None
                if previous is None:
                    try:
                        from fastf1_source import fallback_snapshot
                        fallback = fallback_snapshot(session, now)
                    except Exception as fallback_error:
                        print(f"FastF1 fallback unavailable: {type(fallback_error).__name__}", file=sys.stderr)
                if fallback:
                    save_json(path, fallback)
                    snapshots.append(fallback)
                    changed = fetched_any = True
                    attempt("fastf1_provisional")
                else:
                    print(f"Session {session['session_key']}: OpenF1 HTTP 401; no new FastF1 report.")
                    snapshots.append(previous or {
                        "session": session,
                        "status": "OpenF1 인증 대기 / FastF1 자료 미제공",
                        "data": {},
                    })
                continue
            attempt("missing" if isinstance(exc, ValueError) else "failed")
            error = f"{type(exc).__name__}: {exc}"
            errors.append(f"{name}: {error}")
            snapshot = dict(previous) if previous else {"session": session, "data": {}}
            snapshot.update(status="갱신 실패 / 자동 재시도 안 함 (수동 요청 시 재수집)", error=error)
        snapshots.append(snapshot)
    if (targets is not None or auth_blocked) and not fetched_any:
        # Automatic run without collected target data (deferred or failed): attempt state only.
        changed = False
    if changed:
        render(snapshots, directory / "weekend-report.html", now)
    print(directory / "weekend-report.html")
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else (0 if changed else 2)


def load_offline(directory):
    snapshots = [load_json(p) for p in sorted((directory / "data").glob("*.json"))]
    snapshots = [s for s in snapshots if isinstance(s, dict) and "session" in s]
    if not snapshots:
        raise ValueError("No session snapshots found")
    by_name = {s["session"]["session_name"]: s for s in snapshots}
    schedule_path = directory / "sessions.json"
    schedule = load_json(schedule_path) if schedule_path.exists() else []
    sessions = [*schedule, *(snapshot["session"] for snapshot in snapshots)]
    return [
        by_name.get(
            n,
            {"session": {"session_name": n}, "status": "로컬 스냅샷 없음", "data": {}},
        )
        for n in weekend_session_names(sessions)
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--meeting",
        type=int,
        help="OpenF1 meeting_key; default: most recent started weekend",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--fastf1-fallback", action="store_true", help="Use FastF1 when OpenF1 returns HTTP 401")
    parser.add_argument("--defer-auth", action="store_true",
                        help="Preserve published reports on HTTP 401; no automatic retry (manual request only)")
    parser.add_argument("--sessions", default="",
                        help="Comma-separated session keys from the automatic gate; only these are fetched")
    parser.add_argument(
        "--offline",
        type=Path,
        help="Render an existing weekend directory without network access",
    )
    args = parser.parse_args()
    try:
        if args.offline:
            render(load_offline(args.offline), args.offline / "weekend-report.html")
            return 0
        targets = [int(x) for x in args.sessions.split(",") if x.strip()] or None
        if targets and args.meeting is None:
            raise ValueError("--sessions requires --meeting")
        result = collect(args.meeting, args.output_root, targets, allow_fastf1=args.fastf1_fallback)
        if args.defer_auth:
            write_collection_output(result == 0)
        return 0 if result == 2 else result
    except (requests.RequestException, ValueError) as exc:
        if args.defer_auth and isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 401:
            write_collection_output(False)
            message = "OpenF1 HTTP 401: attempt recorded, published reports preserved. No automatic retry; request a manual run."
            print(message)
            import os
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
                    handle.write(message + "\n")
            return 0
        print(f"Collection failed; existing reports preserved: {exc}", file=sys.stderr)
        return 1


def write_collection_output(collected):
    import os
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"collected={'true' if collected else 'false'}\n")


if __name__ == "__main__":
    raise SystemExit(main())
