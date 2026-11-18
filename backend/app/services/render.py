import json
import re
import subprocess
import uuid
from pathlib import Path
from statistics import median

from ..database import ROOT

EXPORT_DIR = ROOT / "exports"
TEMP_DIR = ROOT / "temp"


def _run(command: list[str], cwd: Path | None = None) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60 * 60)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout)[-1800:]
        raise RuntimeError(f"FFmpeg render failed: {detail}")


def _face_centers(source: str, start: float, duration: float, width: int, height: int) -> list[tuple[float, float]]:
    try:
        import cv2
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_alt2.xml"
        detector = cv2.CascadeClassifier(str(cascade_path))
        cap = cv2.VideoCapture(source)
        centers = []
        for offset in [0, duration * .25, duration * .5, duration * .75, max(0, duration - .15)]:
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + offset) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                centers.append((x + w / 2, y + h * .45))
        cap.release()
        return centers
    except Exception:
        return []


def _smooth_expr(samples: list[tuple[float, float]], duration: float, speed: float, bound: float, fallback: float) -> str:
    if not samples:
        return str(round(fallback, 2))
    values = [max(0.0, min(bound, p[0])) for p in samples]
    # Use smoothed local medians to avoid jumps when face detection flickers.
    smoothed = [median(values[max(0, i - 1):min(len(values), i + 2)]) for i in range(len(values))]
    if len(smoothed) == 1:
        return str(round(smoothed[0], 2))
    times = [duration * i / (len(smoothed) - 1) / max(.1, speed) for i in range(len(smoothed))]
    expr = str(round(smoothed[-1], 2))
    for i in range(len(smoothed) - 2, -1, -1):
        t0, t1 = times[i], times[i + 1]
        a, b = round(smoothed[i], 2), round(smoothed[i + 1], 2)
        if t1 <= t0:
            expr = str(b)
        else:
            linear = f"{a}+({b}-{a})*(t-{t0:.3f})/{(t1 - t0):.3f}"
            expr = f"if(lt(t,{t1:.3f}),{linear},{expr})"
    return expr


def _crop_filter(video_path: str, clip: dict, project: dict, out_w: int, out_h: int, speed: float) -> str:
    target_ar = out_w / out_h
    in_w, in_h = int(project["width"]), int(project["height"])
    if in_w <= 0 or in_h <= 0:
        return f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h}"
    input_ar = in_w / in_h
    if input_ar >= target_ar:
        crop_w, crop_h = int(in_h * target_ar), in_h
        centers = _face_centers(video_path, float(clip["start"]), float(clip["end"] - clip["start"]), in_w, in_h)
        if centers:
            x_values = [(x - crop_w / 2) for x, _ in centers]
            x_expr = _smooth_expr([(0, x) for x in x_values], clip["end"] - clip["start"], speed,
                                  in_w - crop_w, in_w / 2 - crop_w / 2)
        else:
            x_expr = str(round((in_w - crop_w) / 2, 2))
        y_expr = str(round((in_h - crop_h) / 2, 2))
    else:
        crop_w, crop_h = in_w, int(in_w / target_ar)
        x_expr = "0"
        centers = _face_centers(video_path, float(clip["start"]), float(clip["end"] - clip["start"]), in_w, in_h)
        if centers:
            y_values = [y - crop_h / 2 for _, y in centers]
            y_expr = _smooth_expr([(0, y) for y in y_values], clip["end"] - clip["start"], speed,
                                  in_h - crop_h, (in_h - crop_h) / 2)
        else:
            y_expr = str(round((in_h - crop_h) / 2, 2))
    return f"crop={crop_w}:{crop_h}:x='{x_expr}':y='{y_expr}',scale={out_w}:{out_h}:flags=lanczos"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ").strip()


def _caption_lines(clip: dict, transcript_segments: list[dict], highlighting: bool) -> list[tuple[float, float, list[tuple[str, float]]]]:
    start, end = float(clip["start"]), float(clip["end"])
    rows: list[tuple[float, float, list[tuple[str, float]]]] = []
    def normalize(value: str) -> str:
        return re.sub(r"[^\w']+", "", value.lower())
    source_words = []
    timed_words: list[tuple[str, float, float]] = []
    for seg in transcript_segments:
        for word in seg.get("words", []):
            if float(word.get("end", 0)) <= start or float(word.get("start", 0)) >= end:
                continue
            source_words.append((str(word.get("word", "")).strip(), max(start, float(word["start"])) - start,
                                 min(end, float(word["end"])) - start))
    target_words = (clip.get("transcript") or "").split()
    if len(source_words) == len(target_words) and all(normalize(a[0]) == normalize(b) for a, b in zip(source_words, target_words)):
        timed_words = [(word, a, b) for word, a, b in source_words]
    if not timed_words:
        words = (clip.get("transcript") or "").split()
        duration = max(.25, end - start)
        timed_words = [(word, i * duration / max(1, len(words)), (i + 1) * duration / max(1, len(words)))
                       for i, word in enumerate(words)]
    group_size = 1 if highlighting else 5
    for offset in range(0, len(timed_words), group_size):
        group = timed_words[offset:offset + group_size]
        if not group:
            continue
        word_data = [(w, max(.08, b - a)) for w, a, b in group]
        rows.append((group[0][1], group[-1][2], word_data))
    return rows


def _write_ass(path: Path, clip: dict, transcript_segments: list[dict], out_w: int, out_h: int) -> None:
    styles = {
        "classic": ("Arial", 44, "&H00FFFFFF", "&H00000000", 2, 1, 140),
        "modern": ("Arial", 52, "&H00FFFFFF", "&H0000D8FF", 3, 1, 180),
        "hormozi": ("Arial", 58, "&H00FFFFFF", "&H0000D8FF", 3, 1, 190),
        "minimal": ("Arial", 40, "&H00FFFFFF", "&H00000000", 1, 1, 125),
        "gaming": ("Arial", 50, "&H00FFFFFF", "&H00FFB543", 3, 1, 175),
        "cinematic": ("Arial", 38, "&H00FFFFFF", "&H00000000", 2, 1, 120),
        "karaoke": ("Arial", 52, "&H00FFFFFF", "&H0000D8FF", 3, 1, 180),
    }
    font, size, primary, secondary, outline, shadow, margin_v = styles.get(clip.get("subtitle_style", "modern"), styles["modern"])
    scale = min(out_w / 1080, out_h / 1080)
    size = max(22, round(size * scale))
    margin_v = round(margin_v * scale)
    bold = -1 if clip.get("subtitle_style") in ("modern", "hormozi", "gaming", "karaoke") else 0
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {out_w}
PlayResY: {out_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{secondary},&H99000000,&H80000000,{bold},0,0,0,100,100,0,0,1,{outline},{shadow},2,55,55,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    highlighting = clip.get("subtitle_style") in {"karaoke", "hormozi"}
    for start, end, words in _caption_lines(clip, transcript_segments, highlighting):
        if highlighting:
            body = "".join(f"{{\\k{max(1, round(sec * 100))}}}{_ass_escape(word)} " for word, sec in words).strip()
        else:
            body = _ass_escape(" ".join(word for word, _ in words))
        if not body:
            continue
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(max(start + .08, end))},Default,,0,0,0,,{body}\n")
    path.write_text("".join(lines), encoding="utf-8-sig")


def _ass_time(value: float) -> str:
    value = max(0, value)
    hours = int(value // 3600)
    minutes = int(value % 3600 // 60)
    seconds = value % 60
    return f"{hours}:{minutes:02}:{seconds:05.2f}"


def _atempo(speed: float) -> str:
    factors = []
    remaining = speed
    while remaining > 2:
        factors.append("atempo=2")
        remaining /= 2
    while remaining < .5:
        factors.append("atempo=0.5")
        remaining /= .5
    factors.append(f"atempo={remaining:.4f}")
    return ",".join(factors)


def render_clip(project: dict, clip: dict, transcript_segments: list[dict], broll_rows: list[dict]) -> str:
    source = Path(project["source_path"])
    if not source.is_file():
        raise RuntimeError("The original video file is missing from the project folder.")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    out_id = uuid.uuid4().hex[:8]
    work = TEMP_DIR / f"render_{clip['id']}_{out_id}"
    work.mkdir(parents=True, exist_ok=True)
    out = EXPORT_DIR / f"{project['name'][:50]}_{clip['id'][:8]}_{out_id}.mp4"
    duration = max(.2, float(clip["end"]) - float(clip["start"]))
    speed = max(.5, min(2.0, float(clip.get("speed", 1))))
    out_w, out_h = _output_size(clip.get("aspect_ratio", "9:16"), clip.get("output_size", "1080"))
    font_file = work / "captions.ass"
    if clip.get("subtitle_enabled", True) and clip.get("transcript"):
        _write_ass(font_file, clip, transcript_segments, out_w, out_h)

    layout = clip.get("layout", "smart")
    if layout == "blur":
        base = (f"[0:v]setpts=PTS/{speed:.4f},split=2[back][front];"
                f"[back]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},boxblur=26:12[bg];"
                f"[front]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base]")
    else:
        crop = _crop_filter(str(source), clip, project, out_w, out_h, speed) if layout == "smart" else \
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h}:x=(iw-ow)/2:y=(ih-oh)/2:flags=lanczos"
        base = f"[0:v]setpts=PTS/{speed:.4f},{crop}[base]"
    graph = [base]
    current = "base"
    inputs: list[str] = ["-ss", f"{float(clip['start']):.3f}", "-i", str(source)]
    for index, item in enumerate(broll_rows):
        asset = Path(item["asset_path"])
        if not asset.is_file():
            continue
        input_index = len([x for x in inputs if x == "-i"])  # index of next video input
        inputs.extend(["-stream_loop", "-1", "-i", str(asset)])
        layer = f"br{index}"
        overlay = f"v{index}"
        offset = max(0.0, float(item.get("start_offset", 0))) / speed
        bdur = min(float(item.get("duration", 3)), duration - float(item.get("start_offset", 0))) / speed
        if bdur <= .05:
            continue
        graph.append(f"[{input_index}:v]trim=duration={bdur:.3f},setpts=PTS-STARTPTS,scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h}[{layer}]")
        graph.append(f"[{current}][{layer}]overlay=enable='between(t,{offset:.3f},{offset + bdur:.3f})'[{overlay}]")
        current = overlay
    final = current
    if font_file.exists():
        graph.append(f"[{current}]subtitles=captions.ass[vout]")
        final = "vout"
    graph.append(f"[{final}]fps=30,format=yuv420p[outv]")
    credits = " | ".join(
        f"Video by {item.get('photographer') or 'Pexels contributor'} on Pexels: {item.get('pexels_url')}"
        for item in broll_rows if item.get("pexels_url")
    )
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
               "-filter_complex", ";".join(graph), "-map", "[outv]", "-map", "0:a?",
               "-af", f"volume={max(0, min(3, float(clip.get('volume', 1)))):.3f},{_atempo(speed)}",
               "-t", f"{duration / speed:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    if credits:
        command[-1:-1] = ["-metadata", f"comment={credits}"]
    try:
        _run(command, work)
        if not out.exists() or out.stat().st_size < 1024:
            raise RuntimeError("FFmpeg finished without creating a usable MP4.")
    except Exception:
        out.unlink(missing_ok=True)
        raise
    finally:
        for path in work.iterdir():
            path.unlink(missing_ok=True)
        work.rmdir()
    return str(out)


def _output_size(ratio: str, quality: str) -> tuple[int, int]:
    size = 720 if str(quality) == "720" else 1080
    if ratio == "1:1":
        return size, size
    if ratio == "16:9":
        return (1280, 720) if size == 720 else (1920, 1080)
    return (720, 1280) if size == 720 else (1080, 1920)

