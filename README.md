# ClipForge AI v1.1.2

Free, local-first video clipping software for turning long videos into short social clips. Start with a public YouTube link or upload a video from your computer. YouTube links use Gemini for cloud transcription; uploaded files use Whisper locally. ClipForge finds clip moments, lets you edit them, and exports MP4s with FFmpeg. Optional Pexels B-roll adds stock-video cutaways.

## Features

- Import a public YouTube video link, then download the authorized source locally for preview and editing.
- Timestamped YouTube transcription with Gemini; local file uploads continue to use faster-whisper on your computer.
- Suggest clip moments, titles, captions, and B-roll search phrases with Gemini when configured.
- Search and add Pexels B-roll manually or request automatic cutaways.
- Edit clip timing, transcript, title, subtitles, layout, aspect ratio, resolution, playback speed, and audio volume.
- Export vertical, square, or landscape H.264 MP4 clips, individually or in batches.
- No subscription or payment setup. Exports do not have a watermark.

## Setup on Windows

### 1. Install prerequisites

- Install [Python 3.11 or newer](https://www.python.org/downloads/windows/). During setup, enable **Add Python to PATH**.
- Install FFmpeg and make sure both `ffmpeg` and `ffprobe` are available in PowerShell. One option is [gyan.dev FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/); install a release build and add its `bin` folder to PATH.

### 2. Download ClipForge

Download and unzip this repository, or clone it:

```powershell
git clone https://github.com/ryangeethsara/clipforge-ai.git
cd clipforge-ai
```

### 3. Install and launch

Double-click `install.bat`, then `start.bat`. The app opens at [http://127.0.0.1:8765](http://127.0.0.1:8765). The installer adds the Python packages, including yt-dlp for YouTube import.

## Import from YouTube

The Dashboard and **My projects** page both show two choices: paste a YouTube link or import a video file from your computer.

1. Create an API key in [Google AI Studio](https://aistudio.google.com/apikey).
2. In ClipForge, open **Settings → Gemini clip analysis**, paste the key, and save it.
3. On the dashboard or **My projects** page, paste a YouTube video URL. Check the permission box and select **Import link**.
4. Wait for the source video to download locally. Choose clip length and count, then select **Find my clips**.

Gemini reads the public YouTube link and returns a transcript with AI-generated timestamps. ClipForge uses those timestamps against the locally downloaded video to suggest edit points. Review and adjust the clip boundaries and subtitles before exporting; generated transcript wording and timing can be imperfect. The Gemini YouTube URL feature is currently documented as a no-charge preview. Google says its pricing and rate limits may change, so check the latest [video-understanding documentation](https://ai.google.dev/gemini-api/docs/video-understanding) and [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing). The same key also supports optional clip ranking and title/caption suggestions.

**Only import videos you own or are authorized to download and edit.** YouTube’s [terms](https://www.youtube.com/t/terms) limit downloading and modifying content except where the service permits it, you have permission from the rights holders, or applicable law allows it. ClipForge only accepts public video links; it does not sign into YouTube or import private videos/playlists.

## Upload from your computer

Choose **Upload a video from this computer** for an MP4, MOV, MKV, AVI, or WEBM source up to 4 GB. These uploads are transcribed locally with faster-whisper and do not need a Gemini key. The first transcription downloads the selected speech model. **Base** is quick on CPU; **Small** is a balanced default; larger models can improve accuracy but need more memory and time.

## Optional Pexels B-roll

Pexels currently says new API key issuance is paused. Check the [Pexels API page](https://www.pexels.com/api/) for its current status. If you already have a key, open **Settings → Pexels B-roll**, paste the key, and save. Add cutaways manually in a clip’s **B-roll** editor, or turn on automatic B-roll suggestions during analysis.

ClipForge overlays cutaway video while retaining original audio and keeps Pexels and contributor links with each asset. Review the current [Pexels API documentation](https://www.pexels.com/api/documentation/) and [Pexels license](https://www.pexels.com/license/) for attribution and usage terms.

## Files, privacy, and costs

- The app listens on `127.0.0.1` by default. Do not expose it publicly; this is a single-user local tool without user accounts.
- Uploaded/downloaded sources, project data, downloaded B-roll, and exports are stored under `projects/`, `data/`, and `exports/` in this folder.
- Gemini and Pexels API keys are stored locally in `data/settings.json` and are not returned by the settings API. Protect your Windows account and disk.
- For YouTube imports, Gemini receives the public video URL and processes the referenced video for transcription; it does not receive the locally downloaded file from ClipForge. Gemini may also receive transcript excerpts for clip ranking. For uploaded files, speech-to-text and video rendering run locally; optional Gemini ranking sends transcript excerpts only.
- Google’s [Gemini API terms](https://ai.google.dev/gemini-api/terms) say content submitted through the unpaid tier may be used to improve Google products. Avoid sending sensitive material and review current terms before use.
- The YouTube URL feature is currently no-charge in preview, subject to rate limits and change. Gemini’s other API features and Pexels are governed by their current quota and pricing policies. Check Google’s current [pricing page](https://ai.google.dev/gemini-api/docs/pricing).
- The source remains on your computer after the initial download. Do not close the app while a source is downloading or a clip is rendering.

## Troubleshooting

- **FFmpeg not found:** Add FFmpeg’s `bin` directory to PATH, then close and reopen ClipForge.
- **YouTube link is not accepted:** Use a public single-video URL from `youtube.com` or `youtu.be`; private links and playlists are not supported.
- **Download failed:** Check internet access, confirm the video is public and available, verify FFmpeg is installed, and confirm it is one you are permitted to download.
- **Gemini transcription failed:** Check the API key, selected model, network connection, and current Google API quota. Some accounts or videos may not be supported by the preview feature.
- **First local transcription takes a while:** Whisper is downloading the selected model. Choose Base for a faster first run.
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
