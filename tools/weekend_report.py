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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openf1.util import openf1_client  # noqa: E402

SESSION_NAMES = ("Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race")
LABELS = dict(zip(SESSION_NAMES, ("프랙티스 1", "프랙티스 2", "프랙티스 3", "퀄리파잉", "레이스")))
ROOT = Path(__file__).resolve().parents[1]


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
            if (
                exc.response.status_code not in (429, 500, 502, 503, 504)
                or attempt == 3
            ):
                raise
            delay = exc.response.headers.get("Retry-After", "")
            time.sleep(min(60, int(delay)) if delay.isdigit() else 2 ** (attempt + 1))
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def seconds(value):
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        return "—"
    return f"{int(value // 60)}:{value % 60:06.3f}"


def esc(value):
    return html.escape(str(value))


def deleted_laps(messages):
    deleted = set()
    for message in messages:
        match = re.search(
            r"CAR (\d+).*TIME .*DELETED.*LAP (\d+)", message.get("message", "")
        )
        if match:
            deleted.add(tuple(map(int, match.groups())))
    return deleted


def summarize(snapshot):
    data = snapshot["data"]
    drivers = {x["driver_number"]: x for x in data.get("drivers", [])}
    results = {x["driver_number"]: x for x in data.get("session_result", [])}
    numbers = (
        set(drivers) | set(results) | {x["driver_number"] for x in data.get("laps", [])}
    )
    deleted = deleted_laps(data.get("race_control", []))
    all_laps = data.get("laps", [])
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
            samples = [
                x["lap_duration"]
                for x in clean
                if stint["lap_start"] <= x["lap_number"] <= (stint.get("lap_end") or -1)
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
                "position": result.get("position"),
                "status": "DSQ"
                if result.get("dsq")
                else "DNS"
                if result.get("dns")
                else "DNF"
                if result.get("dnf")
                else "기록 있음"
                if result
                else "결과 대기",
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
                "pits": len(pits),
                "records": len(laps),
                "stints": by_compound,
                "laps": [
                    {
                        "lap": x["lap_number"],
                        "time": x.get("lap_duration"),
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


def render(snapshots, output, now=None):
    now = now or datetime.now(timezone.utc)
    sections, chart_data = [], []
    summary = []
    for item in snapshots:
        session = item["session"]
        name = session["session_name"]
        label = LABELS[name]
        data = item.get("data", {})
        rows = summarize(item) if data else []
        summary.append(
            f'<li><a href="#{name.replace(" ", "-")}">{label}</a> · {len(rows)}명 · {esc(item["status"])}</li>'
        )
        body = f'<h2 id="{name.replace(" ", "-")}">{label}</h2><p>{esc(item["status"])} · session_key {esc(session.get("session_key", "—"))} · 수집 시각 {esc(item.get("fetched_at", "—"))} UTC</p>'
        if item.get("error"):
            body += f'<p class="notice">이번 갱신 실패: {esc(item["error"])}. 기존 데이터가 있으면 마지막 성공 스냅샷을 표시합니다.</p>'
        if not rows:
            sections.append(
                body + "<p>아직 수집된 데이터가 없습니다. 열리지 않았거나 데이터 제공을 기다리는 세션입니다.</p>"
            )
            continue
        bests = [r["fastest"] for r in rows if r["fastest"] is not None]
        best = min(bests) if bests else None
        head = (
            "<th>Q1</th><th>Q2</th><th>Q3</th><th>탈락 / 진출</th>"
            if name == "Qualifying"
            else "<th>관측 최속</th><th>최속 대비</th>"
        )
        records = []
        for row in rows:
            rank = row["position"] if row["position"] is not None else "—"
            if name == "Qualifying":
                q = row["q"]
                phase = (
                    "Q3 기록"
                    if q[2] is not None
                    else "Q2 기록 / Q3 없음"
                    if q[1] is not None
                    else "Q1 기록 / Q2 없음"
                    if q[0] is not None
                    else "단계 자료 없음"
                )
                extra = (
                    "".join(f"<td>{seconds(v)}</td>" for v in q) + f"<td>{phase}</td>"
                )
            else:
                delta = (
                    f'+{row["fastest"] - best:.3f}s'
                    if row["fastest"] is not None and best is not None
                    else "—"
                )
                extra = f'<td>{seconds(row["fastest"])}</td><td>{delta}</td>'
            gap = row["gap"]
            if isinstance(gap, list):
                gap = " / ".join(str(x) if x is not None else "—" for x in gap)
            elif isinstance(gap, (float, int)):
                gap = f"+{gap:.3f}s"
            records.append(
                f'<tr data-search="{esc((row["name"] + " " + row["team"]).lower())}"><td>{rank}</td><td><b>#{row["number"]} {esc(row["name"])}</b><small>{esc(row["team"])}</small></td><td>{row["status"]}</td>{extra}<td>{seconds(row["median"])}<small>표본 {row["samples"]}랩</small></td><td>{row["completed"] if row["completed"] is not None else "—"} / {row["records"]}</td><td>{esc(gap if gap is not None else "—")}</td><td>{row["points"] if row["points"] is not None else "—"}</td><td>{row["pits"]}</td></tr>'
            )
            chart_data.append(dict(row, session=label))
        body += f'<div class="scroll"><table><thead><tr><th>API 순위</th><th>드라이버 / 팀</th><th>상태</th>{head}<th>랩 중앙값</th><th>완료 / 기록 랩</th><th>API 선두 격차</th><th>점수</th><th>피트 진입</th></tr></thead><tbody>{"".join(records)}</tbody></table></div>'
        body += (
            '<details><summary>전체 선수 타이어 스틴트 · 롱런 참고 지표</summary><div class="cards">'
        )
        for row in rows:
            stint_text = (
                "".join(
                    f'<li>{esc(s.get("compound", "UNKNOWN"))} L{s["lap_start"]}–{s.get("lap_end") or "?"} · 중앙값 {seconds(s["median"])} / {s["sample_count"]}랩</li>'
                    for s in row["stints"]
                )
                or "<li>스틴트 데이터 없음</li>"
            )
            body += f'<article><h3>#{row["number"]} {esc(row["name"])}</h3><ul>{stint_text}</ul></article>'
        body += "</div></details>"
        sections.append(body)
    location = next(
        (
            x["session"].get("location")
            for x in snapshots
            if x["session"].get("location")
        ),
        "Grand Prix",
    )
    safe_json = json.dumps(chart_data, ensure_ascii=False).replace("</", "<\\/")
    page = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>F1 주말 전체 선수 보고서</title>
<style>html{color-scheme:dark}body{background:#0b1321;color:#edf4fc;font:15px/1.7 system-ui,sans-serif;margin:0}main{max-width:1500px;margin:auto;padding:36px 22px}h1{font-size:40px}h2{margin-top:48px;border-top:2px solid #335170;padding-top:22px}p,small{color:#b7c9df}small{display:block}a{color:#6deac9}.notice{padding:16px;background:#342b20;border-left:3px solid #f1c472}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px}th,td{padding:11px;border-bottom:1px solid #314158;text-align:left}th,article{background:#152339}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px}article{padding:16px;border-radius:10px}input,select,button{background:#152339;color:white;border:1px solid #46617d;padding:10px;margin:6px;font:inherit;border-radius:6px}svg{width:100%;min-width:650px;background:#152339}details{margin:20px 0}summary{cursor:pointer;color:#6deac9}@media print{html{color-scheme:light}body{background:white;color:black}small,p{color:#333}button,input,select{display:none}th,article,svg{background:#eee}.scroll{overflow:visible}table{font-size:8px;white-space:normal}article{break-inside:avoid}a{color:#15584a}}</style>
<main><header><p>SEONY F1 / WEEKEND REPORT</p><h1>@@LOCATION@@ · 주말 전체 선수 보고서</h1><p>프랙티스 1·2·3 + 퀄리파잉 + 레이스<br>생성 시각 @@NOW@@ UTC / 원본 OpenF1 API 기준</p><button onclick="document.querySelectorAll('details').forEach(d=>d.open=true);window.print()">인쇄 / PDF 저장</button></header><p class="notice">FIA 공식 결과와 독립 대조하지 않은 OpenF1 데이터 보고서입니다. 데이터 대기·누락·갱신 실패를 구분하고, 모든 선수는 각 세션의 drivers / 결과 / 랩 응답 합집합으로 포함합니다. 경기 전후 일정에 따라 아직 열리지 않은 세션이 있습니다.</p><ul>@@SUMMARY@@</ul><input id="search" placeholder="전체 표에서 선수 / 팀 검색" aria-label="선수 팀 검색">@@SECTIONS@@
<h2>선수별 세션 랩타임 차트</h2><select id="selection" aria-label="세션 및 선수 선택"></select><div class="scroll"><svg id="chart" viewBox="0 0 1100 360" role="img" aria-label="선택 선수 랩타임"></svg></div><p>긴 랩도 생략하지 않습니다. 빨간 점은 삭제 확인 랩입니다. 마우스를 올리면 랩 번호와 시간을 볼 수 있습니다.</p>
<h2>지표 해석과 한계</h2><ul><li>순위·완료 랩·포인트·격차는 session_result 원본입니다. API가 순위를 제공하지 않으면 임의 순위를 만들지 않습니다.</li><li>퀄리파잉 Q1/Q2/Q3는 API duration 배열만 사용합니다. 빈 단계만으로 탈락을 단정하지 않으며, 미진출·미출전·기록 삭제의 구분은 공식 판정 대조가 필요합니다.</li><li>관측 최속은 양수 랩 기록에서 race_control의 삭제 확인 랩을 제외한 최솟값입니다. 공식 유효 랩 판정과 다를 수 있습니다.</li><li>중앙값 및 스틴트 중앙값은 1랩·피트 아웃·피트 진입·삭제 확인·누락 시간을 제외합니다. 연료량·트래픽·SC·VSC·트랙 변화는 보정하지 않아 순수 페이스나 롱런 우열을 단정하지 않습니다. 스틴트별 표본 수를 함께 표시합니다.</li><li>피트 진입 수는 관측 랩의 시간 범위 안에서만 집계하며 타이어 교체 횟수나 실제 정차시간을 뜻하지 않습니다.</li><li>세션별 공식 완료 랩과 관측 랩 기록 수는 별개입니다. 누락을 0초나 0랩으로 바꾸지 않습니다.</li><li>스프린트 주말 등에서 프랙티스 2·3이 열리지 않으면 일정 없음으로 표시합니다. 이 보고서의 대상은 지정된 5개 세션이며 스프린트는 포함하지 않습니다.</li><li>원본과 수집 시각은 각 세션 JSON 스냅샷에 보존합니다. 라이브 진행 중 공개 API가 차단되면 기존 스냅샷을 유지하고 다음 예약 실행에서 재조회합니다.</li></ul><h2>출처</h2><p><a href="https://api.openf1.org/v1/sessions?meeting_key=@@MEETING@@">OpenF1 주말 세션 목록</a> · 각 session_key의 drivers, session_result, laps, stints, pit, race_control 엔드포인트.<br>이 HTML은 인터넷 없이 검색·차트·표를 사용할 수 있습니다.</p></main>
<script>const rows=@@DATA@@;const sel=document.getElementById('selection');rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=r.session+' / #'+r.number+' '+r.name;sel.append(o)});document.getElementById('search').oninput=e=>document.querySelectorAll('tr[data-search]').forEach(r=>r.hidden=!r.dataset.search.includes(e.target.value.toLowerCase()));function draw(){const svg=document.getElementById('chart'),r=rows[+sel.value];if(!r){svg.innerHTML='<text x="40" y="60" fill="white">데이터 대기</text>';return}const p=r.laps.filter(x=>Number.isFinite(x.time)&&x.time>0);if(!p.length){svg.innerHTML='<text x="40" y="60" fill="white">랩 기록 없음</text>';return}const low=Math.floor(Math.min(...p.map(x=>x.time))-2),high=Math.ceil(Math.max(...p.map(x=>x.time))+2),max=Math.max(2,...p.map(x=>x.lap)),X=l=>65+(l-1)/(max-1)*1000,Y=t=>300-(t-low)/(high-low)*265;let s='';for(let i=0;i<6;i++){const v=low+(high-low)*i/5,y=Y(v);s+=`<line x1="65" x2="1065" y1="${y}" y2="${y}" stroke="#40536c"/><text x="4" y="${y}" fill="#b7c9df">${v.toFixed(1)}s</text>`}let prev=null;for(const x of r.laps){if(!Number.isFinite(x.time)||x.time<=0){prev=null;continue}if(prev&&x.lap===prev.lap+1)s+=`<line x1="${X(prev.lap)}" y1="${Y(prev.time)}" x2="${X(x.lap)}" y2="${Y(x.time)}" stroke="#6deac9"/>`;s+=`<circle cx="${X(x.lap)}" cy="${Y(x.time)}" r="4" fill="${x.deleted?'#ff7474':'#6deac9'}"><title>L${x.lap}: ${x.time.toFixed(3)}초</title></circle>`;prev=x}for(let l=1;l<=max;l+=Math.max(1,Math.ceil(max/10)))s+=`<text x="${X(l)}" y="330" fill="#b7c9df">L${l}</text>`;svg.innerHTML=s}sel.onchange=draw;draw();</script></html>"""
    values = {
        "LOCATION": esc(location),
        "NOW": now.isoformat(),
        "SUMMARY": "".join(summary),
        "SECTIONS": "".join(sections),
        "DATA": safe_json,
        "MEETING": str(
            next(
                (
                    s["session"].get("meeting_key")
                    for s in snapshots
                    if s["session"].get("meeting_key")
                ),
                "",
            )
        ),
    }
    for key, value in values.items():
        page = page.replace("@@" + key + "@@", value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page)


def collect(meeting_key=None, output_root=None):
    now = datetime.now(timezone.utc)
    sessions = fetch(
        "sessions", {"meeting_key": meeting_key} if meeting_key else {"year": now.year}
    )
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
    directory = (output_root or ROOT / "reports") / f"weekend-{meeting_key}"
    save_json(directory / "sessions.json", sessions)
    snapshots, errors = [], []
    for name in SESSION_NAMES:
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
        previous = json.loads(path.read_text()) if path.exists() else None
        if session.get("is_cancelled"):
            snapshots.append({"session": session, "status": "취소", "data": {}})
            continue
        if now < stamp(session["date_end"]) + timedelta(minutes=30):
            snapshots.append(
                previous
                or {"session": session, "status": "종료 후 30분까지 수집 대기", "data": {}}
            )
            continue
        try:
            data = {
                endpoint: fetch(endpoint, {"session_key": session["session_key"]})
                for endpoint in (
                    "drivers",
                    "session_result",
                    "laps",
                    "stints",
                    "pit",
                    "race_control",
                )
            }
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
            save_json(path, snapshot)
        except (requests.RequestException, ValueError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            errors.append(f"{name}: {error}")
            snapshot = dict(previous) if previous else {"session": session, "data": {}}
            snapshot.update(status="갱신 실패 / 재시도 대기", error=error)
        snapshots.append(snapshot)
    render(snapshots, directory / "weekend-report.html", now)
    print(directory / "weekend-report.html")
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--meeting",
        type=int,
        help="OpenF1 meeting_key; default: most recent started weekend",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--offline",
        type=Path,
        help="Render an existing weekend directory without network access",
    )
    args = parser.parse_args()
    try:
        if args.offline:
            snapshots = [
                json.loads(p.read_text())
                for p in (args.offline / "data").glob("*.json")
            ]
            snapshots = [s for s in snapshots if isinstance(s, dict) and "session" in s]
            if not snapshots:
                raise ValueError("No session snapshots found")
            by_name = {s["session"]["session_name"]: s for s in snapshots}
            ordered = [
                by_name.get(
                    n,
                    {"session": {"session_name": n}, "status": "로컬 스냅샷 없음", "data": {}},
                )
                for n in SESSION_NAMES
            ]
            render(ordered, args.offline / "weekend-report.html")
            return 0
        return collect(args.meeting, args.output_root)
    except (requests.RequestException, ValueError) as exc:
        print(f"Collection failed; existing reports preserved: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
