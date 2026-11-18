import re
from pathlib import Path
from urllib.parse import urlsplit
from typing import Callable


VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024


def normalize_youtube_url(value: str) -> tuple[str, str]:
    if len(value) > 2048:
        raise ValueError("The YouTube video link is too long.")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid public YouTube video link.") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise ValueError("Use a YouTube video link from youtube.com or youtu.be.")
    if parsed.username or parsed.password or port not in (None, 80, 443):
        raise ValueError("Enter a regular public YouTube video link without a custom server or port.")

    parts = [part for part in parsed.path.split("/") if part]
    video_id = ""
    if host == "youtu.be" and parts:
        video_id = parts[0]
    elif parsed.path.rstrip("/") == "/watch":
        from urllib.parse import parse_qs
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
    elif len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
        video_id = parts[1]
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("That link does not contain a valid YouTube video ID.")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def download_youtube_video(url: str, folder: Path,
                           progress_hook: Callable[[dict], None] | None = None) -> tuple[Path, dict]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("YouTube import needs yt-dlp. Run install.bat to install the current requirements.") from exc

    folder.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(folder / "source.%(ext)s"),
        "noplaylist": True,
        "ignoreconfig": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "max_filesize": MAX_VIDEO_BYTES,
        "progress_hooks": [progress_hook] if progress_hook else [],
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            if not info:
                raise RuntimeError("YouTube did not return video details.")
            candidates = []
            final_path = info.get("filepath")
            if final_path:
                candidates.append(Path(final_path))
            try:
                candidates.append(Path(downloader.prepare_filename(info)))
            except Exception:
                pass
    except RuntimeError:
        raise
    except Exception as exc:
        detail = str(exc).strip()[:500]
        raise RuntimeError(f"YouTube download failed: {detail}") from exc

    for candidate in folder.glob("source.*"):
        if candidate.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
            candidates.append(candidate)
    root = folder.resolve()
    existing = []
    for path in dict.fromkeys(candidates):
        try:
            resolved = path.resolve()
            if resolved.parent == root and resolved.is_file() and resolved.stat().st_size > 0:
                existing.append(resolved)
        except OSError:
            continue
    if not existing:
        raise RuntimeError("The YouTube download finished without a usable video file. Check that FFmpeg is installed.")
    source = existing[0]
    if source.stat().st_size > MAX_VIDEO_BYTES:
        raise RuntimeError("This video is larger than ClipForge's 4 GB source limit.")
    return source, info
