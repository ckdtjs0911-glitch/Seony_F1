"""Race-only event timeline and retirement list from explicit OpenF1 records."""

from datetime import datetime, timedelta, timezone
from html import escape
import re
from itertools import groupby


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except (ValueError, AttributeError):
        return None


def event_label(record):
    message = (record.get("message") or "").upper()
    flag = (record.get("flag") or "").upper().replace("_", " ")
    if flag=='CLEAR' and record.get('scope')=='Sector':
        return '주의 구간 해제'
    if flag == "RED" or re.search(r"\bRED FLAG\b", message):
        return "레드 플래그"
    if "VIRTUAL SAFETY CAR" in message or message.startswith("VSC "):
        if re.search(r'\bENDED\b',message):
            return 'VSC 종료'
        if 'DEPLOYED' in message:
            return 'VSC 투입'
        return "VSC 종료 예고" if "ENDING" in message else "VSC"
    if "SAFETY CAR" in message:
        if 'LAPPED CARS' in message and 'OVERTAKE' in message:
            return '주회 뒤처진 차량 추월 허용'
        if 'LIGHTS OFF' in message:
            return '세이프티카 표시등 꺼짐'
        if re.search(r'\bENDED\b',message):
            return '세이프티카 종료'
        if "IN THIS LAP" in message:
            return "SC 철수 예고"
        if "DEPLOYED" in message:
            return "세이프티카 투입"
        return "세이프티카 안내"
    if flag == "DOUBLE YELLOW" or "DOUBLE YELLOW" in message:
        return "더블 옐로 플래그"
    if flag == "YELLOW" or message.startswith("YELLOW IN "):
        return "옐로 플래그"
    if "RESUMPTION ORDER" in message:
        return "재출발 순서 안내"
    if "WILL RESUME" in message or "WILL RESTART" in message:
        return "재출발 예정"
    if "RESTART" in message or "RESUMED" in message or message == "SESSION RESUMED":
        return "재개 안내"
    if "SUSPENDED" in message or "ABORTED" in message:
        return "세션 중단"
    if flag == "GREEN" and record.get("scope") == "Track":
        return "트랙 그린 플래그"
    if flag == "CHEQUERED":
        return "체커드 플래그"
    return None


def race_events(snapshot):
    if snapshot["session"]["session_name"] != "Race":
        return []
    data = snapshot.get("data", {})
    laps = data.get("laps", [])
    starts = [parse_time(lap.get("date_start")) for lap in laps]
    starts = [time for time in starts if time]
    if not starts:
        return []
    start = min(starts)
    end = max(
        parse_time(lap["date_start"]) + timedelta(seconds=lap.get("lap_duration") or 0)
        for lap in laps
        if parse_time(lap.get("date_start"))
    )
    events = []
    for record in data.get("race_control", []):
        date = parse_time(record.get("date"))
        label = event_label(record)
        if label and date and start <= date <= end:
            events.append(dict(record, label=label))
    return sorted(events, key=lambda record: parse_time(record["date"]))


def render_race_events(snapshot, rows):
    if snapshot["session"]["session_name"] != "Race":
        return ""

    def esc(value):
        return escape(str(value))

    events = race_events(snapshot)
    header = (
        '<section id="race-incidents"><h3>레이스 주요 상황 · 리타이어</h3>'
        '<p class="meta">경기 통제 기록을 한국어로 정리했습니다 · 시각은 UTC · SC 철수 예고·재출발 예정은 실제 재출발과 구분합니다. '
        "그린 플래그만으로 재출발을 단정하지 않습니다. 트랙 구간 번호는 랩타임 섹터 1·2·3과 다를 수 있습니다.</p>"
    )
    body = "<h4>레이스 상황 타임라인</h4>"
    safety=[e for e in events if 'SAFETY CAR' in (e.get('message') or '').upper() or (e.get('message') or '').upper().startswith('VSC ')]
    if safety:
        body+='<aside class="notice"><strong>세이프티카 · VSC 운영 안내</strong><p>SC는 실제 세이프티카 투입, VSC는 가상 세이프티카 안내입니다. 철수 예고·표시등 꺼짐과 종료를 별도로 표시합니다. 명시적 종료 기록이 없으면 종료 시각이나 지속 시간을 추정하지 않습니다.</p>'
        for event in safety:
            lap=event.get('lap_number');when=parse_time(event['date']).strftime('%H:%M:%S')
            body+=f'<p>{esc(str(lap)+"랩" if lap is not None else "랩 미확인")} · {when} UTC — {esc(event["label"])}</p>'
        body+='</aside>'
    if events:
        body += """<style>
.event-flow{display:flex;align-items:stretch;gap:12px;overflow-x:auto;padding:10px 0 18px;list-style:none;margin:0}
.event-flow li{display:flex;align-items:center;gap:12px}
.event-card{min-width:210px;padding:16px 20px;background:#152339;border:1px solid #35465e;border-left:4px solid var(--flag);border-radius:12px}
.event-card strong{display:block;color:var(--flag);margin:8px 0;font-size:17px}.event-card p{margin:4px 0}
.event-card time{color:#a9bed7;font-size:13px}.event-arrow{color:#60c6f5;font-size:26px}.event-lap{margin-top:18px;font-size:16px}
.event-flow:focus{outline:2px solid #60c6f5}</style>
<p class="meta">화살표는 같은 랩에 기록된 안내의 시간 순서이며, 사건의 인과관계를 뜻하지 않습니다.</p>"""
        for lap, group in groupby(events,key=lambda e:e.get('lap_number')):
            body += f'<h5 class="event-lap">{esc(str(lap)+"랩" if lap is not None else "랩 미확인")}</h5><ol class="event-flow" tabindex="0" aria-label="랩별 상황 안내">'
            for index,event in enumerate(group):
                label=event['label'];when=parse_time(event['date']).astimezone(timezone.utc).strftime('%H:%M:%S')
                scope='서킷 전체' if event.get('scope')=='Track' else '해당 차량' if event.get('scope')=='Driver' else '범위 미확인'
                if event.get('sector') is not None:scope=f'트랙 구간 {event["sector"]}'
                if event.get('driver_number') is not None:scope+=f' · #{event["driver_number"]}'
                if label=='주회 뒤처진 차량 추월 허용':
                    numbers=re.findall(r'\d+', (event.get('message') or '').split(':',1)[-1]) if ':' in (event.get('message') or '') else []
                    if numbers:scope='허용 차량 · '+', '.join('#'+n for n in numbers)
                color='#ff687c' if '레드' in label or '중단' in label else '#ffd65c' if '옐로' in label or '세이프티' in label or 'SC' in label else '#6deac9' if '해제' in label or '그린' in label else '#b6c7dc'
                arrow='<span class="event-arrow" aria-hidden="true">→</span>' if index else ''
                body+=f'<li>{arrow}<article class="event-card" style="--flag:{color}"><time>{when} UTC</time><strong>{esc(label)}</strong><p>범위 · {esc(scope)}</p></article></li>'
            body+='</ol>'
    else:
        body += "<p>표시할 레이스 상황 메시지가 없습니다. 메시지 누락 가능성이 있어 사건이 없었다는 뜻은 아닙니다.</p>"
    body += "<h4>리타이어 및 미출전·실격</h4>"
    retired = [row for row in rows if row["status"] in ("DNF", "DNS", "DSQ")]
    if retired:
        body += '<p class="meta">DNF는 결과 API 기준입니다. 완료 랩 수·마지막 관측 랩은 리타이어 발생 랩이나 시각이 아닙니다. 원인은 추정하지 않습니다.</p><div class="scroll result-table"><table><thead><tr><th>선수</th><th>상태</th><th>공식 완료 랩</th><th>마지막 관측 랩</th><th>리타이어 시각·원인</th></tr></thead><tbody>'
        for row in retired:
            last = max((lap["lap"] for lap in row["laps"]), default=None)
            search = esc((row["name"] + " " + row["team"]).lower())
            body += f'<tr data-search="{search}"><td>#{row["number"]} {esc(row["name"])}<small>{esc(row["team"])}</small></td><td>{row["status"]}</td><td>{row["completed"] if row["completed"] is not None else "—"}</td><td>{last if last is not None else "—"}</td><td>미확인</td></tr>'
        body += "</tbody></table></div>"
    else:
        body += "<p>수집된 결과에서 DNF·DNS·DSQ로 표시된 선수는 없습니다. 결과 미수집 시에는 판정을 보류합니다.</p>"
    return header + body + "</section>"
