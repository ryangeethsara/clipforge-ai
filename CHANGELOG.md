# Changelog

## v1.2.0

- Removed local speech model setup; both YouTube links and uploaded files now use Gemini cloud transcription.
- Kept the YouTube URL field and computer file picker together on the Dashboard and My projects page.
- Added temporary Gemini Files API uploads for local video files and best-effort deletion after transcription.
- Set the supported local file upload limit to 2 GB per file.
- Updated settings, progress messages, setup, privacy, and troubleshooting guidance for cloud transcription.

## v1.1.2

- Put separate **Paste YouTube link** and **Import video file** buttons at the top of the Dashboard and My projects page.
- Moved the full import choices above the dashboard statistics so they are visible sooner.

## v1.1.1

- Made YouTube URL import available from both the Dashboard and My projects page.
- Updated the main project buttons to focus the YouTube URL field.

## v1.1.0

- Added YouTube-link import as the primary source workflow.
- Added Gemini timestamped cloud transcription for public YouTube videos.
- Added local yt-dlp download and FFmpeg metadata preparation before clip analysis.
- Kept speech recognition on the computer for imported video files.
- Added an import permission confirmation, download progress, and privacy/setup guidance.
- Kept clean exports with no watermark.

## v1.0.0

- First public release with computer-based speech recognition, optional Gemini clip ranking, Pexels B-roll, clip editing, and local FFmpeg exports.
