"""Qualifying location replay with phase-specific completed valid lap times."""
import base64
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PRACTICE_SESSIONS = ("Practice 1", "Practice 2", "Practice 3")


def lap_compounds(snapshot):
    data = snapshot["data"]
    compounds = {}
    for stint in data.get("stints", []):
        start, end = stint.get("lap_start"), stint.get("lap_end")
        compound = stint.get("compound")
        if start is None or end is None or not compound:
            continue
        for lap in range(start, end + 1):
            compounds.setdefault((stint["driver_number"], lap), set()).add(compound.upper())
    return {key: next(iter(values)) for key, values in compounds.items() if len(values) == 1}


def practice_timing(snapshot):
    from weekend_report import deleted_laps
    from report_video import epoch

    session = snapshot["session"]
    data = snapshot["data"]
    start = epoch(session["date_start"])
    deleted = deleted_laps(data.get("race_control", []), data["laps"])
    laps = []
    for lap in data["laps"]:
        number, index = lap["driver_number"], lap["lap_number"]
        duration = lap.get("lap_duration")
        if (not lap.get("date_start") or not isinstance(duration, (int, float))
                or duration <= 0 or lap.get("is_pit_out_lap") or (number, index) in deleted):
            continue
        elapsed = epoch(lap["date_start"]) - start
        if elapsed >= 0:
            laps.append([number, 1, elapsed, duration, index])
    end = max([epoch(session["date_end"]) - start, *(r[2] + r[3] for r in laps)])
    return {"start": start, "phases": [[1, 0, end]], "laps": laps}


def replay_path(snapshot, directory):
    session = snapshot["session"]
    key, meeting = session["session_key"], session.get("meeting_key")
    directory = directory or ROOT / "reports" / f"weekend-{meeting}" / "media"
    kind = "practice" if session.get("session_name", "").startswith("Practice ") else "qualifying"
    return directory / f"{key}-{kind}.json.gz"


def timing_data(snapshot):
    from weekend_report import qualifying_windows, lap_qualifying_phase, deleted_laps
    from report_video import epoch
    windows=qualifying_windows(snapshot)
    if not windows:raise ValueError('No verified Q1/Q2/Q3 timing windows')
    start=min(a.timestamp() for _,a,_ in windows)
    deleted=deleted_laps(snapshot['data'].get('race_control',[]),snapshot['data']['laps'])
    laps=[]
    for r in snapshot['data']['laps']:
        if not r.get('date_start') or not isinstance(r.get('lap_duration'),(int,float)) or r['lap_duration']<=0:continue
        if r.get('is_pit_out_lap') or (r['driver_number'],r['lap_number']) in deleted:continue
        phase=lap_qualifying_phase(r,windows)
        if phase: laps.append([r['driver_number'],phase,epoch(r['date_start'])-start,r['lap_duration'],r['lap_number']])
    phases=[]
    for phase,a,b in windows:
        finish=[epoch(r['date']) for r in snapshot['data'].get('race_control',[]) if r.get('qualifying_phase')==phase and r.get('message')=='SESSION FINISHED' and r.get('date')]
        own_end=max((l[2]+l[3] for l in laps if l[1]==phase),default=b.timestamp()-start)
        boundary=min(b.timestamp()-start,max(finish)-start if finish else b.timestamp()-start)
        next_start=min((c.timestamp()-start for p,c,_ in windows if p>phase),default=float('inf'))
        phases.append([phase,a.timestamp()-start,min(next_start,max(boundary,own_end))])
    participants={str(phase):sorted({r['driver_number'] for r in snapshot['data']['laps'] if lap_qualifying_phase(r,windows)==phase}) for phase,_,_ in windows}
    return {'start':start,'phases':phases,'laps':laps,'participants':participants}


def collect_qualifying(snapshot,directory,fetch):
    from report_video import epoch,iso
    practice = snapshot['session']['session_name'] in PRACTICE_SESSIONS
    timing = practice_timing(snapshot) if practice else timing_data(snapshot)
    key=snapshot['session']['session_key'];directory.mkdir(parents=True,exist_ok=True)
    target = replay_path(snapshot, directory)
    signature=hashlib.sha256(json.dumps({'session':snapshot['session'],'data':snapshot['data']},sort_keys=True).encode()).hexdigest()
    old=json.loads(gzip.decompress(target.read_bytes())) if target.exists() else {}
    start=timing['start'];end=start+max(p[2] for p in timing['phases'])
    if old.get('signature')==signature and old.get('complete') and old.get('queried_end',-1)>=end-start:return False
    value=old if old.get('signature')==signature else dict(timing,signature=signature,session_key=key,drivers=[],source='https://openf1.org/docs/#location',fetched_at=datetime.now(timezone.utc).isoformat())
    cached={d['number']:d for d in value['drivers']}
    value.update(timing)
    if practice and not target.exists():
        target.write_bytes(gzip.compress(json.dumps(value, separators=(',', ':')).encode(), mtime=0))
    for d in snapshot['data']['drivers']:
        number=d['driver_number']
        existing=cached.get(number,{}).get('locations',[])
        if existing and existing[-1][0]/1000>=end-start-2:continue
        query_start=start+existing[-1][0]/1000 if existing else start-1
        rows=fetch('location',{'session_key':key,'driver_number':number,'date>':iso(query_start),'date<':iso(end+1)})
        if any(r.get('session_key')!=key or r.get('driver_number')!=number for r in rows):raise ValueError('Qualifying location identity mismatch')
        locations=existing[:];last=locations[-1][0] if locations else -1e20
        for r in sorted(rows,key=lambda r:r['date']):
            t=round((epoch(r['date'])-start)*1000)
            if t-last>=500 and r.get('x') is not None and r.get('y') is not None:
                locations.append([t,r['x'],r['y']]);last=t
        cached[number]={'number':number,'name':d.get('name_acronym',str(number)),'color':'#'+(d.get('team_colour') or 'b6c7dc'),'locations':locations}
        value['drivers']=list(cached.values())
        tmp=target.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0));tmp.replace(target)
        print(f'Qualifying {key} driver {number}: {len(locations)} locations',flush=True)
    value['track'] = []
    for lap in sorted(value['laps'], key=lambda row: row[3]):
        points = cached.get(lap[0], {}).get('locations', [])
        track = [r for r in points if lap[2]*1000 <= r[0] <= (lap[2]+lap[3])*1000]
        if len(track) >= 3 and track[-1][0]-track[0][0] >= lap[3]*900:
            value['track'] = [r[1:] for r in track]
            break
    from circuit_geometry import enrich_mapped_pit
    enrich_mapped_pit(snapshot,value)
    value['complete']=True
    value['queried_end']=end-start
    target.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0));return True


def render_qualifying(snapshot,directory=None):
    session = snapshot["session"]
    name = session.get("session_name", "")
    practice = name in PRACTICE_SESSIONS and bool(snapshot.get("data", {}).get("laps"))
    if name != "Qualifying" and not practice:
        return ""
    key = session["session_key"]
    path = replay_path(snapshot, directory)
    if not path.exists():
        return ""
    meta = json.loads(gzip.decompress(path.read_bytes()))
    if meta.get("session_key") != key or (not practice and not meta.get("complete")):
        return ""
    if practice:
        recorded = {d["number"]: d for d in meta.get("drivers", [])}
        for d in snapshot["data"].get("drivers", []):
            number = d["driver_number"]
            recorded.setdefault(number, {"number": number, "name": d.get("name_acronym") or str(number),
                                         "color": "#" + (d.get("team_colour") or "b6c7dc"), "locations": []})
        meta.update(practice_timing(snapshot), label=f"FP{name[-1]}", drivers=list(recorded.values()))
    compounds = lap_compounds(snapshot)
    for lap in meta.get("laps", []):
        lap[5:] = [compounds.get((lap[0], lap[4]))]
    payload = base64.b64encode(gzip.compress(json.dumps(meta, separators=(",", ":")).encode(), mtime=0)).decode()
    script = (ROOT / "tools/qualifying_replay.js").read_text(encoding="utf-8")
    title = f"시간별 FP{name[-1]} 위치 · 유효 랩" if practice else "시간별 퀄리파잉 위치 · Q1/Q2/Q3"
    phases = ('<label hidden><select class="q-phase"><option value="1">FP</option></select></label>' if practice
              else '<label>단계 <select class="q-phase" aria-label="퀄리파잉 단계"><option value="1">Q1</option><option value="2">Q2</option><option value="3">Q3</option></select></label>')
    location_note = (
        "위치 자료가 없는 차량과 시간대는 지도에서 생략합니다. 순위표에는 재생 시각까지 완료한 유효 랩의 최고 기록을 표시합니다. 회색 선은 저장된 주행 좌표를 바탕으로 그린 서킷 참고선입니다."
        if practice else "선택한 단계의 실제 서킷 위치를 표시합니다."
    )
    canvas = '<canvas class="q-canvas" width="1280" height="680" style="width:100%;max-width:1280px" aria-label="서킷 위치와 유효 최고 랩"></canvas>'
    if practice:
        canvas = """<style>
.practice-replay-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.practice-replay-grid h4{color:#6deac9;margin:0 0 .65rem}
.practice-timing{overflow:auto;max-height:32rem;border:1px solid #33465f;border-radius:8px}
.practice-timing table{width:100%;min-width:315px;white-space:nowrap;font-size:.95rem}
.practice-timing th,.practice-timing td{padding:.45rem;text-align:left}
.practice-timing th{position:sticky;top:0;background:#18263b}
.practice-timing tr:first-child td{background:#1b3556}
.practice-replay-grid canvas{display:block;width:100%;height:auto}
@media(max-width:760px){.practice-replay-grid{grid-template-columns:minmax(0,1fr)}}
</style><div class="practice-replay-grid"><section><h4>드라이버 타이밍</h4>
<div class="practice-timing" role="region" aria-label="프랙티스 드라이버 타이밍" tabindex="0">
<table><thead><tr><th>드라이버</th><th>1위와의 차이</th><th>유효 최고 랩</th><th>타이어</th></tr></thead>
<tbody class="q-timing"><tr><td colspan="4">아직 완료된 유효 랩이 없습니다.</td></tr></tbody></table></div></section>
<section><h4>서킷 위치 · 시간별 재생</h4><canvas class="q-canvas" width="540" height="680" aria-label="프랙티스 서킷 위치"></canvas></section></div>"""
    return f'''<section class="qualifying-replay" id="qualifying-replay-{key}"><h3>{title}</h3><p>{location_note} 1위와의 차이는 각 선수의 유효 최고 랩을 비교한 값입니다. 타이어는 해당 랩의 스틴트 기준이며, 확인할 수 없으면 미확인으로 표시합니다.</p>
<p>{phases} <button class="q-play" type="button">일시정지</button> <input class="q-seek" type="range" min="0" max="1000" value="0" aria-label="세션 재생 위치" style="width:40%"> <select class="q-rate" aria-label="세션 재생 속도"><option value="1">1배속</option><option value="4" selected>4배속</option><option value="8">8배속</option><option value="16">16배속</option><option value="32">32배속</option></select> <span class="q-clock"></span></p>
<p class="q-status" role="status">위치 데이터를 준비하고 있습니다.</p>{canvas}
<p>기록은 랩 완료 뒤 반영하며, 삭제 기록과 대조해 식별된 랩과 아웃랩은 제외합니다. 위치가 2초 넘게 비면 숨깁니다. 미관측 위치를 피트에 있다고 추정하지 않습니다.</p>
<p>청록색 피트레인은 지도 경로를 근사 정합한 참고선이며 실제 차량 궤적과는 구분합니다.</p>
<script class="q-payload" type="application/octet-stream">{payload}</script><script>{script}</script></section>'''


def qualifying_sources(snapshot,directory=None):
    """Sources for the Q1/Q2/Q3 replay; call only when it is rendered."""
    from report_sources import map_credit,openf1,when
    key=snapshot['session'].get('session_key');meeting=snapshot['session'].get('meeting_key')
    directory=directory or ROOT/'reports'/f'weekend-{meeting}'/'media'
    path=replay_path(snapshot, directory)
    meta=json.loads(gzip.decompress(path.read_bytes())) if path.exists() else {}
    practice = snapshot["session"].get("session_name") in PRACTICE_SESSIONS
    if meta.get("session_key") != key:
        meta = {}
    if not practice and not meta.get("complete"):return []
    entries = [f"유효 랩·타이어: OpenF1 {openf1('race_control',key)} · {openf1('laps',key)} · {openf1('stints',key)} (보고서 스냅샷)"]
    if any(driver.get("locations") for driver in meta.get("drivers", [])):
        entries.append(f"위치: OpenF1 {openf1('location',key)} · 수집 {when(meta.get('fetched_at'))}")
    if meta.get("track_session_key"):
        entries.append(f"서킷 참고선: 라스베이거스 퀄리파잉 OpenF1 {openf1('location',meta['track_session_key'])}")
    return entries+map_credit(meta.get('pit_reference'))
