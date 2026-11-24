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

VERSION = 1
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
    W, H, fps = 1280, 720, 20
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
                    drs_text = "작동" if drs in (10, 12, 14) else ("꺼짐" if drs in (0, 1, 8) else "미제공")
                    text = f'{sample.get("speed", "—")} km/h   기어 {sample.get("n_gear", "—")}   DRS {drs_text}'
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
    encode(telemetry_file, telemetry_frames())
    videos.append({"file": telemetry_file, "title": f'결승 1·2위 · 랩 {raw["lap"]} 차량 데이터 비교', "description": "같은 UTC 시각에 맞춘 속도·가속 페달·브레이크 사용·기어 비교. DRS가 없으면 미제공으로 표시합니다. 약 3배속이며 실제 중계 영상은 포함하지 않습니다."})

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
    if not maximum_lap or not any(chart.values()):
        raise ValueError("No valid lap-position chart samples")

    def lap_frames():
        for i in range(30 * fps):
            progress = maximum_lap * i / (30 * fps - 1)
            im, draw = frame("레이스 순위 흐름 · 랩 차트", f'우승자 각 랩 완료 시각의 순위 기록 | 랩 {min(maximum_lap, int(progress)):02d}/{maximum_lap} | 선 사이 이동은 표시용 애니메이션')
            left, right, top, bottom = 70, 1040, 170, 610
            n = max(22, len(names))
            xy = lambda lap, pos: (left + lap / maximum_lap * (right-left), top + (pos-1)/(n-1)*(bottom-top))
            for pos in range(1, n+1):
                y = xy(0, pos)[1]
                draw.line((left, y, right, y), fill="#25354a")
                draw.text((25, y-8), str(pos), font=fonts[15], fill="#bacbe0")
            for lap in range(0, maximum_lap+1, 5):
                x = xy(lap, 1)[0]
                draw.text((x-8, bottom+10), str(lap), font=fonts[15], fill="#bacbe0")
            for driver, points in chart.items():
                shown = [p for p in points if p[0] <= progress]
                if not shown:
                    continue
                pixels = [xy(*p) for p in shown]
                if len(pixels) > 1:
                    draw.line(pixels, fill=colors[driver], width=3 if driver in pair else 1)
                x, y = pixels[-1]
                draw.ellipse((x-4,y-4,x+4,y+4), fill=colors[driver])
            # Fixed driver legend avoids overlapping rank labels, including retired drivers.
            for j, driver in enumerate(names):
                y = 160 + j * 21
                draw.text((1070, y), f'{names[driver].get("name_acronym", driver)} #{driver}', font=fonts[15], fill=colors[driver])
            draw.text((40, 658), "OpenF1 position · 순위 변화에는 피트·리타이어 등이 포함됩니다. 선 교차 수는 실제 추월 횟수가 아닙니다.", font=fonts[18], fill="#bacbe0")
            yield im
    lap_file = f"{key}-lap-chart.mp4"
    encode(lap_file, lap_frames())
    videos.append({"file": lap_file, "title": "전체 드라이버 · 레이스 순위 흐름", "description": "우승자의 각 랩 완료 시각에 기록된 순위를 연결했습니다. 각 선수의 결승선 통과 순위와는 기준이 다르며, 순위 변화·선 교차를 실제 추월 횟수로 세지 않습니다. 원본 게시물의 ‘46랩 선두·30회 이상 교체’ 주장은 검증 수치로 사용하지 않았습니다."})
    manifest = {"version": VERSION, "session_key": key, "signature": signature, "source_file": source.name, "source": raw["source"], "reference": raw["reference"], "fetched_at": raw["fetched_at"], "videos": videos}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def render_section(snapshot, media_root=None):
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
    for video in value["videos"]:
        asset = directory / Path(video["file"]).name
        if not asset.exists():
            continue
        uri = "data:video/mp4;base64," + base64.b64encode(asset.read_bytes()).decode()
        cards.append(f'<h3>{html.escape(video["title"])}</h3><p>{html.escape(video["description"])}</p><video controls playsinline preload="none" style="width:100%;max-width:1280px;background:#0b1321" src="{uri}"></video><p><a download="{html.escape(asset.name)}" href="{uri}">MP4 영상 다운로드</a></p>')
    if not cards:
        return ""
    return '<section id="data-videos"><h2>영상으로 보는 레이스</h2><p>실제 수집한 OpenF1 데이터로 만든 그래픽 영상입니다. 중계 장면이나 추정 제동 압력은 포함하지 않습니다.</p>' + "".join(cards) + f'<p>출처: <a href="https://openf1.org/docs/">OpenF1 car_data · position · laps</a> · 수집 {html.escape(value["fetched_at"])}<br>구성 참고: <a href="{REFERENCE}">라스베가스 랩 차트 릴스</a> (공개 설명만 확인, 영상 화면 미확인).</p></section>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT / "reports")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    import weekend_report
    paths = [args.snapshot] if args.snapshot else sorted(args.root.glob("weekend-*/data/*.json"))
    for path in paths:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot.get("session", {}).get("session_name") != "Race" or not snapshot.get("data", {}).get("session_result"):
            continue
        # Automatic runs only process snapshots freshly collected in this run.
        if not args.snapshot and datetime.now(timezone.utc).timestamp() - epoch(snapshot["fetched_at"]) > 1800:
            continue
        directory = path.parent.parent / "media"
        source = directory / f'{snapshot["session"]["session_key"]}-video-data.json'
        try:
            if not args.offline:
                source = collect(snapshot, directory, weekend_report.fetch)
            changed = render_videos(snapshot, source, directory)
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
