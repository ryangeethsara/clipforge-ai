import io
import json
import subprocess
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.app.database import connect
from backend.app.main import app
from backend.app.services.analysis import heuristic_score, make_candidates, gemini_enrich
from backend.app.services.pexels import search_videos


class ClipForgeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="clipforge-check-")
        cls.folder = Path(cls.temp.name)
        cls.source = cls.folder / "sample_source.mp4"
        cls.broll = cls.folder / "sample_broll.mp4"
        for output, color in ((cls.source, "0x425571"), (cls.broll, "0x7c457d")):
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d=7",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=7",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output)
            ], check=True, capture_output=True)
        cls.client = TestClient(app)
        cls.client.__enter__()
        cls.project_id = None

    @classmethod
    def tearDownClass(cls):
        if cls.project_id:
            cls.client.delete(f"/api/projects/{cls.project_id}")
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()

    def test_home_upload_edit_render_and_download(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("ClipForge AI", home.text)
        self.assertEqual(self.client.get("/styles.css").status_code, 200)
        self.assertEqual(self.client.get("/app.js").status_code, 200)
        settings = self.client.get("/api/settings").json()
        self.assertIn("gemini_configured", settings)
        self.assertNotIn("gemini_api_key", settings)

        with self.source.open("rb") as video:
            uploaded = self.client.post("/api/upload", files={"files": ("sample_source.mp4", video, "video/mp4")})
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        project = uploaded.json()["projects"][0]
        self.__class__.project_id = project["id"]
        self.assertEqual(project["width"], 640)
        self.assertEqual(project["height"], 360)
        thumbnail = self.client.get(f"/api/projects/{project['id']}/thumbnail")
        self.assertEqual(thumbnail.status_code, 200, thumbnail.text)
        self.assertEqual(thumbnail.headers["content-type"], "image/jpeg")

        clip_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with connect() as db:
            db.execute("""INSERT INTO clips (id,project_id,start,end,transcript,title,score,hook_score,subtitle_style,
                layout,aspect_ratio,output_size,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (clip_id, project["id"], .25, 6.6,
                 "This is a complete sample sentence. Here is a second line for captions.",
                 "Sample clip", 72, 68, "karaoke", "smart", "9:16", "720", now))

        pexels_video = {"id": 13, "duration": 8, "width": 1080, "height": 1920,
            "download_url": "https://videos.pexels.com/sample.mp4", "pexels_url": "https://www.pexels.com/video/13/",
            "photographer": "ClipForge Test", "photographer_url": "https://www.pexels.com/@test",
            "thumbnail": "https://images.pexels.com/sample.jpg"}
        with patch("backend.app.main.load_settings", return_value={"pexels_api_key": "test-key"}), \
             patch("backend.app.main.search_videos", return_value=[pexels_video]):
            search = self.client.get(f"/api/clips/{clip_id}/broll/search", params={"query": "sample cutaway"})
        self.assertEqual(search.status_code, 200, search.text)
        token = search.json()["results"][0]["selection_token"]
        with patch("backend.app.main.download_video", return_value=str(self.broll)):
            added = self.client.post(f"/api/clips/{clip_id}/broll/add", json={"selection_token": token,
                "start_offset": 2.0, "duration": 2.0})
        self.assertEqual(added.status_code, 200, added.text)
        broll_id = added.json()["id"]
        placement = self.client.patch(f"/api/broll/{broll_id}", json={"start_offset": 2.4, "duration": 2.0})
        self.assertEqual(placement.status_code, 200, placement.text)

        edited = self.client.patch(f"/api/clips/{clip_id}", json={"title": "Edited sample", "speed": 1.1,
            "subtitle_style": "karaoke", "layout": "smart", "output_size": "720"})
        self.assertEqual(edited.status_code, 200, edited.text)
        project_detail = self.client.get(f"/api/projects/{project['id']}").json()
        self.assertEqual(project_detail["clips"][0]["title"], "Edited sample")
        self.assertEqual(len(project_detail["clips"][0]["broll"]), 1)

        queued = self.client.post(f"/api/clips/{clip_id}/export")
        self.assertEqual(queued.status_code, 200, queued.text)
        job_id = queued.json()["job_id"]
        job = None
        for _ in range(90):
            time.sleep(.5)
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"complete", "failed"}:
                break
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "complete", job.get("error"))
        output = Path(job["output_path"])
        self.assertTrue(output.is_file())
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)],
                               capture_output=True, text=True, check=True)
        data = json.loads(probe.stdout)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (720, 1280))
        self.assertTrue(any(s["codec_type"] == "audio" for s in data["streams"]))
        self.assertIn("Pexels", data["format"].get("tags", {}).get("comment", ""))
        downloaded = self.client.get(job["download_url"])
        self.assertEqual(downloaded.status_code, 200)
        self.assertGreater(len(downloaded.content), 10_000)

    def test_candidate_scoring_and_duration_boundaries(self):
        score, hook, reason = heuristic_score("Why this works is because the first example proves it.", 18)
        self.assertGreaterEqual(score, 35)
        self.assertGreater(hook, 30)
        self.assertTrue(reason)
        segments = [
            {"start": 0.0, "end": 5.0, "text": "The first idea is simple and useful."},
            {"start": 5.2, "end": 11.0, "text": "The next example shows why it works."},
            {"start": 11.2, "end": 16.5, "text": "And that is the complete explanation."},
        ]
        candidates = make_candidates(segments, 8, 16, 2)
        self.assertTrue(candidates)
        self.assertTrue(all(8 <= c["end"] - c["start"] <= 16 for c in candidates))

    def test_gemini_and_pexels_response_handling(self):
        candidate = {"start": 1, "end": 20, "transcript": "A true statement.", "score": 50,
                     "hook_score": 42, "reason": "complete"}
        gemini_payload = {"candidates": [{"content": {"parts": [{"text": json.dumps({"clips": [{
            "id": 0, "score": 86, "hook_score": 81, "title": "A faithful title",
            "titles": ["A faithful title", "Another title", "A third title"], "broll_query": "hands building a bridge"
        }]})}]}}]}
        with patch("backend.app.services.analysis.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(gemini_payload).encode())) as request:
            enriched = gemini_enrich([candidate.copy()], "test-key", "gemini-3.8-flash")
        self.assertEqual(enriched[0]["score"], 86)
        self.assertEqual(len(enriched[0]["titles"]), 3)
        self.assertEqual(enriched[0]["broll_query"], "hands building a bridge")
        self.assertIn("gemini-3.8-flash:generateContent", request.call_args.args[0].full_url)

        pexels_payload = {"videos": [{"id": 13, "url": "https://www.pexels.com/video/13/", "duration": 8,
            "image": "https://images.pexels.com/example.jpg", "user": {"name": "Contributor", "url": "https://www.pexels.com/@contributor"},
            "video_files": [{"quality": "hd", "file_type": "video/mp4", "width": 1080, "height": 1920,
                             "link": "https://videos.pexels.com/example.mp4"}]}]}
        with patch("backend.app.services.pexels.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(pexels_payload).encode())) as request:
            results = search_videos("city at night", "pexels-test-key")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["photographer"], "Contributor")
        self.assertEqual(request.call_args.args[0].headers["Authorization"], "pexels-test-key")


if __name__ == "__main__":
    unittest.main()
