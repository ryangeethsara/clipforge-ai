# ClipForge AI v1.2.0

ClipForge is a free, local video clipping app for turning long videos into short social clips. Paste a public YouTube link or import a video file. Gemini creates timestamped transcripts for both source types; ClipForge uses those timestamps to make editable clips and renders the exports on your computer with FFmpeg. Optional Pexels B-roll adds stock-video cutaways.

ClipForge has no subscription or payment plan. Gemini API quotas and pricing depend on your Google account, model, and current Google policies, so check those before use.

## Features

- Paste a public YouTube video URL or import a video file from your computer.
- Transcribe both source types with Gemini cloud video understanding.
- Suggest clip moments, titles, captions, and B-roll search phrases with Gemini.
- Search and add Pexels B-roll manually or request automatic cutaways.
- Edit clip timing, transcript, title, subtitles, layout, aspect ratio, resolution, playback speed, and audio volume.
- Export vertical, square, or landscape H.264 MP4 clips, individually or in batches.
- No watermark on exports.
- Keep source videos, project data, editing, and exports on your computer; cloud transcription requires sending video content to Gemini.

## Setup on Windows

### 1. Install prerequisites

- Install [Python 3.11 or newer](https://www.python.org/downloads/windows/). During setup, enable **Add Python to PATH**.
- Install FFmpeg and make sure `ffmpeg` and `ffprobe` are available in PowerShell. One option is [gyan.dev FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/); install a release build and add its `bin` folder to PATH.

### 2. Download ClipForge

Download and unzip this repository, or clone it:

```powershell
git clone https://github.com/ryangeethsara/clipforge-ai.git
cd clipforge-ai
```

### 3. Install and launch

Double-click `install.bat`, then `start.bat`. The app opens at [http://127.0.0.1:8765](http://127.0.0.1:8765). The installer adds the Python packages, including the Gemini SDK and yt-dlp for YouTube source import.

### 4. Add a Gemini API key

1. Create an API key in [Google AI Studio](https://aistudio.google.com/apikey).
2. In ClipForge, open **Settings → Gemini clip analysis**.
3. Paste the key and select **Save settings**.

The key is saved locally in `data/settings.json`. Keep it private. A Gemini key is required to analyze either a YouTube link or an uploaded file.

## Import and create clips

On the Dashboard or **My projects** page, choose one of these import options:

### Paste a YouTube link

1. Paste a public, single-video URL into **YouTube video URL**.
2. Confirm that you own the video or have permission to download and edit it.
3. Select **Import link**. ClipForge downloads the source locally for preview and editing.
4. Choose the clip length and count, then select **Find my clips**.

Gemini reads the public YouTube video URL and returns an AI-generated transcript with timestamps. ClipForge matches those timestamps against the locally downloaded video. Review the transcript and clip boundaries before export because generated words and timestamps may be imperfect.

**Only import videos you own or are authorized to download and edit.** YouTube’s [terms](https://www.youtube.com/t/terms) limit downloading and modifying content except where the service permits it, you have permission from the rights holders, or applicable law allows it. ClipForge only accepts public video links; it does not sign into YouTube or import private videos or playlists.

### Import a video file

Select **Browse files** or **Add videos**, or drop a video into the upload area. Supported formats are MP4, MOV, MKV, AVI, and WEBM. Gemini’s documented Files API file limit is 2 GB per file. The source stays in your project folder for editing and export.

For transcription, ClipForge uploads the video to Gemini’s Files API, requests a timestamped transcript, then attempts to delete the temporary Gemini file. Google says Files API uploads are automatically deleted after 48 hours; see the [Files API documentation](https://ai.google.dev/gemini-api/docs/files). Cloud transcription will not work without an internet connection or an available Gemini quota.

## Optional Pexels B-roll

If you have a Pexels API key, open **Settings → Pexels B-roll** and save it. Add cutaways manually in a clip’s **B-roll** editor, or turn on automatic B-roll suggestions during analysis. Pexels may change key issuance and API access; check the [Pexels API page](https://www.pexels.com/api/) for current status.

ClipForge overlays cutaway video while retaining original audio and keeps Pexels and contributor links with each asset. Review the current [Pexels API documentation](https://www.pexels.com/api/documentation/) and [Pexels license](https://www.pexels.com/license/) for attribution and usage terms.

## Files, privacy, and costs

- ClipForge listens on `127.0.0.1` by default. Do not expose it publicly; this is a single-user local tool without user accounts.
- Uploaded and downloaded sources, project data, downloaded B-roll, and exports are stored under `projects/`, `data/`, and `exports/` in this folder.
- Gemini and Pexels API keys are stored locally in `data/settings.json` and are not returned by the settings API. Protect your Windows account and disk.
- For YouTube imports, Gemini receives the public video URL. For file imports, Gemini receives the uploaded video. The transcript is also sent to Gemini for clip ranking and title/caption suggestions. Editing and rendering run locally.
- Gemini API quotas, model access, and pricing can change. Check Google’s current [pricing](https://ai.google.dev/gemini-api/docs/pricing) and [terms](https://ai.google.dev/gemini-api/terms) before using it. Google’s terms say data submitted through the unpaid tier may be used to improve Google products. Avoid sending sensitive videos or material unless you have reviewed the current terms and are comfortable with them.
- The YouTube URL feature and Gemini API free quotas are subject to model availability, usage limits, and policy changes. “Free” is not a guaranteed unlimited service.
- The source video remains on your computer after import. Do not close the app while a source is downloading or a clip is rendering.

## Troubleshooting

- **FFmpeg not found:** Add FFmpeg’s `bin` directory to PATH, then close and reopen ClipForge.
- **YouTube link is not accepted:** Use a public, single-video URL from `youtube.com` or `youtu.be`; private links and playlists are not supported.
- **Download failed:** Check internet access, confirm the video is public, verify FFmpeg is installed, and confirm you are permitted to download it.
- **Gemini transcription failed:** Check the API key, selected model, internet connection, upload size, and current Google API quota. Some videos or models may not be supported.
- **No clip moments found:** Try a shorter clip duration or a video with clearer speech.
- **Pexels search failed:** Check the API key and internet connection.
- **Export failed:** Check the displayed error, available disk space, and that the source video still exists in its project folder.

## Development

From the repository folder, create and activate a virtual environment, then install the development requirements:

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
