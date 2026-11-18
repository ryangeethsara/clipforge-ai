import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB_PATH = DATA / "clipforge.sqlite3"


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_path TEXT NOT NULL,
            duration REAL NOT NULL DEFAULT 0,
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            file_size INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ready',
            progress INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'Ready to analyze',
            error TEXT,
            transcript_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            settings_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS clips (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            start REAL NOT NULL,
            end REAL NOT NULL,
            transcript TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            titles_json TEXT NOT NULL DEFAULT '[]',
            description TEXT NOT NULL DEFAULT '',
            caption TEXT NOT NULL DEFAULT '',
            hashtags_json TEXT NOT NULL DEFAULT '[]',
            hook TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            score INTEGER NOT NULL DEFAULT 0,
            hook_score INTEGER NOT NULL DEFAULT 0,
            broll_query TEXT NOT NULL DEFAULT '',
            broll_reason TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            subtitle_style TEXT NOT NULL DEFAULT 'modern',
            layout TEXT NOT NULL DEFAULT 'smart',
            aspect_ratio TEXT NOT NULL DEFAULT '9:16',
            output_size TEXT NOT NULL DEFAULT '1080',
            volume REAL NOT NULL DEFAULT 1,
            speed REAL NOT NULL DEFAULT 1,
            subtitle_enabled INTEGER NOT NULL DEFAULT 1,
            exported_path TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS broll (
            id TEXT PRIMARY KEY,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            query TEXT NOT NULL,
            asset_path TEXT NOT NULL,
            pexels_url TEXT NOT NULL,
            photographer TEXT NOT NULL DEFAULT '',
            photographer_url TEXT NOT NULL DEFAULT '',
            start_offset REAL NOT NULL DEFAULT 0,
            duration REAL NOT NULL DEFAULT 3,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS export_jobs (
            id TEXT PRIMARY KEY,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'queued',
            error TEXT,
            output_path TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id);
        CREATE INDEX IF NOT EXISTS idx_broll_clip ON broll(clip_id);
        CREATE INDEX IF NOT EXISTS idx_exports_clip ON export_jobs(clip_id);
        """)
        clip_columns = {row[1] for row in db.execute("PRAGMA table_info(clips)").fetchall()}
        if "active" not in clip_columns:
            db.execute("ALTER TABLE clips ADD COLUMN active INTEGER NOT NULL DEFAULT 1")


def row_json(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def decode_json_fields(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    for field in fields:
        key = f"{field}_json"
        if key in item:
            try:
                item[field] = json.loads(item.pop(key) or "[]")
            except (TypeError, json.JSONDecodeError):
                item[field] = []
    return item

