# ClipForge AI

Free local-first video clipping software for turning long videos into short, editable social clips. ClipForge transcribes speech on your computer, uses Gemini to help identify moments, and exports MP4 clips with FFmpeg. Optional Pexels B-roll adds stock-video cutaways.

## Features

- Local speech-to-text with faster-whisper; video and audio files stay on your computer.
- Optional Gemini analysis for clip suggestions, titles, captions, and B-roll search prompts. Only transcript excerpts are sent to Gemini.
- Automatic B-roll suggestions and manual Pexels video search, placement, and removal.
- Trim clips, edit transcripts and titles, choose subtitle styles, and adjust video layout, ratio, resolution, playback speed, and audio volume.
- Export vertical, square, or landscape H.264 MP4 clips, individually or in batches.
- No subscription or payment setup. Exports do not have a watermark.

## Quick start on Windows

### 1. Install prerequisites

- Install [Python 3.11 or newer](https://www.python.org/downloads/windows/). During setup, enable **Add Python to PATH**.
- Install FFmpeg and make sure both `ffmpeg` and `ffprobe` are available in PowerShell. One option is [gyan.dev FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/); install a release build and add its `bin` folder to PATH.

### 2. Get ClipForge

Download and unzip this repository, or clone it:

```powershell
git clone https://github.com/ryangeethsara/clipforge-ai.git
cd clipforge-ai
```

### 3. Install and run

Double-click `install.bat`, then double-click `start.bat`. ClipForge opens at [http://127.0.0.1:8765](http://127.0.0.1:8765). Add a video, choose a local Whisper model, and select **Find my clips**.

The first transcription downloads the selected speech model. **Base** is quick on CPU; **Small** is a balanced default; larger models can improve accuracy but need more memory and time. FFmpeg renders locally.

## Optional Gemini setup

1. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey).
2. In ClipForge, open **Settings → Gemini clip analysis**, paste the key, and save.

Gemini receives candidate transcript excerpts and timestamps, not the source video. If Gemini is not configured or a request fails, ClipForge uses its local transcript-based ranking. Gemini API usage has its own quotas and pricing; check Google's current [Gemini API documentation](https://ai.google.dev/gemini-api/docs) before use.

## Optional Pexels B-roll setup

Pexels currently says new API key issuance is paused. Check the [Pexels API page](https://www.pexels.com/api/) for its current status. If you already have a key, open **Settings → Pexels B-roll**, paste the key, and save. Add cutaways manually in a clip's **B-roll** editor, or turn on automatic B-roll suggestions when analyzing a video.

ClipForge overlays cutaway video while retaining the original audio, and keeps Pexels and contributor links with each asset. Review the current [Pexels API documentation](https://www.pexels.com/api/documentation/) and [Pexels license](https://www.pexels.com/license/) for attribution and usage terms.

## Data, privacy, and costs

- The app listens only on `127.0.0.1` by default. Do not expose it publicly; it is a single-user local tool and does not include user accounts.
- Uploaded source videos, project data, downloaded B-roll, and exports are stored in this project folder under `projects/`, `data/`, and `exports/`.
- Gemini and Pexels keys are stored locally in `data/settings.json` and are not returned by the settings API. Protect your Windows account and disk.
- Speech recognition and video rendering run locally. Gemini and Pexels features need internet access and their own API keys. Gemini usage may be billable.

## Troubleshooting

- **FFmpeg not found:** Add the FFmpeg `bin` directory to PATH, then close and reopen ClipForge.
- **First transcription takes a while:** Whisper is downloading the chosen model. Try Base for a faster first run.
- **No clip moments found:** Try a shorter duration range or a video with clearer speech.
- **Gemini request failed:** Check the API key, selected model name, network connection, and Google API quota. Local ranking remains available.
- **Pexels search failed:** Check the API key and internet connection.
- **Export failed:** Check the displayed error, free disk space, and that the source video still exists in its project folder.

## Development

From the repository folder, create and activate a virtual environment, then install the requirements:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Start the service:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

Run the integration checks:

```powershell
python -m unittest discover -s tests -v
```

## License

This repository currently has no software license. A public GitHub page makes the source visible, but reuse and redistribution rights are not granted until a license is chosen and added.
