"""Describe OpenF1 position exchanges without claiming verified on-track passes."""
from collections import Counter, defaultdict
from datetime import datetime
from html import escape


def exchanges(snapshot):
    events, seen = [], set()
    key = snapshot['session'].get('session_key')
    for record in snapshot.get('data', {}).get('overtakes', []):
        a, b = record.get('overtaking_driver_number'), record.get('overtaken_driver_number')
        if record.get('session_key') != key or not isinstance(a, int) or not isinstance(b, int) or a == b:
            continue
        try:
            when = datetime.fromisoformat(record['date'].replace('Z', '+00:00'))
            if when.tzinfo is None:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        identity = (when, a, b, record.get('position'))
        if identity not in seen:
            seen.add(identity)
            events.append(dict(record, when=when))
    events.sort(key=lambda e: e['when'])
    # Opposite exchanges at an identical timestamp have no reliable ordering.
    directions = defaultdict(set)
    for e in events:
        pair = tuple(sorted((e['overtaking_driver_number'], e['overtaken_driver_number'])))
        directions[(pair, e['when'])].add(e['overtaking_driver_number'])
    last = {}
    for e in events:
        a, b = e['overtaking_driver_number'], e['overtaken_driver_number']
        pair = tuple(sorted((a, b)) )
        ambiguous = len(directions[(pair, e['when'])]) > 1
        e['repass'] = not ambiguous and last.get(pair) == b
        e['ambiguous'] = ambiguous
        last[pair] = None if ambiguous else a
    return events


def render_overtakes(snapshot):
    if snapshot['session']['session_name'] != 'Race':
        return ''
    header = '<section id="race-overtakes"><h2>오버테이크 · 선수별 순위 교환 기록</h2>'
    notice = ('<p class="notice">실제 트랙 추월 총횟수는 이 데이터만으로 확정할 수 없습니다. '
              'OpenF1 overtakes에는 트랙 추월뿐 아니라 피트스톱·경기 후 페널티에 따른 순위 교환도 포함되며 누락될 수 있습니다. '
              '아래 횟수는 중복을 제거한 API 순위 교환 기록입니다. 순위 변화만으로 추월 원인을 추정하지 않습니다.</p>')
    if 'overtakes' not in snapshot.get('data', {}):
        return header + notice + '<p>순위 교환 데이터 미수집·미제공: 0회라는 뜻이 아닙니다.</p></section>'
    events = exchanges(snapshot)
    outgoing, incoming, details = Counter(), Counter(), defaultdict(list)
    drivers = {d['driver_number']: d for d in snapshot['data'].get('drivers', [])}
    def name(number):
        return f'#{number} ' + drivers.get(number, {}).get('full_name', '선수명 미제공')
    for e in events:
        a, b = e['overtaking_driver_number'], e['overtaken_driver_number']
        outgoing[a] += 1
        incoming[b] += 1
        details[a].append((e, b, True))
        details[b].append((e, a, False))
    body = f'<p><b>레이스 전체 API 순위 교환: {len(events)}건</b> · 사건 1건을 한 번만 집계합니다. 선수별 앞선 횟수와 뒤처진 횟수를 모두 더하면 이중 집계됩니다.</p>'
    body += '<p>재추월·재추월당함은 같은 두 선수의 직전 API 교환 방향이 뒤집힌 경우입니다. 실제 트랙에서의 재추월을 확인한 뜻은 아닙니다. 같은 시각에 양방향 교환이 있으면 순서를 미확인으로 표시합니다.</p>'
    body += '<div class="scroll result-table"><table><thead><tr><th>선수 / 팀</th><th>앞선 횟수</th><th>뒤처진 횟수</th><th>재추월</th><th>재추월당함</th></tr></thead><tbody>'
    numbers = sorted(set(drivers) | set(details), key=lambda n: (-outgoing[n], n))
    for n in numbers:
        repasses = sum(e['repass'] for e, _, out in details[n] if out)
        repassed = sum(e['repass'] for e, _, out in details[n] if not out)
        team = drivers.get(n, {}).get('team_name', '팀 미제공')
        body += f'<tr data-search="{escape((name(n)+" "+team).lower(), quote=True)}"><td>{escape(name(n))}<small>{escape(team)}</small></td><td>{outgoing[n]}</td><td>{incoming[n]}</td><td>{repasses}</td><td>{repassed}</td></tr>'
    body += '</tbody></table></div>'
    for n in numbers:
        body += f'<details><summary>{escape(name(n))} · 상대 및 시간별 상세 ({len(details[n])}건)</summary>'
        if not details[n]:
            body += '<p>API에 기록된 교환 없음 · 실제 추월이 없었다는 뜻은 아닙니다.</p></details>'
            continue
        body += '<div class="scroll"><table><thead><tr><th>시각 UTC</th><th>상대 선수</th><th>기록 구분</th><th>앞선 선수의 교환 후 순위</th></tr></thead><tbody>'
        for e, other, out in details[n]:
            label = ('재추월' if out else '재추월당함') if e['repass'] else ('앞섬' if out else '뒤처짐')
            if e['ambiguous']:
                label += ' · 동일 시각 순서 미확인'
            position = e.get('position')
            body += f'<tr><td>{e["when"].strftime("%m-%d %H:%M:%S.%f")[:-3]}</td><td>{escape(name(other))}</td><td>{label} (API)</td><td>{escape(str(position if position is not None else "—"))}</td></tr>'
        body += '</tbody></table></div></details>'
    return header + notice + body + '</section>'


def overtake_sources(snapshot):
    """Sources for the position-exchange appendix; call only when it is rendered."""
    from report_sources import link, openf1
    key = snapshot["session"].get("session_key", "")
    return [f"OpenF1 {openf1('overtakes', key)} (보고서 스냅샷) · {link('https://openf1.org/docs/#overtakes', '집계 정의')}"]
