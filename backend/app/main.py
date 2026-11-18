import json
import logging
import mimetypes
import re
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import ROOT, connect, init_db, decode_json_fields
from .settings import load_settings, save_settings, public_settings
from .services.pexels import search_videos, download_video
from .services.pipeline import process_project
from .services.render import render_clip
from .services.youtube import normalize_youtube_url, download_youtube_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOG = logging.getLogger("clipforge")
PROJECT_DIR = ROOT / "projects"
EXPORT_DIR = ROOT / "exports"
FRONTEND_DIR = ROOT / "frontend"
MAX_UPLOAD = 4 * 1024 * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
EXPORT_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clip-export")
BROLL_SEARCHES: dict[str, dict[str, Any]] = {}
BROLL_LOCK = threading.Lock()
ACTIVE_PROCESS: dict[str, threading.Event] = {}
PROCESS_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

app = FastAPI(title="ClipForge AI", version="1.1.0")


@app.on_event("startup")
def startup() -> None:
    for directory in (PROJECT_DIR, EXPORT_DIR, ROOT / "temp", ROOT / "data"):
        directory.mkdir(parents=True, exist_ok=True)
    init_db()
    with connect() as db:
        db.execute("UPDATE projects SET status='failed', stage='App closed before processing finished · retry this project', error='The previous processing session stopped before completion.' WHERE status IN ('processing','importing')")
        db.execute("UPDATE export_jobs SET status='failed', error='The previous export session stopped before completion.', finished_at=? WHERE status IN ('queued','rendering')", (_utc_now(),))
    for child in (ROOT / "temp").glob("render_*"):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def _json_clip(row: dict) -> dict:
    return decode_json_fields(dict(row), ("titles", "hashtags"))


def _project(project_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Project not found")
        data = dict(row)
        transcript_data = json.loads(data.pop("transcript_json") or "[]")
        data["transcript"] = ({"language": transcript_data.get("language"),
                               "segment_count": len(transcript_data.get("segments", []))}
                              if isinstance(transcript_data, dict) else {"language": None, "segment_count": 0})
        data["settings"] = json.loads(data.pop("settings_json") or "{}")
        data["source_ready"] = Path(data["source_path"]).is_file()
        clips = db.execute("SELECT * FROM clips WHERE project_id = ? AND active=1 ORDER BY score DESC, start ASC", (project_id,)).fetchall()
        clip_data = []
        for clip_row in clips:
            clip = _json_clip(dict(clip_row))
            assets = db.execute("SELECT * FROM broll WHERE clip_id = ? ORDER BY start_offset", (clip["id"],)).fetchall()
            clip["broll"] = [{k: v for k, v in dict(asset).items() if k != "asset_path"} | {
                "media_url": f"/api/broll/{asset['id']}/media"} for asset in assets]
            clip["export_url"] = f"/api/clips/{clip['id']}/exported" if clip.get("exported_path") else None
            clip_data.append(clip)
        data["clips"] = clip_data
        data["source_url"] = f"/api/projects/{project_id}/source"
        data["thumbnail_url"] = f"/api/projects/{project_id}/thumbnail"
        return data


def _get_clip(clip_id: str) -> tuple[dict, dict, list[dict], list[dict]]:
    with connect() as db:
        row = db.execute("""SELECT c.*,p.source_path,p.source_name,p.duration AS project_duration,p.width,p.height,
            p.name AS project_name,p.transcript_json FROM clips c JOIN projects p ON p.id=c.project_id WHERE c.id=?""",
            (clip_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Clip not found")
        clip = _json_clip(dict(row))
        project = {"id": clip["project_id"], "name": clip["project_name"], "source_path": clip["source_path"],
                   "source_name": clip["source_name"], "duration": clip["project_duration"], "width": clip["width"], "height": clip["height"]}
        transcript = json.loads(clip.pop("transcript_json") or "{}")
        segments = transcript.get("segments", []) if isinstance(transcript, dict) else []
        broll = [dict(item) for item in db.execute("SELECT * FROM broll WHERE clip_id=? ORDER BY start_offset", (clip_id,)).fetchall()]
        return clip, project, segments, broll


def _ffprobe(path: Path) -> dict:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                capture_output=True, text=True, timeout=90)
    except FileNotFoundError as exc:
        raise HTTPException(500, "FFprobe was not found. Install FFmpeg and restart ClipForge.") from exc
    if result.returncode:
        raise HTTPException(400, "This file could not be read as a video.")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Video metadata could not be read.") from exc
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise HTTPException(400, "The selected file does not contain a video stream.")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    return {"duration": duration, "width": int(video.get("width", 0)), "height": int(video.get("height", 0)),
            "codec": video.get("codec_name", "unknown")}


def _make_thumbnail(source: Path, target: Path, duration: float) -> None:
    try:
        offset = min(1.0, max(0.0, duration * .1))
        result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{offset:.2f}",
                                 "-i", str(source), "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(target)],
                                capture_output=True, timeout=45)
        if result.returncode or not target.is_file():
            target.unlink(missing_ok=True)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        target.unlink(missing_ok=True)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "name": "ClipForge AI"}


@app.get("/api/settings")
def get_settings() -> dict:
    return public_settings()


@app.put("/api/settings")
def put_settings(payload: dict = Body(...)) -> dict:
    updates = {}
    for key in ("gemini_api_key", "pexels_api_key"):
        if key in payload:
            value = str(payload[key] or "").strip()
            if len(value) > 300:
                raise HTTPException(400, f"{key.replace('_', ' ').title()} is too long.")
            updates[key] = value
    if "gemini_model" in payload:
        model = str(payload["gemini_model"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{2,100}", model):
            raise HTTPException(400, "Gemini model name is invalid.")
        updates["gemini_model"] = model
    if "whisper_model" in payload:
        model = str(payload["whisper_model"])
        if model not in {"tiny", "base", "small", "medium", "large-v3"}:
            raise HTTPException(400, "Choose a supported Whisper model.")
        updates["whisper_model"] = model
    if "auto_broll" in payload:
        updates["auto_broll"] = bool(payload["auto_broll"])
    return save_settings(updates)


@app.get("/api/projects")
def list_projects() -> dict:
    with connect() as db:
        rows = db.execute("""SELECT p.*,(SELECT COUNT(*) FROM clips c WHERE c.project_id=p.id AND c.active=1) AS clip_count
            FROM projects p ORDER BY created_at DESC""").fetchall()
        export_count = db.execute("SELECT COUNT(*) AS n FROM export_jobs WHERE status='complete'").fetchone()["n"]
        clip_total = db.execute("SELECT COUNT(*) AS n FROM clips").fetchone()["n"]
    projects = []
    for row in rows:
        item = dict(row)
        item.pop("transcript_json", None)
        item.pop("settings_json", None)
        projects.append(item)
    return {"projects": projects, "stats": {"videos": len(projects), "clips": clip_total, "exports": export_count}}


@app.post("/api/upload")
async def upload_videos(files: list[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(400, "Choose one or more video files.")
    results = []
    for upload in files[:20]:
        safe_name = Path(upload.filename or "video").name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"{safe_name}: choose MP4, MOV, MKV, AVI or WEBM.")
        project_id = uuid.uuid4().hex
        folder = PROJECT_DIR / project_id
        folder.mkdir(parents=True, exist_ok=False)
        target = folder / f"source{suffix}"
        size = 0
        try:
            with target.open("wb") as output:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, f"{safe_name}: maximum video size is 4 GB.")
                    output.write(chunk)
            if size == 0:
                raise HTTPException(400, f"{safe_name}: the file is empty.")
            metadata = _ffprobe(target)
            _make_thumbnail(target, folder / "thumbnail.jpg", metadata["duration"])
            now = _utc_now()
            with connect() as db:
                db.execute("""INSERT INTO projects (id,name,source_name,source_path,duration,width,height,file_size,
                    status,progress,stage,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (project_id, Path(safe_name).stem[:120], safe_name, str(target), metadata["duration"],
                     metadata["width"], metadata["height"], size, "ready", 0, "Ready to analyze", now))
            results.append(_project(project_id))
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        finally:
            await upload.close()
    return {"projects": results}


@app.post("/api/import-youtube")
def import_youtube(payload: dict = Body(...)) -> dict:
    if payload.get("rights_confirmed") is not True:
        raise HTTPException(400, "Confirm that you have permission to download and edit this video.")
    try:
        youtube_url, video_id = normalize_youtube_url(str(payload.get("url", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    project_id = uuid.uuid4().hex
    folder = PROJECT_DIR / project_id
    folder.mkdir(parents=True, exist_ok=False)
    now = _utc_now()
    with connect() as db:
        db.execute("""INSERT INTO projects (id,name,source_name,source_path,youtube_url,status,progress,stage,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (project_id, f"YouTube {video_id}", "source.mp4", str(folder / "_pending_source"), youtube_url,
             "importing", 1, "Preparing authorized YouTube download", now))
    threading.Thread(target=_import_youtube_project, args=(project_id, youtube_url), daemon=True,
                     name=f"clipforge-youtube-{project_id[:8]}").start()
    return {"project": _project(project_id)}


def _import_youtube_project(project_id: str, youtube_url: str) -> None:
    folder = PROJECT_DIR / project_id
    last_progress = {"value": -1, "percent": 0}

    def on_progress(info: dict) -> None:
        if info.get("status") != "downloading":
            return
        percent = None
        if info.get("total_bytes"):
            percent = 100 * info.get("downloaded_bytes", 0) / info["total_bytes"]
        elif info.get("total_bytes_estimate"):
            percent = 100 * info.get("downloaded_bytes", 0) / info["total_bytes_estimate"]
        if percent is None:
            return
        percent = max(last_progress["percent"], min(100, percent))
        value = max(1, min(19, int(1 + percent * .18)))
        if value == last_progress["value"]:
            return
        last_progress["value"] = value
        last_progress["percent"] = percent
        with connect() as db:
            db.execute("UPDATE projects SET progress=?,stage=? WHERE id=? AND status='importing'",
                       (value, f"Downloading authorized YouTube video · {int(percent)}%", project_id))

    try:
        source, info = download_youtube_video(youtube_url, folder, on_progress)
        metadata = _ffprobe(source)
        size = source.stat().st_size
        _make_thumbnail(source, folder / "thumbnail.jpg", metadata["duration"])
        title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", str(info.get("title") or "YouTube video")).strip()[:120]
        source_name = f"{title or 'YouTube video'}{source.suffix.lower()}"[:180]
        with connect() as db:
            db.execute("""UPDATE projects SET name=?,source_name=?,source_path=?,duration=?,width=?,height=?,file_size=?,
                status='ready',progress=0,stage='YouTube source downloaded · ready to analyze',error=NULL WHERE id=?""",
                (title or "YouTube video", source_name, str(source), metadata["duration"], metadata["width"],
                 metadata["height"], size, project_id))
    except Exception as exc:
        LOG.exception("YouTube import failed for project %s", project_id)
        with connect() as db:
            db.execute("UPDATE projects SET status='failed',progress=0,stage='YouTube import failed',error=? WHERE id=?",
                       (str(exc)[:1000], project_id))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    return _project(project_id)


@app.get("/api/projects/{project_id}/source")
def get_source(project_id: str):
    with connect() as db:
        row = db.execute("SELECT source_path,source_name FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None or not Path(row["source_path"]).is_file():
        raise HTTPException(404, "Source video not found")
    return FileResponse(row["source_path"], filename=row["source_name"],
                        media_type=mimetypes.guess_type(row["source_name"])[0] or "application/octet-stream")


@app.get("/api/projects/{project_id}/thumbnail")
def get_thumbnail(project_id: str):
    with connect() as db:
        row = db.execute("SELECT source_path FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found")
    folder = Path(row["source_path"]).resolve().parent
    thumbnail = folder / "thumbnail.jpg"
    if folder.parent != PROJECT_DIR.resolve() or not thumbnail.is_file():
        raise HTTPException(404, "Thumbnail not available")
    return FileResponse(thumbnail, media_type="image/jpeg")


@app.patch("/api/projects/{project_id}")
def rename_project(project_id: str, payload: dict = Body(...)) -> dict:
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 120:
        raise HTTPException(400, "Project name must contain 1 to 120 characters.")
    with connect() as db:
        result = db.execute("UPDATE projects SET name=? WHERE id=?", (name, project_id))
        if result.rowcount == 0:
            raise HTTPException(404, "Project not found")
    return _project(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    folder = (PROJECT_DIR / project_id).resolve()
    if folder.parent != PROJECT_DIR.resolve():
        raise HTTPException(400, "Invalid project path.")
    with connect() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        output_paths = [r[0] for r in db.execute("SELECT output_path FROM export_jobs WHERE clip_id IN (SELECT id FROM clips WHERE project_id=?)", (project_id,)).fetchall() if r[0]]
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    shutil.rmtree(folder, ignore_errors=True)
    for output in output_paths:
        path = Path(output).resolve()
        if path.parent == EXPORT_DIR.resolve():
            path.unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/projects/{project_id}/process")
def process(project_id: str, payload: dict = Body(default={})) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Project not found")
        if row["status"] in {"processing", "importing"}:
            return {"ok": True, "message": "Analysis is already running."}
        if not Path(row["source_path"]).is_file():
            raise HTTPException(400, "The source video is not ready yet. Wait for the import to finish or import it again.")
        minimum = int(payload.get("minimum", 15))
        maximum = int(payload.get("maximum", 30))
        count = int(payload.get("count", 5))
        if minimum < 3 or maximum <= minimum or maximum > 180 or count < 1 or count > 30:
            raise HTTPException(400, "Choose a valid clip duration and clip count.")
        settings = load_settings()
        whisper_model = payload.get("whisper_model", settings["whisper_model"])
        if whisper_model not in {"tiny", "base", "small", "medium", "large-v3"}:
            raise HTTPException(400, "Choose a supported Whisper model.")
        config = {"minimum": minimum, "maximum": maximum, "count": count, "whisper_model": whisper_model,
                  "auto_broll": bool(payload.get("auto_broll", settings["auto_broll"]))}
        db.execute("UPDATE projects SET status='processing', progress=0, stage='Queued', error=NULL, settings_json=? WHERE id=?",
                   (json.dumps(config), project_id))
    cancel_event = threading.Event()
    with PROCESS_LOCK:
        ACTIVE_PROCESS[project_id] = cancel_event
    threading.Thread(target=_run_project, args=(project_id, cancel_event), daemon=True, name=f"clipforge-{project_id[:8]}").start()
    return {"ok": True, "message": "Analysis started."}


def _run_project(project_id: str, cancel_event: threading.Event) -> None:
    try:
        process_project(project_id, cancel_event)
    finally:
        with PROCESS_LOCK:
            ACTIVE_PROCESS.pop(project_id, None)


@app.post("/api/projects/{project_id}/cancel")
def cancel_processing(project_id: str) -> dict:
    with PROCESS_LOCK:
        event = ACTIVE_PROCESS.get(project_id)
    if event is None:
        raise HTTPException(409, "This project is not processing.")
    event.set()
    with connect() as db:
        db.execute("UPDATE projects SET stage='Cancelling local analysis' WHERE id=?", (project_id,))
    return {"ok": True, "message": "Cancellation requested."}


@app.patch("/api/clips/{clip_id}")
def edit_clip(clip_id: str, payload: dict = Body(...)) -> dict:
    allowed = {"start", "end", "transcript", "title", "caption", "description", "subtitle_style", "layout",
               "aspect_ratio", "output_size", "volume", "speed", "subtitle_enabled", "hook"}
    updates = {key: value for key, value in payload.items() if key in allowed}
    with connect() as db:
        row = db.execute("SELECT c.*,p.duration AS project_duration FROM clips c JOIN projects p ON p.id=c.project_id WHERE c.id=?", (clip_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Clip not found")
        if "start" in updates or "end" in updates:
            start = float(updates.get("start", row["start"]))
            end = float(updates.get("end", row["end"]))
            if start < 0 or end <= start or end > float(row["project_duration"]) + .1:
                raise HTTPException(400, "Clip trim points are outside the source video.")
            updates.update(start=start, end=end)
        for key, limit in {"title": 140, "caption": 1000, "description": 1000, "transcript": 12000, "hook": 300}.items():
            if key in updates:
                updates[key] = str(updates[key])[:limit]
        if "subtitle_style" in updates and updates["subtitle_style"] not in {"classic", "modern", "hormozi", "minimal", "gaming", "cinematic", "karaoke"}:
            raise HTTPException(400, "Unknown subtitle style.")
        if "layout" in updates and updates["layout"] not in {"smart", "blur", "center"}:
            raise HTTPException(400, "Unknown video layout.")
        if "aspect_ratio" in updates and updates["aspect_ratio"] not in {"9:16", "16:9", "1:1"}:
            raise HTTPException(400, "Unknown aspect ratio.")
        if "output_size" in updates and updates["output_size"] not in {"720", "1080"}:
            raise HTTPException(400, "Choose 720p or 1080p output.")
        if "volume" in updates:
            updates["volume"] = max(0, min(3, float(updates["volume"])))
        if "speed" in updates:
            updates["speed"] = max(.5, min(2, float(updates["speed"])))
        if "subtitle_enabled" in updates:
            updates["subtitle_enabled"] = int(bool(updates["subtitle_enabled"]))
        if updates:
            sets = ",".join(f"{key}=?" for key in updates)
            db.execute(f"UPDATE clips SET {sets}, exported_path=NULL WHERE id=?", list(updates.values()) + [clip_id])
    return {"ok": True}


def _export_job(job_id: str) -> None:
    with connect() as db:
        job = db.execute("SELECT * FROM export_jobs WHERE id=?", (job_id,)).fetchone()
    if job is None:
        return
    try:
        clip, project, segments, broll = _get_clip(job["clip_id"])
        with connect() as db:
            db.execute("UPDATE export_jobs SET status='rendering' WHERE id=?", (job_id,))
        path = render_clip(project, clip, segments, broll)
        with connect() as db:
            db.execute("UPDATE clips SET exported_path=? WHERE id=?", (path, clip["id"]))
            db.execute("UPDATE export_jobs SET status='complete',output_path=?,finished_at=? WHERE id=?",
                       (path, _utc_now(), job_id))
    except Exception as exc:
        LOG.exception("Export failed for job %s", job_id)
        with connect() as db:
            db.execute("UPDATE export_jobs SET status='failed',error=?,finished_at=? WHERE id=?",
                       (str(exc)[:1500], _utc_now(), job_id))


def _queue_export(clip_id: str) -> dict:
    with connect() as db:
        if not db.execute("SELECT 1 FROM clips WHERE id=?", (clip_id,)).fetchone():
            raise HTTPException(404, "Clip not found")
        job_id = uuid.uuid4().hex
        db.execute("INSERT INTO export_jobs (id,clip_id,status,created_at) VALUES (?,?,?,?)",
                   (job_id, clip_id, "queued", _utc_now()))
    EXPORT_POOL.submit(_export_job, job_id)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/clips/{clip_id}/export")
def export_clip(clip_id: str) -> dict:
    return _queue_export(clip_id)


@app.post("/api/projects/{project_id}/export-all")
def export_all(project_id: str) -> dict:
    with connect() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        clips = db.execute("SELECT id FROM clips WHERE project_id=? AND active=1", (project_id,)).fetchall()
    if not clips:
        raise HTTPException(400, "Analyze the video before exporting clips.")
    return {"jobs": [_queue_export(row["id"]) for row in clips]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM export_jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Export job not found")
    item = dict(row)
    item["download_url"] = f"/api/jobs/{job_id}/download" if item.get("output_path") else None
    return item


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    item = get_job(job_id)
    path = item.get("output_path")
    if item["status"] != "complete" or not path or not Path(path).is_file():
        raise HTTPException(404, "Export is not ready yet.")
    if Path(path).resolve().parent != EXPORT_DIR.resolve():
        raise HTTPException(400, "Invalid export path.")
    return FileResponse(path, filename=Path(path).name, media_type="video/mp4")


@app.get("/api/clips/{clip_id}/exported")
def get_exported(clip_id: str):
    clip, _, _, _ = _get_clip(clip_id)
    path = clip.get("exported_path")
    if not path or not Path(path).is_file() or Path(path).resolve().parent != EXPORT_DIR.resolve():
        raise HTTPException(404, "Export this clip first.")
    return FileResponse(path, filename=Path(path).name, media_type="video/mp4")


@app.get("/api/exports")
def list_exports() -> dict:
    with connect() as db:
        rows = db.execute("""SELECT e.*,c.title,p.name AS project_name FROM export_jobs e
            JOIN clips c ON c.id=e.clip_id JOIN projects p ON p.id=c.project_id
            WHERE e.status='complete' ORDER BY e.finished_at DESC LIMIT 100""").fetchall()
    return {"exports": [{**dict(r), "download_url": f"/api/jobs/{r['id']}/download"} for r in rows]}


@app.get("/api/clips/{clip_id}/broll/search")
def search_broll(clip_id: str, query: str, orientation: str = "portrait") -> dict:
    _get_clip(clip_id)
    if len(query.strip()) < 2:
        raise HTTPException(400, "Enter a short visual search phrase.")
    orientation = orientation if orientation in {"portrait", "landscape", "square"} else "portrait"
    settings = load_settings()
    if not settings["pexels_api_key"]:
        raise HTTPException(400, "Add a Pexels API key in Settings first.")
    try:
        videos = search_videos(query.strip(), settings["pexels_api_key"], orientation)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    results = []
    with BROLL_LOCK:
        for video in videos:
            token = uuid.uuid4().hex
            video["query"] = query.strip()
            BROLL_SEARCHES[token] = {"video": video, "clip_id": clip_id}
            results.append({k: v for k, v in video.items() if k != "download_url"} | {"selection_token": token})
        while len(BROLL_SEARCHES) > 500:
            BROLL_SEARCHES.pop(next(iter(BROLL_SEARCHES)))
    return {"results": results, "credit": "Pexels footage · credit photographer when sharing", "pexels_url": "https://www.pexels.com"}


@app.post("/api/clips/{clip_id}/broll/add")
def add_broll(clip_id: str, payload: dict = Body(...)) -> dict:
    _get_clip(clip_id)
    token = str(payload.get("selection_token", ""))
    with BROLL_LOCK:
        selection = BROLL_SEARCHES.pop(token, None)
    if not selection or selection["clip_id"] != clip_id:
        raise HTTPException(400, "That Pexels result expired. Search again.")
    clip, project, _, _ = _get_clip(clip_id)
    video = selection["video"]
    try:
        asset = download_video(video, PROJECT_DIR / project["id"] / "assets")
    except Exception as exc:
        raise HTTPException(502, f"Could not download Pexels video: {exc}") from exc
    full_duration = max(.1, float(clip["end"] - clip["start"]))
    offset = max(0, min(full_duration - .2, float(payload.get("start_offset", full_duration * .45))))
    duration = max(.2, min(float(payload.get("duration", 4)), full_duration - offset, 12))
    asset_id = uuid.uuid4().hex
    with connect() as db:
        db.execute("""INSERT INTO broll (id,clip_id,query,asset_path,pexels_url,photographer,photographer_url,
            start_offset,duration,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (asset_id, clip_id, video.get("query", "Pexels cutaway"), asset, video["pexels_url"], video["photographer"],
             video["photographer_url"], offset, duration, _utc_now()))
    return {"ok": True, "id": asset_id}


@app.delete("/api/broll/{asset_id}")
def delete_broll(asset_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT asset_path FROM broll WHERE id=?", (asset_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "B-roll item not found")
        path = Path(row["asset_path"]).resolve()
        db.execute("DELETE FROM broll WHERE id=?", (asset_id,))
    if path.parent.name == "assets" and "projects" in path.parts:
        path.unlink(missing_ok=True)
    return {"ok": True}


@app.patch("/api/broll/{asset_id}")
def edit_broll(asset_id: str, payload: dict = Body(...)) -> dict:
    with connect() as db:
        row = db.execute("SELECT b.*,c.end-c.start AS clip_duration FROM broll b JOIN clips c ON c.id=b.clip_id WHERE b.id=?", (asset_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "B-roll item not found")
        offset = float(payload.get("start_offset", row["start_offset"]))
        duration = float(payload.get("duration", row["duration"]))
        if offset < 0 or duration < .2 or duration > 12 or offset + duration > float(row["clip_duration"]):
            raise HTTPException(400, "B-roll placement must fit inside the clip and last 0.2 to 12 seconds.")
        db.execute("UPDATE broll SET start_offset=?,duration=? WHERE id=?", (offset, duration, asset_id))
    return {"ok": True}


@app.get("/api/broll/{asset_id}/media")
def broll_media(asset_id: str):
    with connect() as db:
        row = db.execute("SELECT asset_path FROM broll WHERE id=?", (asset_id,)).fetchone()
    if row is None or not Path(row["asset_path"]).is_file():
        raise HTTPException(404, "B-roll media not found")
    return FileResponse(row["asset_path"], media_type="video/mp4")


@app.get("/api/projects/{project_id}/transcript")
def get_transcript(project_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT transcript_json FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found")
    try:
        data = json.loads(row["transcript_json"])
    except json.JSONDecodeError:
        data = {}
    return data


@app.get("/")
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")

