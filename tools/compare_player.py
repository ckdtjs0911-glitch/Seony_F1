"""An offline, selectable two-driver telemetry replay for race reports."""
import base64
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect_player(snapshot, directory, fetch):
    from report_video import epoch, iso
    session = snapshot['session']
    if session.get('session_name') != 'Race':
        return False
    key = session['session_key']
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{key}-compare.json.gz'
    # Timing changes invalidate the cache; request timestamps do not.
    timing = {'session': session, 'laps': snapshot['data']['laps'], 'drivers': snapshot['data']['drivers']}
    signature = hashlib.sha256(json.dumps(timing, sort_keys=True).encode()).hexdigest()
    old = json.loads(gzip.decompress(target.read_bytes())) if target.exists() else {}
    if old.get('signature') == signature and all(x.get('rows') or x.get('no_laps') for x in old.get('drivers', [])):
        return False
    laps = [x for x in snapshot['data']['laps'] if x.get('date_start') and x.get('lap_duration')]
    if not laps:
        raise ValueError('No timed race laps for replay')
    start = min(epoch(x['date_start']) for x in laps)
    end = max(epoch(x['date_start']) + x['lap_duration'] for x in laps)
    value = {'session_key': key, 'signature': signature, 'start': start, 'end': end,
             'fetched_at': datetime.now(timezone.utc).isoformat(), 'source': 'https://openf1.org/docs/',
             'columns': ['UTC offset ms', 'speed km/h', 'throttle', 'brake on/off', 'gear', 'drs'], 'drivers': []}
    previous = {d['number']: d for d in old.get('drivers', [])} if old.get('signature') == signature else {}
    for driver in snapshot['data']['drivers']:
        number = driver['driver_number']
        own = [x for x in laps if x['driver_number'] == number]
        entry = {'number': number, 'name': driver.get('full_name', str(number)), 'color': '#' + (driver.get('team_colour') or 'b6c7dc'),
                 'laps': [[x['lap_number'], round(epoch(x['date_start']) - start, 3), x['lap_duration']] for x in own], 'rows': [], 'no_laps': not own}
        if previous.get(number, {}).get('rows'):
            value['drivers'].append(previous[number])
            continue
        if own:
            a = min(epoch(x['date_start']) for x in own)
            b = max(epoch(x['date_start']) + x['lap_duration'] for x in own)
            try:
                rows = fetch('car_data', {'session_key': key, 'driver_number': number, 'date>': iso(a - 1), 'date<': iso(b + 1)})
                if any(x.get('session_key') != key or x.get('driver_number') != number for x in rows):
                    raise ValueError('Replay source session/driver mismatch')
                entry['rows'] = sorted([[round((epoch(x['date']) - start) * 1000), x.get('speed'), x.get('throttle'), x.get('brake'), x.get('n_gear'), x.get('drs')] for x in rows], key=lambda x: x[0])
            except Exception as exc:
                entry['error'] = type(exc).__name__
        value['drivers'].append(entry)
        print(f'Replay {key} driver {number}: {len(entry["rows"])} samples', flush=True)
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    comparable = lambda v: {k: x for k, x in v.items() if k != 'fetched_at'}
    if old and comparable(old) == comparable(value):
        return False
    temporary = target.with_suffix('.tmp')
    temporary.write_bytes(gzip.compress(raw, mtime=0))
    temporary.replace(target)
    return True


def render_player(snapshot, directory):
    if snapshot['session'].get('session_name') != 'Race':
        return ''
    key = snapshot['session'].get('session_key')
    path = directory / f'{key}-compare.json.gz'
    if not path.exists():
        return ''
    value = json.loads(gzip.decompress(path.read_bytes()))
    if value.get('session_key') != key:
        return ''
    payload = base64.b64encode(path.read_bytes()).decode()
    script = (ROOT / 'tools' / 'compare_player.js').read_text(encoding='utf-8')
    return '''<section id="driver-replay"><h3>두 선수 선택 · 차량 데이터 비교</h3>
<p>선수 두 명과 랩을 고르면 같은 UTC 시각의 속도·가속·브레이크 사용을 자동 재생합니다. 랩 시작점을 서로 맞춘 비교가 아닙니다.</p>
<div style="display:flex;gap:16px;flex-wrap:wrap"><label>첫 번째 선수 <select id="replay-a" aria-label="첫 번째 선수"></select></label><label>두 번째 선수 <select id="replay-b" aria-label="두 번째 선수"></select></label><label>비교 랩 <select id="replay-lap" aria-label="비교 랩"></select></label><label>재생 속도 <select id="replay-rate"><option value="1">1배속</option><option value="3" selected>3배속</option><option value="8">8배속</option></select></label></div>
<p><button id="replay-play" type="button">일시정지</button> <input id="replay-seek" aria-label="재생 위치" type="range" min="0" max="1000" value="0" style="width:55%"> <span id="replay-clock"></span></p>
<p id="replay-status" role="status">차량 데이터를 준비하고 있습니다.</p>
<canvas id="replay-canvas" width="1280" height="720" style="width:100%;max-width:1280px;background:#0b1321" aria-label="선택한 두 선수의 속도 비교 재생"></canvas>
<p>1초 넘는 데이터 공백은 빈 구간으로 표시합니다. 브레이크는 압력이 아닌 사용 여부입니다. 타이어·연료 조건이 다를 수 있으며, 그래프 교차는 추월 횟수가 아닙니다.</p>
</section><script type="application/octet-stream" id="replay-payload">''' + payload + '</script><script>' + script + '</script>'
