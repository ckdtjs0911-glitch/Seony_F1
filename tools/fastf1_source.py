"""Load FastF1 as a supplementary data source, keeping OpenF1 snapshots intact."""
import argparse
import hashlib
import html
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CODES={'Practice 1':'FP1','Practice 2':'FP2','Practice 3':'FP3','Qualifying':'Q','Race':'R','Sprint':'S','Sprint Qualifying':'SQ'}
PIN='f237036fdd7d3f982faf539ad01d57b115d139fe'


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if c.isalnum())


def identity_check(snapshot, event, session_name, date):
    s=snapshot['session']
    if session_name!=s['session_name'] or normalized(event['Location'])!=normalized(s['location']):
        raise ValueError('FastF1 event/session identity mismatch')
    expected=datetime.fromisoformat(s['date_start'].replace('Z','+00:00'))
    actual=datetime.fromisoformat(str(date).replace('Z','+00:00'))
    if actual.tzinfo is None:actual=actual.replace(tzinfo=timezone.utc)
    if actual.year!=s['year'] or abs((actual-expected).total_seconds())>6*3600:
        raise ValueError('FastF1 year/session start mismatch')


def compare_laps(snapshot,rows):
    drivers={str(d['driver_number']):d for d in snapshot['data']['drivers']}
    lookup={(str(l['driver_number']),int(l['lap_number'])):l for l in snapshot['data']['laps'] if isinstance(l.get('lap_duration'),(int,float))}
    matched=[];identity=[]
    for row in rows:
        d=drivers.get(row['driver_number'])
        if not d or normalized(d.get('name_acronym'))!=normalized(row['driver']):
            if row['driver_number'] not in identity:identity.append(row['driver_number'])
            continue
        own=lookup.get((row['driver_number'],row['lap_number']))
        if own and row['lap_time'] is not None:
            matched.append({'driver_number':row['driver_number'],'lap_number':row['lap_number'],'openf1':own['lap_duration'],'fastf1':row['lap_time'],'difference':round(row['lap_time']-own['lap_duration'],6)})
    return {'matched_laps':len(matched),'differences_over_2ms':sum(abs(r['difference'])>.002 for r in matched),'unmatched_driver_numbers':identity,'rows':matched}


def open_session(snapshot):
    import fastf1

    s = snapshot["session"]
    cache=ROOT/'.cache'/'fastf1';cache.mkdir(parents=True,exist_ok=True);fastf1.Cache.configure(cache_dir=str(cache))
    schedule=fastf1.get_event_schedule(s['year'],include_testing=False,backend='fastf1')
    matching=schedule[schedule['Location'].map(normalized)==normalized(s['location'])]
    if len(matching)!=1:raise ValueError('No unique FastF1 schedule entry for requested year and location')
    event=matching.iloc[0]
    session=fastf1.get_session(s['year'],int(event['RoundNumber']),CODES[s['session_name']])
    identity_check(snapshot,event,session.name,session.date)
    return fastf1, event, session


def fallback_snapshot(session_info, now):
    """Adapt verified FastF1 data for the report renderer after an OpenF1 401."""
    import math
    import pandas as pd
    import requests
    from fastf1.ergast import Ergast

    fastf1, event, session = open_session({"session": session_info})
    url = "https://livetiming.formula1.com" + session.api_path + "SessionInfo.json"
    response = requests.get(url, timeout=20)
    name = session_info["session_name"]
    data = {key: [] for key in ("drivers", "laps", "session_result", "stints", "pit", "race_control")}

    def number(value):
        try:
            value = float(value)
            return value if math.isfinite(value) and value >= 0 else None
        except (ValueError, TypeError):
            return None

    def seconds(value):
        return value.total_seconds() if pd.notna(value) and hasattr(value, "total_seconds") else None

    if response.status_code == 200:
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        results = session.results
        laps = session.laps
        detail = True
    else:
        endpoint = {"Race": "get_race_results", "Qualifying": "get_qualifying_results", "Sprint": "get_sprint_results"}.get(name)
        if not endpoint:
            return None
        result = getattr(Ergast(), endpoint)(season=session_info["year"], round=int(event["RoundNumber"]))
        if not result.content:
            return None
        results = result.content[0].rename(columns={"number": "DriverNumber", "position": "Position",
            "givenName": "FirstName", "familyName": "LastName", "constructorName": "TeamName",
            "driverCode": "Abbreviation", "points": "Points", "laps": "Laps", "totalRaceTime": "Time"})
        if "DriverNumber" not in results:
            results = results.rename(columns={"driverNumber": "DriverNumber"})
        laps = None
        detail = False
    for _, row in results.iterrows():
        driver = number(row.get("DriverNumber"))
        if not driver:
            continue
        driver = int(driver)
        full_name = " ".join(str(row[field]) for field in ("FirstName", "LastName") if pd.notna(row.get(field)))
        data["drivers"].append({"driver_number": driver, "full_name": full_name or f"Driver {driver}",
            "team_name": str(row["TeamName"]) if pd.notna(row.get("TeamName")) else "팀 정보 없음"})
        if number(row.get("Position")):
            data["session_result"].append({"driver_number": driver, "position": int(row["Position"]),
                "number_of_laps": number(row.get("Laps")), "points": number(row.get("Points")),
                "duration": [seconds(row.get(q)) for q in ("Q1", "Q2", "Q3")] if name == "Qualifying" else None})
    stint_laps = {}
    if laps is not None:
        for _, row in laps.iterrows():
            driver, lap = number(row.get("DriverNumber")), number(row.get("LapNumber"))
            duration = seconds(row.get("LapTime"))
            if not driver or not lap or not duration or (pd.notna(row.get("Deleted")) and row["Deleted"]):
                continue
            driver, lap = int(driver), int(lap)
            data["laps"].append({"driver_number": driver, "lap_number": lap, "lap_duration": duration,
                "duration_sector_1": seconds(row.get("Sector1Time")),
                "duration_sector_2": seconds(row.get("Sector2Time")),
                "duration_sector_3": seconds(row.get("Sector3Time")),
                "is_pit_out_lap": bool(pd.notna(row.get("PitOutTime")))})
            stint = number(row.get("Stint"))
            if stint and pd.notna(row.get("Compound")):
                stint_laps.setdefault((driver, int(stint), str(row["Compound"])), []).append(lap)
    data["stints"] = [
        {"driver_number": driver, "stint_number": stint, "compound": compound,
         "lap_start": min(lap_numbers), "lap_end": max(lap_numbers)}
        for (driver, stint, compound), lap_numbers in stint_laps.items()
    ]
    if not (data["laps"] or data["session_result"]):
        return None
    return {"session": session_info, "data": data, "data_source": "fastf1",
        "status": "FastF1 임시 보고서 · OpenF1 인증 대기" if detail else "FastF1 공개 결과만 · OpenF1 인증 대기",
        "fetched_at": now.isoformat(), "fastf1_version": fastf1.__version__,
        "fastf1_timing_status": response.status_code, "fastf1_source_url": url if detail else "https://api.jolpi.ca/ergast/"}


def collect(snapshot,directory,force=False,telemetry=True,authenticated=False):
    import fastf1
    import pandas as pd
    directory.mkdir(parents=True,exist_ok=True)
    s=snapshot['session'];key=s['session_key'];target=directory/f'{key}-fastf1.json'
    fingerprint=hashlib.sha256(json.dumps({'session':s,'data':snapshot['data'],'pin':PIN},sort_keys=True).encode()).hexdigest()
    if target.exists() and not force:
        previous=json.loads(target.read_text(encoding='utf-8'))
        if previous.get('fingerprint')==fingerprint and (not authenticated or previous.get('telemetry_loaded',False)>=telemetry):return False
    fastf1, event, session = open_session(snapshot)
    # Probe public access first. Never trigger an interactive account prompt in a report job.
    import requests
    response=requests.get('https://livetiming.formula1.com'+session.api_path+'SessionInfo.json',timeout=20)
    private_access=response.status_code==200 or authenticated
    results=[]
    from fastf1.ergast import Ergast
    endpoint={'Race':'get_race_results','Qualifying':'get_qualifying_results','Sprint':'get_sprint_results'}.get(s['session_name'])
    if endpoint:
        result=getattr(Ergast(),endpoint)(season=s['year'],round=int(event['RoundNumber']))
        if len(result.content):results=json.loads(result.content[0].to_json(orient='records',date_format='iso'))
    if private_access:
        session.load(laps=True,telemetry=telemetry,weather=False,messages=True)
        if session.laps is None or session.laps.empty:raise ValueError('FastF1 timing data unavailable')
    def scalar(v):
        if v is None or pd.isna(v):return None
        if hasattr(v,'total_seconds'):return v.total_seconds()
        if hasattr(v,'item'):return v.item()
        return v
    laps=[]
    for _,r in (session.laps.iterrows() if private_access else []):
        if pd.isna(r.get('LapNumber')) or pd.isna(r.get('DriverNumber')):continue
        laps.append({'driver_number':str(r['DriverNumber']),'driver':str(r.get('Driver','')),'lap_number':int(r['LapNumber']),'lap_time':scalar(r.get('LapTime')),
                     'sector_1':scalar(r.get('Sector1Time')),'sector_2':scalar(r.get('Sector2Time')),'sector_3':scalar(r.get('Sector3Time')),
                     'compound':scalar(r.get('Compound')),'stint':scalar(r.get('Stint')),'deleted':scalar(r.get('Deleted')),'accurate':scalar(r.get('IsAccurate'))})
    car={}
    if telemetry and private_access:
        for number,df in session.car_data.items():
            car[str(number)]={'sample_count':len(df),'columns':list(df.columns),
                              'first_sample':json.loads(df.head(1).to_json(orient='records',date_format='iso')),
                              'last_sample':json.loads(df.tail(1).to_json(orient='records',date_format='iso'))}
        if not car:raise ValueError('FastF1 telemetry requested but unavailable')
    value={'status':'connected' if private_access else 'results_only' if results else 'schedule_only','session_key':key,'fingerprint':fingerprint,'fetched_at':datetime.now(timezone.utc).isoformat(),
           'timing_http_status':response.status_code,'timing_auth_required':response.status_code==401,'public_result_source':'FastF1 Ergast/Jolpica backend',
           'library_version':fastf1.__version__,'library_commit':PIN,'source':'https://docs.fastf1.dev/','api_path':session.api_path,
           'identity':{'year':s['year'],'location':str(event['Location']),'event':str(event['EventName']),'round':int(event['RoundNumber']),'session':session.name,'date':str(session.date)},
           'laps':laps,'results':results,'telemetry_loaded':bool(car),'car_data':car,
           'comparison':compare_laps(snapshot,laps)}
    old=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    stable=lambda v:{k:r for k,r in v.items() if k!='fetched_at'}
    if stable(old)==stable(value):return False
    tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(target)
    status_path=directory/f'{key}-fastf1-status.json'
    if status_path.exists():status_path.unlink()
    return True


def render_source(snapshot):
    s=snapshot['session'];key=s.get('session_key');directory=ROOT/'reports'/f'weekend-{s.get("meeting_key")}'/'media'
    path=directory/f'{key}-fastf1.json';failure=directory/f'{key}-fastf1-status.json'
    if not path.exists():
        if failure.exists():return '<section class="fastf1-source"><h3>FastF1 보조 데이터</h3><p>조회 기능은 연결됐지만 이 세션의 데이터 수집은 완료하지 못했습니다. 기존 OpenF1 기록을 유지합니다.</p></section>'
        return ''
    v=json.loads(path.read_text(encoding='utf-8'))
    if v.get('session_key')!=key:return ''
    c=v['comparison'];count=sum(x['sample_count'] for x in v['car_data'].values())
    if v['status']!='connected':
        public=f'선수 결과 {len(v["results"])}명 조회 완료' if v['results'] else '해당 세션의 일정 조회 완료'
        limitation='상세 랩·차량 데이터 서버가 HTTP 401 응답으로 F1 TV 인증을 요구해 조회를 보류했습니다(인증 대기).' if v.get('timing_auth_required') else '상세 랩·차량 데이터는 수집하지 못했습니다.'
        return f'<section class="fastf1-source"><h3>FastF1 보조 데이터 연결</h3><p>{public} · {html.escape(v["identity"]["event"])} · {html.escape(v["identity"]["session"])}</p><p>{limitation} 랩·텔레메트리 대조는 완료로 처리하지 않았으며 기존 OpenF1 기록을 유지합니다.</p></section>'
    return f'<section class="fastf1-source"><h3>FastF1 보조 데이터 연결</h3><p>실제 수집 완료 · {len(v["laps"]):,}개 랩 · 차량 샘플 {count:,}개 확인</p><p>동일 선수·동일 랩 {c["matched_laps"]:,}개 대조 · 0.002초 초과 차이 {c["differences_over_2ms"]:,}개 · 선수 번호·약어 불일치 {len(c["unmatched_driver_numbers"])}명. 기존 OpenF1 기록을 덮어쓰지 않았습니다.</p><p>같은 타이밍 원본을 사용할 수 있어 독립적인 공식 검증을 뜻하지 않습니다. 브레이크는 사용 여부이며 제동 압력이 아닙니다.</p></section>'



def fastf1_sources(snapshot):
    """Source details for the FastF1 section; call only when it is rendered."""
    from report_sources import link,when
    s=snapshot['session'];key=s.get('session_key');directory=ROOT/'reports'/f'weekend-{s.get("meeting_key")}'/'media'
    path=directory/f'{key}-fastf1.json';failure=directory/f'{key}-fastf1-status.json';docs=link('https://docs.fastf1.dev/','FastF1 공식 문서')
    if not path.exists():
        if not failure.exists():return []
        checked=json.loads(failure.read_text(encoding='utf-8')).get('checked_at')
        return [f'FastF1 조회 시도 {when(checked)} · 데이터 미수집 · {docs}']
    v=json.loads(path.read_text(encoding='utf-8'))
    if v.get('session_key')!=key:return []
    library=f'FastF1 {html.escape(str(v.get("library_version") or "버전 미기록"))} · 소스 커밋 {html.escape(str(v.get("library_commit") or "")[:12])} · {docs}'
    if v.get('status')=='connected':
        return [f'F1 타이밍·텔레메트리(FastF1 경유) · 수집 {when(v.get("fetched_at"))}',library]
    public='공개 결과: FastF1 Ergast/Jolpica 백엔드' if v.get('results') else '공개 일정: FastF1 일정 조회'
    entries=[f'{public} · 조회 {when(v.get("fetched_at"))}']
    if v.get('timing_http_status') is not None:
        entries.append(f'상세 타이밍 서버 응답 HTTP {html.escape(str(v["timing_http_status"]))}'+(' · 인증 대기, 상세 데이터 미수집' if v.get('timing_auth_required') else ' · 상세 데이터 미수집'))
    return entries+[library]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--snapshot',type=Path);parser.add_argument('--root',type=Path,default=ROOT/'reports');parser.add_argument('--force',action='store_true');parser.add_argument('--timing-only',action='store_true');parser.add_argument('--authenticated',action='store_true',help='Use operator-configured F1 account credentials for detailed timing; never put credentials in command arguments');parser.add_argument('--sessions',default='',help='Comma-separated session keys selected by the automatic gate');args=parser.parse_args()
    import weekend_report as w
    paths=[args.snapshot] if args.snapshot else sorted(args.root.glob('weekend-*/data/*.json'))
    selected={x.strip() for x in args.sessions.split(',') if x.strip()}
    if selected:paths=[p for p in paths if p.stem in selected]
    for path in paths:
        snapshot=json.loads(path.read_text(encoding='utf-8'));s=snapshot.get('session',{})
        if s.get('session_name') not in CODES or not snapshot.get('data') or snapshot.get('data_source') == 'fastf1':continue
        if not args.snapshot and datetime.now(timezone.utc).timestamp()-w.stamp(snapshot['fetched_at']).timestamp()>1800:continue
        directory=path.parent.parent/'media'
        try:
            changed=collect(snapshot,directory,args.force,not args.timing_only,args.authenticated)
            if changed:
                w.render(w.load_offline(path.parent.parent),path.parent.parent/'weekend-report.html')
                if s['session_name'] in ('Race','Qualifying'):w.render([snapshot],path.parent.parent/('race-report.html' if s['session_name']=='Race' else 'qualifying-report.html'))
            print(f'FastF1 {s["session_key"]}: {"updated" if changed else "unchanged"}')
        except Exception as exc:
            directory.mkdir(parents=True,exist_ok=True)
            # Record a failed attempt separately; preserve every successful source and report.
            status={'status':'unavailable','session_key':s['session_key'],'checked_at':datetime.now(timezone.utc).isoformat(),'error_type':type(exc).__name__}
            (directory/f'{s["session_key"]}-fastf1-status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
            print(f'FastF1 {s["session_key"]}: unavailable ({type(exc).__name__}: {exc})')
            if args.snapshot:return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
