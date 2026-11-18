import json
from pathlib import Path
from threading import Lock

from .database import ROOT, DATA

SETTINGS_PATH = DATA / "settings.json"
LOCK = Lock()
DEFAULTS = {
    "gemini_model": "gemini-3.8-flash",
    "whisper_model": "small",
    "auto_broll": False,
    "pexels_api_key": "",
    "gemini_api_key": "",
}


def load_settings() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        with LOCK, SETTINGS_PATH.open("r", encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, json.JSONDecodeError):
        saved = {}
    return {**DEFAULTS, **saved}


def save_settings(updates: dict) -> dict:
    current = load_settings()
    for key in DEFAULTS:
        if key in updates:
            current[key] = updates[key]
    with LOCK, SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return public_settings(current)


def public_settings(value: dict | None = None) -> dict:
    current = value or load_settings()
    return {
        "gemini_model": current["gemini_model"],
        "whisper_model": current["whisper_model"],
        "auto_broll": bool(current["auto_broll"]),
        "gemini_configured": bool(current["gemini_api_key"]),
        "pexels_configured": bool(current["pexels_api_key"]),
    }

