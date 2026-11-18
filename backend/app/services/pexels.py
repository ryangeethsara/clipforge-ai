import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def search_videos(query: str, api_key: str, orientation: str = "portrait", per_page: int = 8) -> list[dict]:
    if not api_key:
        raise RuntimeError("Add a Pexels API key in Settings to search stock footage.")
    params = urllib.parse.urlencode({"query": query[:120], "orientation": orientation, "per_page": max(1, min(20, per_page))})
    request = urllib.request.Request(f"https://api.pexels.com/v1/videos/search?{params}", headers={"Authorization": api_key})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Pexels API error ({exc.code}): {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Pexels request failed: {exc}") from exc

    results = []
    for video in data.get("videos", []):
        files = [f for f in video.get("video_files", []) if f.get("file_type", "").lower().startswith("video/mp4") and f.get("link")]
        if not files:
            continue
        files.sort(key=lambda f: (f.get("quality") == "hd", min(f.get("width", 0), 1920)), reverse=True)
        file = files[0]
        results.append({
            "id": video.get("id"), "duration": video.get("duration", 0),
            "width": file.get("width", 0), "height": file.get("height", 0), "download_url": file["link"],
            "pexels_url": video.get("url", "https://www.pexels.com"),
            "photographer": video.get("user", {}).get("name", "Pexels contributor"),
            "photographer_url": video.get("user", {}).get("url", "https://www.pexels.com"),
            "thumbnail": video.get("image", ""),
        })
    return results


def download_video(video: dict, directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"pexels_{uuid.uuid4().hex[:12]}.mp4"
    request = urllib.request.Request(video["download_url"], headers={"User-Agent": "ClipForgeAI/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response, target.open("wb") as output:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 250 * 1024 * 1024:
                    raise RuntimeError("The Pexels asset exceeded the 250 MB safety limit.")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return str(target)

