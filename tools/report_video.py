"""Collect real OpenF1 samples, align UTC timestamps and render self-contained report videos."""
import argparse
import base64
import bisect
import hashlib
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

VERSION = 7
ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "https://www.instagram.com/reel/DgCU86yhjUz/"


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def past_sample(samples, now, max_gap=1.0):
    """Use past samples only; never interpolate discrete signals or hide long gaps."""
    times = [epoch(x["date"]) for x in samples]
    i = bisect.bisect_right(times, now) - 1
    return samples[i] if i >= 0 and now - times[i] <= max_gap else None


def select_scene(snapshot):
    data = snapshot["data"]
    results = sorted((x for x in data["session_result"] if isinstance(x.get("position"), (int, float))), key=lambda x: x["position"])
    drivers = [x["driver_number"] for x in results[:2]]
    if len(drivers) != 2:
        raise ValueError("Two classified drivers required")
    laps = [{x["lap_number"]: x for x in data["laps"] if x["driver_number"] == d and x.get("date_start") and x.get("lap_duration") and not x.get("is_pit_out_lap")} for d in drivers]
    common = sorted(set(laps[0]) & set(laps[1]), reverse=True)
    # Penultimate shared lap avoids incomplete finish-line telemetry.
    for number in common[1:] + common[:1]:
        pair = [x[number] for x in laps]
        start = max(epoch(x["date_start"]) for x in pair)
        end = min(epoch(x["date_start"]) + x["lap_duration"] for x in pair)
        if end - start > 20:
            return drivers, number, start, end
    raise ValueError("No overlapping clean lap available")


def collect(snapshot, directory, fetch):
    """Cache scoped original responses separately from the existing report snapshot."""
    drivers, lap, start, end = select_scene(snapshot)
    session = snapshot["session"]
    params = {"session_key": session["session_key"]}
    car = {}
    for driver in drivers:
        car[str(driver)] = fetch("car_data", dict(params, driver_number=driver, **{"date>": iso(start - 1), "date<": iso(end + 1)}))
        rows = car[str(driver)]
        if len(rows) < 20 or any(x.get("session_key") != session["session_key"] or x.get("driver_number") != driver for x in rows):
            raise ValueError("Telemetry missing or session/driver mismatch")
        car[str(driver)] = sorted(rows, key=lambda x: epoch(x["date"]))
        valid = [epoch(x["date"]) for x in rows]
        if min(valid) > start + 1 or max(valid) < end - 1:
            raise ValueError("Telemetry does not cover requested scene")
    positions = fetch("position", params)
    if not positions or any(x.get("session_key") != session["session_key"] for x in positions):
        raise ValueError("Position records unavailable or wrong session")
    positions.sort(key=lambda x: epoch(x["date"]))
    value = {"version": VERSION, "session": session, "fetched_at": datetime.now(timezone.utc).isoformat(), "drivers": drivers, "lap": lap, "start": start, "end": end, "car_data": car, "position": positions,
             "source": "https://openf1.org/docs/", "reference": {"url": REFERENCE, "verified": "Public caption only; reel frames were inaccessible", "claim": "46 of 50 laps led; 30+ mid-lap lead changes (not independently confirmed)"}}
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{session["session_key"]}-video-data.json'
    old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    stable = lambda v: {k: x for k, x in v.items() if k != "fetched_at"}
    if old is None or stable(old) != stable(value):
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def font_path():
    for path in ["C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(path).exists():
            return path
    raise RuntimeError("A TrueType font is required")


def render_videos(snapshot, source, directory):
    # Heavy dependencies are only loaded for actual video generation.
    import numpy as np
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont

    raw = json.loads(source.read_text(encoding="utf-8"))
    key = snapshot["session"]["session_key"]
    if raw["session"]["session_key"] != key:
        raise ValueError("Video source session mismatch")
    signature = hashlib.sha256(source.read_bytes() + str(VERSION).encode()).hexdigest()
    manifest_path = directory / f"{key}-videos.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("signature") == signature and all((directory / x["file"]).exists() for x in old["videos"]):
            return False
    directory.mkdir(parents=True, exist_ok=True)
    fonts = {s: ImageFont.truetype(font_path(), s) for s in [15, 18, 22, 26, 34]}
    names = {x["driver_number"]: x for x in snapshot["data"]["drivers"]}
    colors = {d: "#" + (x.get("team_colour") or "b6c7dc") for d, x in names.items()}
    W, H, fps = 1280, 720, 30
    videos = []

    def frame(title, subtitle):
        im = Image.new("RGB", (W, H), "#0b1321")
        draw = ImageDraw.Draw(im)
        draw.text((40, 22), "SEONY F1 / LAS VEGAS" if snapshot["session"].get("location") == "Las Vegas" else "SEONY F1 / " + snapshot["session"].get("location", "F1"), font=fonts[18], fill="#6deac9")
        draw.text((40, 54), title, font=fonts[34], fill="white")
        draw.text((40, 103), subtitle, font=fonts[18], fill="#bacbe0")
        return im, draw

    def encode(filename, frames):
        target = directory / filename
        temporary = target.with_name(target.stem + ".tmp.mp4")
        writer = imageio_ffmpeg.write_frames(str(temporary), (W, H), fps=fps, codec="libx264", pix_fmt_out="yuv420p", output_params=["-crf", "23", "-movflags", "+faststart"], macro_block_size=1)
        writer.send(None)
        try:
            for im in frames:
                writer.send(np.asarray(im).tobytes())
        finally:
            writer.close()
        temporary.replace(target)

    pair = raw["drivers"]
    start, end = raw["start"], raw["end"]
    duration = 32
    channels = [("speed", "속도 (km/h)", 370), ("throttle", "가속 페달 (%)", 100), ("brake", "브레이크 사용 · 0=해제 / 100=사용", 100)]
    traces = {}
    for driver in pair:
        rows = raw["car_data"][str(driver)]
        traces[driver] = rows

    def telemetry_frames():
        for i in range(duration * fps):
            now = start + (end - start) * i / (duration * fps - 1)
            clock = datetime.fromtimestamp(now, timezone.utc).strftime("%H:%M:%S.%f")[:-5]
            im, draw = frame(f'결승 1·2위 비교 · 랩 {raw["lap"]}', f'같은 UTC 시각 비교  {clock} UTC  |  약 {(end-start)/duration:.1f}배속 · 화면 사이 값 보간 없음')
            for j, driver in enumerate(pair):
                x = 40 + j * 620
                sample = past_sample(traces[driver], now)
                draw.rounded_rectangle((x, 145, x + 590, 245), radius=14, fill="#152339")
                name = names[driver].get("full_name", str(driver))
                draw.text((x + 16, 155), name, font=fonts[26], fill=colors[driver])
                if sample:
                    drs = sample.get("drs")
                    drs_text = "   DRS 작동" if drs in (10, 12, 14) else ("   DRS 꺼짐" if drs in (0, 1, 8) else "")
                    text = f'{sample.get("speed", "—")} km/h   기어 {sample.get("n_gear", "—")}{drs_text}'
                else:
                    text = "차량 데이터 공백 (1초 초과)"
                draw.text((x + 16, 203), text, font=fonts[22], fill="white")
            for k, (channel, label, maximum) in enumerate(channels):
                top, left, right, height = 285 + k * 110, 230, 1230, 74
                draw.text((40, top + 15), label if channel != "brake" else "브레이크 사용", font=fonts[18], fill="#bacbe0")
                draw.rectangle((left, top, right, top + height), outline="#35465e")
                for driver in pair:
                    previous = None
                    for row in traces[driver]:
                        t, value = epoch(row["date"]), row.get(channel)
                        if not start <= t <= end or value is None:
                            previous = None
                            continue
                        point = (left + (t - start) / (end - start) * (right-left), top + height - min(maximum, max(0, value)) / maximum * height)
                        if previous and t - previous[0] <= 1:
                            # Step chart: samples retain discrete brake/gear states.
                            draw.line([previous[1], (point[0], previous[1][1]), point], fill=colors[driver], width=2)
                        previous = (t, point)
                    sample = past_sample(traces[driver], now)
                    if sample and sample.get(channel) is not None:
                        y = top + height - min(maximum, max(0, sample[channel])) / maximum * height
                        x = left + (now-start)/(end-start)*(right-left)
                        draw.ellipse((x-5, y-5, x+5, y+5), fill=colors[driver], outline="white")
                x = left + (now-start)/(end-start)*(right-left)
                draw.line((x, top, x, top+height), fill="#f3f6fc", width=1)
            draw.text((40, 624), "가로축: 공통 시각 · 색상: 팀 · 브레이크는 압력(%)이 아닌 사용 여부", font=fonts[18], fill="white")
            draw.text((40, 658), "OpenF1 car_data 약 3.7Hz | 연료·타이어 조건이 달라 성능 우열이나 추월을 단정할 수 없습니다.", font=fonts[18], fill="#bacbe0")
            yield im
    telemetry_file = f"{key}-telemetry.mp4"
    # Fixed first/second-place video is retired; the selectable player replaces it.

    # Sample the position feed at each leader lap completion, not each car's separate crossing.
    winner = pair[0]
    completions = sorted((epoch(x["date_start"]) + x["lap_duration"], x["lap_number"]) for x in snapshot["data"]["laps"] if x["driver_number"] == winner and x.get("date_start") and x.get("lap_duration"))
    positions = {}
    for row in raw["position"]:
        positions.setdefault(row["driver_number"], []).append(row)
    chart = {d: [] for d in names}
    for t, lap in completions:
        for driver in names:
            # Position feed records changes, so hold until next update; this is not car telemetry.
            row = past_sample(positions.get(driver, []), t, max_gap=math.inf)
            if row and isinstance(row.get("position"), (int, float)):
                chart[driver].append((lap, row["position"]))
    maximum_lap = max((x[1] for x in completions), default=0)
    gap_path = directory / f'{key}-intervals.json'
    gaps = {}
    if gap_path.exists():
        gap_source = json.loads(gap_path.read_text(encoding='utf-8'))
        if gap_source.get('session_key') == key:
            for row in gap_source['rows']:
                gaps.setdefault(row['driver_number'], []).append(row)
    for rows in gaps.values():
        rows.sort(key=lambda r: epoch(r['date']))
    gap_times = {d:[epoch(r['date']) for r in rows] for d,rows in gaps.items()}
    if not maximum_lap or not any(chart.values()):
        raise ValueError("No valid lap-position chart samples")

    def lap_frames():
        label_positions = {}
        for i in range(30 * fps):
            progress = maximum_lap * i / (30 * fps - 1)
            # The video clock follows the same lap-time axis as the animation.
            lap_times = [(0, min(epoch(x['date_start']) for x in snapshot['data']['laps'] if x.get('date_start')))] + [(lap,t) for t,lap in completions]
            before = max((p for p in lap_times if p[0] <= progress),default=lap_times[0])
            after = next((p for p in lap_times if p[0] > progress),before)
            clock = before[1] if after[0]==before[0] else before[1]+(after[1]-before[1])*(progress-before[0])/(after[0]-before[0])
            im, draw = frame("레이스 순위 흐름 · 랩 차트", f'우승자 각 랩 완료 시각의 순위 기록 | 랩 {min(maximum_lap, int(progress)):02d}/{maximum_lap} | 선 사이 이동은 표시용 애니메이션')
            left, right, top, bottom = 70, 950, 170, 610
            n = max(22, len(names))
            xy = lambda lap, pos: (left + lap / maximum_lap * (right-left), top + (pos-1)/(n-1)*(bottom-top))
            for pos in range(1, n+1):
                y = xy(0, pos)[1]
                draw.line((left, y, right, y), fill="#25354a")
                draw.text((25, y-8), str(pos), font=fonts[15], fill="#bacbe0")
            for lap in range(0, maximum_lap+1, 5):
                x = xy(lap, 1)[0]
                draw.text((x-8, bottom+10), str(lap), font=fonts[15], fill="#bacbe0")
            labels = []
            for driver, points in chart.items():
                shown = [p for p in points if p[0] <= progress]
                if not shown:
                    continue
                pixels = [xy(*p) for p in shown]
                following = next((p for p in points if p[0] > progress), None)
                if following:
                    previous = shown[-1]
                    fraction = (progress - previous[0]) / (following[0] - previous[0])
                    eased = fraction * fraction * (3 - 2 * fraction)
                    pixels.append(xy(progress, previous[1] + (following[1] - previous[1]) * eased))
                if len(pixels) > 1:
                    draw.line(pixels, fill=colors[driver], width=3 if driver in pair else 1)
                x, y = pixels[-1]
                draw.ellipse((x-4,y-4,x+4,y+4), fill=colors[driver])
                labels.append([y, driver, x])
            # Labels follow the moving endpoints; pack close labels to remain readable.
            labels.sort(key=lambda item: (item[0], item[1]))
            previous_y = top - 20
            adjusted = []
            for y, driver, x in labels:
                label_y = max(y, previous_y + 19)
                adjusted.append([label_y, y, driver, x])
                previous_y = label_y
            ceiling = bottom + 5
            for label in reversed(adjusted):
                label[0] = min(label[0], ceiling)
                ceiling = label[0] - 19
            for label_y, y, driver, x in adjusted:
                label_y = label_positions.get(driver, label_y) * .7 + label_y * .3
                label_positions[driver] = label_y
                label_x = 970
                draw.line((x+4, y, label_x, label_y), fill=colors[driver], width=1)
                name = names[driver].get('last_name', str(driver)).title()
                from race_gaps import gap_text
                index=bisect.bisect_right(gap_times.get(driver,[]),clock)-1
                row=gaps[driver][index] if index>=0 and clock-gap_times[driver][index]<=10 else None
                pos=past_sample(positions.get(driver,[]),clock,max_gap=math.inf)
                interval=gap_text(row, bool(pos and pos.get('position')==1))
                draw.text((label_x+5, label_y-10), f'{names[driver].get("name_acronym", driver)} · {name[:12]}  {interval}', font=fonts[15], fill=colors[driver])
            draw.text((40, 658), "이름 옆: 앞차와 간격 · s=초 · —=기록 없음 · 순위 변화·선 교차는 실제 추월 횟수가 아닙니다.", font=fonts[18], fill="#bacbe0")
            yield im
    lap_file = f"{key}-lap-chart.mp4"
    encode(lap_file, lap_frames())
    videos.append({"file": lap_file, "title": "전체 드라이버 · 레이스 순위 흐름", "description": "이름 옆에 같은 시각의 앞차와 간격을 s(초)로 표시합니다. 랩 차이는 +1 LAP처럼 보존하고, 최근 10초 이내 기록이 없으면 —로 표시합니다. 순위 선은 우승자 각 랩 완료 시각을 기준으로 하며 중간 이동은 표시용입니다. 실제 추월 횟수가 아닙니다."})
    manifest = {"version": VERSION, "session_key": key, "signature": signature, "source_file": source.name, "source": raw["source"], "reference": raw["reference"], "fetched_at": raw["fetched_at"], "videos": videos}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def render_section(snapshot, media_root=None):
    if snapshot['session'].get('session_name') != 'Race':
        return ''
    key = snapshot["session"].get("session_key")
    meeting = snapshot["session"].get("meeting_key")
    directory = media_root or ROOT / "reports" / f"weekend-{meeting}" / "media"
    path = directory / f"{key}-videos.json"
    if not path.exists():
        return ""
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("session_key") != key:
        return ""
    cards = []
    from compare_player import render_player
    player = render_player(snapshot, directory)
    from race_gaps import render_gaps
    gap_player = render_gaps(snapshot, directory)
    for video in value["videos"]:
        if video['file'].endswith('-telemetry.mp4'):
            continue
        asset = directory / Path(video["file"]).name
        if not asset.exists():
            continue
        uri = "data:video/mp4;base64," + base64.b64encode(asset.read_bytes()).decode()
        rates = ''.join(f'<option value="{r}"{" selected" if r == "1" else ""}>{r}배속</option>' for r in ['0.25','0.5','0.75','1','1.25','1.5','1.75','2'])
        cards.append(f'<h3>{html.escape(video["title"])}</h3><p>{html.escape(video["description"])}</p><p><label>영상 재생 속도 <select id="rank-video-rate" aria-label="순위 흐름 영상 재생 속도">{rates}</select></label></p><video id="rank-flow-video" controls autoplay muted loop playsinline preload="metadata" style="width:100%;max-width:1280px;background:#0b1321" src="{uri}"></video><script>(()=>{{const rate=document.getElementById("rank-video-rate"),video=document.getElementById("rank-flow-video");rate.addEventListener("change",()=>{{video.playbackRate=Number(rate.value);}});}})();</script><p><a download="{html.escape(asset.name)}" href="{uri}">MP4 영상 다운로드</a></p>')
    if not cards:
        return ""
    return '<section id="data-videos"><h2>영상으로 보는 레이스</h2><p>실제 수집한 OpenF1 데이터로 만든 그래픽 영상입니다. 중계 장면이나 추정 제동 압력은 포함하지 않습니다.</p>' + gap_player + "".join(cards) + player + '</section>'


def video_sources(snapshot, media_root=None):
    """Sources for the rank-flow MP4; call only when the video is rendered."""
    from report_sources import link, openf1, when
    key = snapshot["session"].get("session_key")
    directory = media_root or ROOT / "reports" / f"weekend-{snapshot['session'].get('meeting_key')}" / "media"
    path = directory / f"{key}-videos.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if value.get("session_key") != key:
        return []
    entries = [f"OpenF1 {openf1('position', key)} · {openf1('laps', key)} · 수집 {when(value.get('fetched_at'))}"]
    gaps = directory / f"{key}-intervals.json"
    if gaps.exists():
        entries.append(f"앞차와 간격: OpenF1 {openf1('intervals', key)} · 수집 {when(json.loads(gaps.read_text(encoding='utf-8')).get('fetched_at'))}")
    entries.append(f"구성 참고: {link(REFERENCE, '라스베가스 랩 차트 릴스')} · 공개 설명만 확인했고 영상 화면은 확인하지 못했습니다. 데이터 검증 자료가 아닙니다.")
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT / "reports")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--sessions", default="", help="Comma-separated session keys selected by the automatic gate")
    args = parser.parse_args()
    import weekend_report
    paths = [args.snapshot] if args.snapshot else sorted(args.root.glob("weekend-*/data/*.json"))
    selected = {x.strip() for x in args.sessions.split(",") if x.strip()}
    if selected:
        paths = [p for p in paths if p.stem in selected]
    for path in paths:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot.get("data_source") == "fastf1":
            continue
        if snapshot.get('session',{}).get('session_name')=='Qualifying':
            if not args.snapshot and datetime.now(timezone.utc).timestamp()-epoch(snapshot['fetched_at'])>1800:
                continue
            try:
                from qualifying_replay import collect_qualifying
                changed=args.offline or collect_qualifying(snapshot,path.parent.parent/'media',weekend_report.fetch)
                if changed:
                    weekend_report.render([snapshot],path.parent.parent/'qualifying-report.html')
                    weekend_report.render(weekend_report.load_offline(path.parent.parent),path.parent.parent/'weekend-report.html')
            except Exception as exc:
                if args.snapshot:raise
                print(f'Qualifying replay unavailable: {type(exc).__name__}: {exc}')
            continue
        if snapshot.get("session", {}).get("session_name") != "Race" or not snapshot.get("data", {}).get("session_result"):
            continue
        # Automatic runs only process snapshots freshly collected in this run.
        if not args.snapshot and datetime.now(timezone.utc).timestamp() - epoch(snapshot["fetched_at"]) > 1800:
            continue
        directory = path.parent.parent / "media"
        source = directory / f'{snapshot["session"]["session_key"]}-video-data.json'
        try:
            track_changed = False
            if not args.offline:
                source = collect(snapshot, directory, weekend_report.fetch)
                from race_gaps import collect_gaps
                track_changed = collect_gaps(snapshot, directory, weekend_report.fetch)
            changed = render_videos(snapshot, source, directory) or track_changed
            from compare_player import collect_player
            if not args.offline:
                changed = collect_player(snapshot, directory, weekend_report.fetch) or changed
            if changed:
                weekend_report.render([snapshot], path.parent.parent / "race-report.html")
                weekend_report.render(weekend_report.load_offline(path.parent.parent), path.parent.parent / "weekend-report.html")
            print(f'Video session {snapshot["session"]["session_key"]}: {"updated" if changed else "unchanged"}')
        except Exception as exc:
            if args.snapshot:
                raise
            print(f'Video unavailable for {snapshot["session"]["session_key"]}: {type(exc).__name__}: {exc}')


if __name__ == "__main__":
    main()
