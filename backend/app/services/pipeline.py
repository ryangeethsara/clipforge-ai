import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..database import connect, ROOT
from ..settings import load_settings
from .analysis import transcribe, make_candidates, gemini_enrich
from .pexels import search_videos, download_video

LOG = logging.getLogger("clipforge.pipeline")


def _set_project(project_id: str, **fields) -> None:
    if not fields:
        return
    keys = list(fields)
    sql = ", ".join(f"{key} = ?" for key in keys)
    with connect() as db:
        db.execute(f"UPDATE projects SET {sql} WHERE id = ?", [fields[k] for k in keys] + [project_id])


def process_project(project_id: str, cancel_event: threading.Event | None = None) -> None:
    local_fallback = False
    broll_issue = False
    try:
        with connect() as db:
            project = dict(db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
            settings = load_settings()
            config = json.loads(project.get("settings_json") or "{}")
        _set_project(project_id, status="processing", progress=4, stage="Preparing local speech recognition", error=None)
        segments, language = transcribe(project["source_path"], config.get("whisper_model", settings["whisper_model"]), cancel_event)
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Processing cancelled by user.")
        with connect() as db:
            db.execute("UPDATE projects SET transcript_json = ?, progress = 36, stage = ? WHERE id = ?",
                       (json.dumps({"language": language, "segments": segments}, ensure_ascii=False), "Finding complete moments", project_id))
        if not segments:
            raise RuntimeError("No speech was detected. Try another source or a larger Whisper model.")
        minimum = int(config.get("minimum", 15))
        maximum = int(config.get("maximum", 30))
        amount = max(1, min(30, int(config.get("count", 5))))
        if project["duration"] > 0 and project["duration"] < minimum:
            minimum = max(3, int(project["duration"] * .45))
            maximum = max(minimum + 1, int(project["duration"] * .98))
        candidates = make_candidates(segments, minimum, maximum, amount)
        if not candidates:
            _set_project(project_id, status="complete", progress=100, stage="No complete moments fit this duration range")
            return
        if settings["gemini_api_key"]:
            _set_project(project_id, progress=48, stage=f"Ranking {len(candidates)} moments with Gemini")
            try:
                candidates = gemini_enrich(candidates, settings["gemini_api_key"], settings["gemini_model"])
            except Exception as exc:
                LOG.exception("Gemini analysis failed for project %s", project_id)
                local_fallback = True
                _set_project(project_id, stage="Gemini unavailable · finishing with local ranking")
        else:
            local_fallback = True
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        chosen = candidates[:amount]
        archived_previous = False
        created = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        for index, item in enumerate(chosen):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Processing cancelled by user.")
            if not archived_previous:
                with connect() as db:
                    db.execute("UPDATE clips SET active=0 WHERE project_id=? AND active=1", (project_id,))
                archived_previous = True
            clip_id = uuid.uuid4().hex
            transcript = item["transcript"]
            title = item.get("title") or transcript[:65].strip().rstrip(".,!?")
            titles = list(dict.fromkeys([str(s).strip() for s in item.get("titles", []) if str(s).strip()]))
            for alternative in [title, f"The idea behind {title[:45]}", f"Why this matters: {title[:40]}"]:
                if alternative not in titles:
                    titles.append(alternative)
                if len(titles) == 3:
                    break
            titles = titles[:3]
            caption = item.get("caption") or transcript[:240]
            tags = item.get("hashtags") or ["#shorts", "#video", "#clips"]
            with connect() as db:
                db.execute("""INSERT INTO clips (id,project_id,start,end,transcript,title,titles_json,description,caption,
                    hashtags_json,hook,reason,score,hook_score,broll_query,broll_reason,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (clip_id, project_id, item["start"], item["end"], transcript, title,
                     json.dumps(titles, ensure_ascii=False), item.get("description", ""), caption,
                     json.dumps(tags, ensure_ascii=False), item.get("hook", ""), item.get("reason", ""),
                     item.get("score", 0), item.get("hook_score", 0), item.get("broll_query", ""),
                     item.get("broll_reason", ""), created))
            if config.get("auto_broll") and settings["pexels_api_key"] and item.get("broll_query"):
                try:
                    results = search_videos(item["broll_query"], settings["pexels_api_key"], "portrait", 4)
                    if not results:
                        results = search_videos(item["broll_query"], settings["pexels_api_key"], "landscape", 4)
                    if results:
                        video = results[0]
                        asset = download_video(video, ROOT / "projects" / project_id / "assets")
                        clip_duration = item["end"] - item["start"]
                        overlay_duration = min(5.0, max(1.5, clip_duration * .22))
                        offset = max(0, (clip_duration - overlay_duration) * .52)
                        with connect() as db:
                            db.execute("""INSERT INTO broll (id,clip_id,query,asset_path,pexels_url,photographer,
                                photographer_url,start_offset,duration,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                (uuid.uuid4().hex, clip_id, item["broll_query"], asset, video["pexels_url"],
                                 video["photographer"], video["photographer_url"], offset, overlay_duration, created))
                except Exception:
                    LOG.exception("Pexels B-roll failed for clip %s", clip_id)
                    broll_issue = True
            _set_project(project_id, progress=55 + int(40 * (index + 1) / len(chosen)), stage=f"Preparing clip {index + 1} of {len(chosen)}")
        stage = "Complete · local editorial ranking used" if local_fallback else "Complete · Gemini ranked clips"
        if broll_issue:
            stage += " · some Pexels searches were skipped"
        _set_project(project_id, status="complete", progress=100, stage=stage)
    except Exception as exc:
        LOG.exception("Project processing failed: %s", project_id)
        if cancel_event and cancel_event.is_set():
            _set_project(project_id, status="cancelled", progress=0, stage="Processing cancelled", error=None)
        else:
            _set_project(project_id, status="failed", progress=0, stage="Processing failed", error=str(exc)[:1000])

