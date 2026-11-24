"""Qualifying location replay with phase-specific completed valid lap times."""
import base64
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


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
    timing=timing_data(snapshot);key=snapshot['session']['session_key'];directory.mkdir(parents=True,exist_ok=True)
    target=directory/f'{key}-qualifying.json.gz'
    signature=hashlib.sha256(json.dumps({'session':snapshot['session'],'data':snapshot['data']},sort_keys=True).encode()).hexdigest()
    old=json.loads(gzip.decompress(target.read_bytes())) if target.exists() else {}
    start=timing['start'];end=start+max(p[2] for p in timing['phases'])
    if old.get('signature')==signature and old.get('complete') and old.get('queried_end',-1)>=end-start:return False
    value=old if old.get('signature')==signature else dict(timing,signature=signature,session_key=key,drivers=[],source='https://openf1.org/docs/#location',fetched_at=datetime.now(timezone.utc).isoformat())
    cached={d['number']:d for d in value['drivers']}
    value.update(timing)
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
    best=min(value['laps'],key=lambda r:r[3],default=None)
    points=cached.get(best[0],{}).get('locations',[]) if best else []
    value['track']=[r[1:] for r in points if best and best[2]*1000<=r[0]<=(best[2]+best[3])*1000]
    from circuit_geometry import enrich_mapped_pit
    enrich_mapped_pit(snapshot,value)
    value['complete']=True
    value['queried_end']=end-start
    target.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0));return True


def render_qualifying(snapshot,directory=None):
    if snapshot['session'].get('session_name')!='Qualifying':return ''
    key=snapshot['session']['session_key'];meeting=snapshot['session'].get('meeting_key')
    directory=directory or ROOT/'reports'/f'weekend-{meeting}'/'media'
    path=directory/f'{key}-qualifying.json.gz'
    if not path.exists():return ''
    meta=json.loads(gzip.decompress(path.read_bytes()))
    if meta.get('session_key')!=key or not meta.get('complete'):return ''
    payload=base64.b64encode(path.read_bytes()).decode();script=(ROOT/'tools/qualifying_replay.js').read_text(encoding='utf-8')
    return f'''<section class="qualifying-replay" id="qualifying-replay-{key}"><h3>시간별 퀄리파잉 위치 · Q1/Q2/Q3</h3><p>선택한 단계의 실제 서킷 위치와 그 시점까지 완료한 유효 최고 랩입니다. 오른쪽 차이는 해당 단계 1위 랩타임과의 차이이며, 차량 사이 주행 간격이 아닙니다.</p>
<p><label>단계 <select class="q-phase" aria-label="퀄리파잉 단계"><option value="1">Q1</option><option value="2">Q2</option><option value="3">Q3</option></select></label> <button class="q-play" type="button">일시정지</button> <input class="q-seek" type="range" min="0" max="1000" value="0" aria-label="퀄리파잉 재생 위치" style="width:40%"> <select class="q-rate" aria-label="퀄리파잉 재생 속도"><option value="1">1배속</option><option value="4" selected>4배속</option><option value="8">8배속</option><option value="16">16배속</option><option value="32">32배속</option></select> <span class="q-clock"></span></p>
<p class="q-status" role="status">위치 데이터를 준비하고 있습니다.</p><canvas class="q-canvas" width="1280" height="680" style="width:100%;max-width:1280px" aria-label="퀄리파잉 위치와 단계별 최고 랩"></canvas>
<p>기록은 랩 완료 뒤 반영하며, 최종 삭제 확인 랩과 아웃랩은 제외합니다. 단계 구간은 세션 시작·종료 기록을 사용합니다. 위치가 2초 넘게 비면 숨깁니다. 미관측 위치를 피트에 있다고 추정하지 않습니다. 출처: OpenF1 location·laps·race_control.</p>
<p>청록색 피트레인은 지도 경로를 근사 정합한 참고선입니다. © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors · ODbL 1.0</a> · 정합 기준 <a href="https://github.com/bacinger/f1-circuits">bacinger/f1-circuits · MIT</a>. 실제 차량 궤적과는 구분합니다.</p>
<script class="q-payload" type="application/octet-stream">{payload}</script><script>{script}</script></section>'''
