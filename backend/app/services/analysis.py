import json
import logging
import mimetypes
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

LOG = logging.getLogger("clipforge.analysis")


def _timestamp_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    pieces = text.split(":")
    try:
        numbers = [float(piece) for piece in pieces]
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {text}") from exc
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    raise ValueError(f"Invalid timestamp: {text}")


def _parse_transcript(text: str, duration: float) -> tuple[list[dict[str, Any]], str]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response must be a JSON object.")
    segments = []
    for item in parsed.get("segments", []):
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("text", "")).strip()
        if not phrase:
            continue
        start = _timestamp_seconds(item["start"])
        end = _timestamp_seconds(item["end"])
        if start < 0 or start >= duration or end <= start:
            continue
        end = min(end, duration)
        segments.append({"start": round(start, 3), "end": round(end, 3), "text": phrase[:4000], "words": []})
    segments.sort(key=lambda segment: (segment["start"], segment["end"]))
    if not segments:
        raise RuntimeError("Gemini returned no timestamped speech. Check the video audio and try another model.")
    return segments, str(parsed.get("language") or "unknown")[:40]


def gemini_transcribe_file(video_path: str, api_key: str, model: str, duration: float,
                           cancel_event: threading.Event | None = None) -> tuple[list[dict[str, Any]], str]:
    if not api_key:
        raise RuntimeError("Add a Gemini API key in Settings to transcribe videos in the cloud.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Gemini file upload support is not installed. Run install.bat, then retry.") from exc

    prompt = f"""Transcribe all clearly audible spoken words in this video. Do not summarize, paraphrase, or invent words. Return JSON with exactly these keys: language (a short language name or code) and segments (an array of objects with numeric start and end values in seconds and the verbatim text). Break the transcript into natural speech phrases, usually one sentence per segment. Use the video's original timeline, start each segment when its words begin, and end it when they finish. The video is about {duration:.1f} seconds long. Keep every timestamp between 0 and {duration:.1f}. Include the full spoken transcript, not just highlights. If there is no intelligible speech, return an empty segments array."""
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=30 * 60 * 1000))
    uploaded = None
    try:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Processing cancelled by user.")
        mime_type = mimetypes.guess_type(video_path)[0] or "video/mp4"
        uploaded = client.files.upload(
            file=video_path,
            config=types.UploadFileConfig(mime_type=mime_type),
        )
        deadline = time.monotonic() + 600
        while True:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Processing cancelled by user.")
            state = getattr(uploaded, "state", None)
            state_name = getattr(state, "name", str(state or "")).upper().rsplit(".", 1)[-1]
            if state_name == "ACTIVE":
                break
            if state_name == "FAILED":
                raise RuntimeError("Gemini could not prepare the uploaded video for transcription.")
            if time.monotonic() >= deadline:
                raise RuntimeError("Gemini took too long to prepare the uploaded video. Retry the analysis.")
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Processing cancelled by user.")
        response = client.models.generate_content(
            model=model,
            contents=[uploaded, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.1, max_output_tokens=32768,
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty transcript response. Retry with another model.")
        return _parse_transcript(response.text, duration)
    except RuntimeError:
        raise
    except Exception as exc:
        message = getattr(exc, "message", None) or str(exc)
        raise RuntimeError(f"Gemini file transcription failed: {message[:500]}") from exc
    finally:
        if uploaded is not None and getattr(uploaded, "name", None):
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                LOG.warning("Could not delete temporary Gemini upload %s", uploaded.name, exc_info=True)
        close = getattr(client, "close", None)
        if close:
            try:
                close()
            except Exception:
                LOG.debug("Could not close Gemini client cleanly", exc_info=True)


def gemini_transcribe_youtube(url: str, api_key: str, model: str,
                              duration: float) -> tuple[list[dict[str, Any]], str]:
    if not api_key:
        raise RuntimeError("Add a Gemini API key in Settings to transcribe videos in the cloud.")
    prompt = f"""Transcribe all clearly audible spoken words in this public YouTube video. Do not summarize, paraphrase, or invent words. Return JSON with exactly these keys: language (a short language name or code) and segments (an array of objects with numeric start and end values in seconds and the verbatim text). Break the transcript into natural speech phrases, usually one sentence per segment. Use the video's original timeline, start each segment when its words begin, and end it when they finish. The video is about {duration:.1f} seconds long. Keep every timestamp between 0 and {duration:.1f}. Include the full spoken transcript, not just highlights. If there is no intelligible speech, return an empty segments array."""
    body = {
        "contents": [{"parts": [
            {"file_data": {"file_uri": url}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1,
                             "maxOutputTokens": 32768},
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_transcript(text, duration)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Gemini transcription error ({exc.code}): {details}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Gemini transcription request failed: {exc}") from exc
    except (AttributeError, KeyError, IndexError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Gemini returned an unreadable timestamped transcript: {exc}") from exc


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

