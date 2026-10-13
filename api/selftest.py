import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        command = [
            sys.executable, "-m", "yt_dlp",
            "--dump-single-json", "--skip-download", "--no-warnings", "--no-playlist",
            "--socket-timeout", "15", "--retries", "1",
            "--", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=40, check=False)
            if result.returncode != 0:
                payload = {"ok": False, "stage": "yt-dlp-execution", "error": (result.stderr or result.stdout or "yt-dlp failed")[-600:]}
                status = 502
            else:
                info = json.loads(result.stdout)
                payload = {
                    "ok": bool(info.get("formats") or info.get("url")),
                    "stage": "yt-dlp-resolution",
                    "extractor": info.get("extractor_key"),
                    "title": info.get("title"),
                    "formatCount": len(info.get("formats") or []),
                    "hasDirectUrl": bool(info.get("url")),
                }
                status = 200 if payload["ok"] else 502
        except Exception as exc:
            payload = {"ok": False, "stage": "exception", "error": str(exc)[:500]}
            status = 502
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        return
