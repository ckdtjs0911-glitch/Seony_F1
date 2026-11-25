"""Race-only interval records and approximate circuit location replay."""
import base64
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gap_text(row, leader=False):
    if leader:
        return '선두'
    value = row.get('interval') if row else None
    if isinstance(value, (int, float)) and value >= 0:
        return f'+{value:.3f} s'
    if isinstance(value, str) and 'LAP' in value.upper():
        return value
    return '—'


def collect_gaps(snapshot, directory, fetch):
    from report_video import epoch, iso
    key = snapshot['session']['session_key']
    path = directory / f'{key}-intervals.json'
    if not path.exists():
        rows = fetch('intervals', {'session_key': key})
        if not rows or any(x.get('session_key') != key for x in rows):
            raise ValueError('Intervals missing or wrong session')
        path.write_text(json.dumps({'session_key': key, 'source':'https://openf1.org/docs/#intervals', 'fetched_at':datetime.now(timezone.utc).isoformat(),'rows':rows}, ensure_ascii=False), encoding='utf-8')
    intervals = json.loads(path.read_text(encoding='utf-8'))
    if intervals['session_key'] != key:
        raise ValueError('Wrong gap session')
    target = directory / f'{key}-track.json.gz'
    old = json.loads(gzip.decompress(target.read_bytes())) if target.exists() else {}
    if old.get('complete'):
        return enrich_pits(snapshot, old, target)
    laps = [x for x in snapshot['data']['laps'] if x.get('date_start') and x.get('lap_duration')]
    start = min(epoch(x['date_start']) for x in laps)
    end = max(epoch(x['date_start']) + x['lap_duration'] for x in laps)
    value = old or {'session_key':key,'start':start,'end':end,'drivers':[], 'source':'https://openf1.org/docs/', 'reference':'https://f1cosmos.com/ko/dashboard/replay/11326', 'reference_checked':'User screenshots only; replay page inaccessible', 'fetched_at':datetime.now(timezone.utc).isoformat()}
    cached = {d['number']:d for d in value['drivers']}
    raw_path = directory / f'{key}-video-data.json'
    positions = json.loads(raw_path.read_text(encoding='utf-8'))['position']
    for d in snapshot['data']['drivers']:
        number=d['driver_number']
        if cached.get(number,{}).get('locations'):
            continue
        rows=fetch('location',{'session_key':key,'driver_number':number,'date>':iso(start-1),'date<':iso(end+1)})
        if any(r.get('session_key')!=key or r.get('driver_number')!=number for r in rows):
            raise ValueError('Location session/driver mismatch')
        locations=[];last=-1e20
        for r in sorted(rows,key=lambda r:r['date']):
            t=round((epoch(r['date'])-start)*1000)
            if t-last>=500 and r.get('x') is not None and r.get('y') is not None:
                locations.append([t,r['x'],r['y']]);last=t
        driver={'number':number,'name':d.get('name_acronym',str(number)), 'color':'#'+(d.get('team_colour') or 'b6c7dc'), 'locations':locations,
                'positions':sorted([[round((epoch(r['date'])-start)*1000),r['position']] for r in positions if r['driver_number']==number]),
                'gaps':sorted([[round((epoch(r['date'])-start)*1000),r.get('interval'),r.get('gap_to_leader')] for r in intervals['rows'] if r['driver_number']==number])}
        cached[number]=driver;value['drivers']=list(cached.values())
        target.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0))
        print(f'Track {key} driver {number}: {len(locations)} locations',flush=True)
    winner=next((r['driver_number'] for r in snapshot['data']['session_result'] if r.get('position')==1),None)
    own=sorted([x for x in laps if x['driver_number']==winner],key=lambda x:x['lap_number'])
    chosen=own[-2] if len(own)>1 else own[0]
    a=(epoch(chosen['date_start'])-start)*1000;b=a+chosen['lap_duration']*1000
    driver=cached.get(winner,{})
    value['track']=[r[1:] for r in driver.get('locations',[]) if a<=r[0]<=b]
    value['complete']=True
    target.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0))
    enrich_pits(snapshot, value, target)
    return True


def enrich_pits(snapshot, value, target):
    """Annotate recorded pit laps; a separate lane is inferred only from observed deviations."""
    import math
    import statistics
    import hashlib
    from report_video import epoch
    signature=hashlib.sha256(json.dumps({'pit':snapshot['data'].get('pit',[]),'laps':snapshot['data']['laps'],'track':value.get('track',[])},sort_keys=True).encode()).hexdigest()
    if value.get('pit_signature')==signature:
        return False
    track=value.get('track',[])
    spacing=[math.dist(a,b) for a,b in zip(track,track[1:]) if math.dist(a,b)>0]
    threshold=max(20,statistics.median(spacing)*1.2) if spacing else math.inf
    segments=[]
    for driver in value['drivers']:
        pit_laps={p.get('lap_number') for p in snapshot['data'].get('pit',[]) if p['driver_number']==driver['number']}
        spans=[]
        for lap in snapshot['data']['laps']:
            if lap['driver_number']==driver['number'] and lap.get('lap_number') in pit_laps and lap.get('date_start') and lap.get('lap_duration'):
                start=round((epoch(lap['date_start'])-value['start'])*1000)
                spans.append([start,start+lap['lap_duration']*1000])
        driver['pit_laps']=spans
        for start,end in spans:
            group=[]
            for row in driver.get('locations',[]):
                if not start<=row[0]<=end:continue
                distance=min((math.dist(row[1:],p) for p in track),default=0)
                if distance>threshold:
                    group.append(row[1:])
                else:
                    if len(group)>=5:segments.append(group)
                    group=[]
            if len(group)>=5:segments.append(group)
    value['pit_tracks']=segments
    value['pit_version']=1
    value['pit_signature']=signature
    from circuit_geometry import enrich_mapped_pit
    enrich_mapped_pit(snapshot,value)
    target.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0))
    return True


def render_gaps(snapshot, directory):
    if snapshot['session'].get('session_name')!='Race':return ''
    path=directory/f'{snapshot["session"]["session_key"]}-track.json.gz'
    if not path.exists():return ''
    script=(ROOT/'tools/race_gaps.js').read_text(encoding='utf-8')
    payload=base64.b64encode(path.read_bytes()).decode()
    return '''<section id="race-gap-replay"><h3>시간별 레이스 위치 · 앞차와 간격</h3><p>왼쪽은 실제 위치 기록을 사용한 근사 서킷 지도, 오른쪽은 선두와의 시간차를 원형으로 펼친 보기입니다. 이름 옆 수치는 앞차와의 간격이며 단위는 s(초)입니다.</p>
<p><button type="button" id="gap-play">일시정지</button> <input id="gap-seek" type="range" min="0" max="1000" value="0" aria-label="레이스 시간" style="width:50%"> <select id="gap-rate" aria-label="레이스 재생 속도"><option value="1">1배속</option><option value="4" selected>4배속</option><option value="8">8배속</option><option value="16">16배속</option><option value="32">32배속</option></select> <span id="gap-clock"></span></p>
<p id="gap-status" role="status">위치 데이터를 준비하고 있습니다.</p><canvas id="gap-canvas" width="1280" height="600" style="width:100%;max-width:1280px" aria-label="시간별 서킷 위치와 원형 시간 간격"></canvas>
<p>간격은 OpenF1 intervals의 최근 10초 이내 기록만 표시합니다. 위치는 0.5초 간격으로 저장하며 2초 넘는 공백은 숨깁니다. 랩 차이는 초로 바꾸지 않고 +1 LAP처럼 표시합니다. 점의 중간 이동은 표시용 보간입니다.</p>
<p>청록색 PIT LANE은 확인된 지도 경로를 세션 좌표에 근사 정합한 참고선입니다. 차량의 실제 피트 이동 궤적과는 구분합니다. ‘PIT LAP’은 피트 기록이 있는 랩이며 정확한 피트 진입·출구 시각은 아닙니다. 지도 경로가 없으면 실제 관측에서 분리된 추정 경로만 표시합니다.</p>
</section><script id="gap-payload" type="application/octet-stream">'''+payload+'</script><script>'+script+'</script>'


def gap_sources(snapshot, directory):
    """Sources for the map/interval replay; call only when it is rendered."""
    from report_sources import link, map_credit, openf1, when
    key = snapshot['session'].get('session_key')
    path = directory / f'{key}-track.json.gz'
    value = json.loads(gzip.decompress(path.read_bytes())) if path.exists() else {}
    if value.get('session_key') != key:
        return []
    entries = [f"위치: OpenF1 {openf1('location', key)} · 수집 {when(value.get('fetched_at'))}"]
    gaps = directory / f'{key}-intervals.json'
    if gaps.exists():
        entries.append(f"간격: OpenF1 {openf1('intervals', key)} · 수집 {when(json.loads(gaps.read_text(encoding='utf-8')).get('fetched_at'))}")
    entries += map_credit(value.get('pit_reference'))
    entries.append(f"구성 참고: {link('https://f1cosmos.com/ko/dashboard/replay/11326', 'F1 COSMOS 리플레이')} · 사용자가 제공한 화면을 참고했으며 사이트 리플레이 데이터는 직접 검증하지 못했습니다. 이 세션의 데이터 출처가 아닙니다.")
    return entries
