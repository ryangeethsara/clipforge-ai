import json
import re
import subprocess
import threading
import urllib.error
import urllib.request
from typing import Any

import numpy as np


def transcribe(video_path: str, model_size: str, cancel_event: threading.Event | None = None) -> tuple[list[dict[str, Any]], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Local speech recognition is not installed. Run install.bat, then retry.") from exc

    model_size = model_size if model_size in {"tiny", "base", "small", "medium", "large-v3"} else "small"
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    result: list[dict[str, Any]] = []
    language = "unknown"
    sample_rate = 16_000
    chunk_seconds = 300
    chunk_bytes = sample_rate * chunk_seconds * 4
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video_path, "-vn", "-ac", "1", "-ar",
               str(sample_rate), "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg was not found. Install FFmpeg and make sure it is available on PATH.") from exc
    offset = 0.0
    try:
        assert process.stdout is not None
        while True:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Processing cancelled by user.")
            raw = process.stdout.read(chunk_bytes)
            if not raw:
                break
            # Stream short windows so a long source never becomes a large in-memory audio array.
            usable = len(raw) - (len(raw) % 4)
            audio = np.frombuffer(raw[:usable], dtype="<f4")
            if not audio.size:
                continue
            segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=True)
            language = getattr(info, "language", language)
            for seg in segments:
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("Processing cancelled by user.")
                words = []
                for word in getattr(seg, "words", None) or []:
                    words.append({"start": round(offset + float(word.start), 3),
                                  "end": round(offset + float(word.end), 3), "word": word.word})
                result.append({"start": round(offset + float(seg.start), 3),
                               "end": round(offset + float(seg.end), 3), "text": seg.text.strip(), "words": words})
            offset += audio.size / sample_rate
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Processing cancelled by user.")
        if process.wait(timeout=30) != 0:
            raise RuntimeError("FFmpeg could not decode the source audio for transcription.")
    except Exception:
        if process.poll() is None:
            process.kill()
        raise
    finally:
        if process.stdout:
            process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()
    return result, language


def _sentences(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for segment in segments:
        text = segment["text"].strip()
        if not text:
            continue
        pieces = re.split(r"(?<=[.!?])\s+", text)
        if len(pieces) == 1:
            units.append({"start": segment["start"], "end": segment["end"], "text": text})
            continue
        words = segment.get("words") or []
        cursor = 0
        for piece_index, piece in enumerate(pieces):
            piece = piece.strip()
            if not piece:
                continue
            count = max(1, len(piece.split()))
            selected = words[cursor:cursor + count]
            if selected:
                start, end = selected[0]["start"], selected[-1]["end"]
                cursor += count
            else:
                start = segment["start"] + (segment["end"] - segment["start"]) * (piece_index / max(1, len(pieces)))
                end = min(segment["end"], start + (segment["end"] - segment["start"]) / max(1, len(pieces)))
            units.append({"start": start, "end": end, "text": piece})
    return units


def heuristic_score(text: str, duration: float) -> tuple[int, int, str]:
    lowered = text.lower()
    hook_terms = ("why", "how", "secret", "mistake", "nobody", "never", "imagine", "truth", "because", "the problem")
    insight_terms = ("because", "means", "learn", "realize", "important", "example", "first", "finally", "instead", "actually")
    emotion_terms = ("love", "hate", "amazing", "terrible", "crazy", "funny", "scared", "surprised", "unbelievable")
    hook = 30 + 10 * ("?" in text or "!" in text) + 5 * any(term in lowered for term in hook_terms)
    density = min(100, 35 + 6 * len(set(re.findall(r"\b\w{6,}\b", lowered))) + 5 * any(term in lowered for term in insight_terms))
    emotion = 30 + 10 * min(4, sum(term in lowered for term in emotion_terms))
    completeness = 55 + (12 if text.rstrip().endswith((".", "?", "!")) else 0) + (10 if duration >= 10 else 0)
    score = round((hook + density + emotion + completeness) / 4)
    reason = "A complete thought with clear context and useful or emotionally engaging language."
    if any(term in lowered for term in hook_terms):
        reason = "Opens with a curiosity or contrast cue and reaches a complete point."
    return min(100, score), min(100, int(hook)), reason


def make_candidates(segments: list[dict[str, Any]], minimum: int, maximum: int, count: int) -> list[dict[str, Any]]:
    units = _sentences(segments)
    candidates: list[dict[str, Any]] = []
    target = (minimum + maximum) / 2
    for i, unit in enumerate(units):
        start = unit["start"]
        pieces: list[str] = []
        end = start
        for item in units[i:]:
            if item["start"] - start > maximum:
                break
            pieces.append(item["text"])
            end = item["end"]
            duration = end - start
            if duration >= minimum and duration <= maximum:
                transcript = " ".join(pieces).strip()
                score, hook, reason = heuristic_score(transcript, duration)
                candidates.append({"start": round(start, 2), "end": round(end, 2), "transcript": transcript,
                                   "score": score, "hook_score": hook, "reason": reason,
                                   "_distance": abs(duration - target)})
    candidates.sort(key=lambda c: (c["score"] + max(0, 20 - c["_distance"])) , reverse=True)
    selected: list[dict[str, Any]] = []
    for item in candidates:
        if any(abs(item["start"] - other["start"]) < max(4, minimum * .55) for other in selected):
            continue
        item.pop("_distance", None)
        selected.append(item)
        if len(selected) >= max(count, count * 3):
            break
    return selected[:max(1, count * 3)]


def gemini_enrich(candidates: list[dict[str, Any]], api_key: str, model: str) -> list[dict[str, Any]]:
    if not api_key or not candidates:
        return candidates
    compact = [{"id": i, "start": c["start"], "end": c["end"], "transcript": c["transcript"]}
               for i, c in enumerate(candidates[:45])]
    prompt = """You are an editor selecting short, self-contained video clips from transcript excerpts. Rank the clips as editorial promise, not a prediction of virality. Use only what the transcript says; never invent claims or quotes. Return JSON with a `clips` array. For each item include: id (same integer), score (0-100), hook_score (0-100), title (short and faithful), titles (exactly 3 concise alternatives), description, caption, hashtags (3-6 strings), hook (opening line idea based only on transcript), reason (why it works and whether it is complete), broll_query (short English search phrase for a relevant generic visual cutaway, or empty string if a cutaway would distract), and broll_reason. Favor strong openings, specificity, clear context, coherent ending. Avoid clips that start or end mid-thought. Excerpts:\n""" + json.dumps(compact, ensure_ascii=False)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.25},
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        enriched = {int(x["id"]): x for x in parsed.get("clips", []) if "id" in x}
        for i, candidate in enumerate(candidates):
            result = enriched.get(i)
            if not result:
                continue
            candidate.update({
                "score": max(0, min(100, int(result.get("score", candidate["score"])))),
                "hook_score": max(0, min(100, int(result.get("hook_score", candidate["hook_score"])))),
                "title": str(result.get("title", ""))[:140],
                "titles": [str(s)[:140] for s in result.get("titles", [])[:3]],
                "description": str(result.get("description", ""))[:500],
                "caption": str(result.get("caption", ""))[:700],
                "hashtags": [str(s)[:40] for s in result.get("hashtags", [])[:8]],
                "hook": str(result.get("hook", ""))[:240],
                "reason": str(result.get("reason", candidate["reason"]))[:500],
                "broll_query": str(result.get("broll_query", ""))[:120],
                "broll_reason": str(result.get("broll_reason", ""))[:300],
            })
        return candidates
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Gemini API error ({exc.code}): {details}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc
    except (KeyError, IndexError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Gemini returned an unreadable response: {exc}") from exc

