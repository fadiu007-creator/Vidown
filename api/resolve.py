import json
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

ALLOWED_HOSTS = {
    "youtube.com", "youtu.be", "youtube-nocookie.com",
    "tiktok.com", "instagram.com", "facebook.com", "fb.watch",
    "x.com", "twitter.com", "reddit.com", "redd.it",
    "pinterest.com", "pin.it", "vimeo.com", "dailymotion.com",
    "twitch.tv", "streamable.com",
}
RATE_WINDOW_SECONDS = 60
RATE_MAX_REQUESTS = 8
_request_counts = {}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def host_allowed(hostname):
    host = (hostname or "").lower().removeprefix("www.")
    return any(host == domain or host.endswith("." + domain) for domain in ALLOWED_HOSTS)


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self._send_json(405, {"ok": False, "error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST to resolve a public media URL."}})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 1 or length > 16384:
            self._send_json(400, {"ok": False, "error": {"code": "INVALID_BODY", "message": "Send a small JSON body with a video URL."}})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": {"code": "INVALID_JSON", "message": "The request body must be valid JSON."}})
            return

        raw_url = body.get("url", "").strip() if isinstance(body.get("url"), str) else ""
        if not raw_url or len(raw_url) > 4096:
            self._send_json(400, {"ok": False, "error": {"code": "INVALID_URL", "message": "Enter a valid public video URL."}})
            return
        parsed = urlparse(raw_url)
        if parsed.scheme not in ("http", "https") or not host_allowed(parsed.hostname):
            self._send_json(400, {"ok": False, "error": {"code": "URL_NOT_ALLOWED", "message": "This platform is not on Vidown’s supported public-site list."}})
            return

        client_ip = (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()
        now = time.time()
        recent = [stamp for stamp in _request_counts.get(client_ip, []) if now - stamp < RATE_WINDOW_SECONDS]
        if len(recent) >= RATE_MAX_REQUESTS:
            self._send_json(429, {"ok": False, "error": {"code": "RATE_LIMITED", "message": "Too many requests. Wait one minute and try again."}})
            return
        recent.append(now)
        _request_counts[client_ip] = recent
        if len(_request_counts) > 5000:
            _request_counts.clear()

        mode = "audio" if body.get("mode") == "audio" else "video"
        quality = str(body.get("quality", "720"))
        quality = quality if quality in ("1080", "720", "480", "360") else "0"
        if mode == "audio":
            fmt = "bestaudio/best"
        elif quality == "0":
            fmt = "best[ext=mp4]/best"
        else:
            fmt = f"best[height<={quality}][ext=mp4]/best[height<={quality}]/best"

        command = [
            sys.executable, "-m", "yt_dlp",
            "--dump-single-json", "--no-warnings", "--no-playlist",
            "--socket-timeout", "15", "--retries", "1", "--extractor-retries", "1",
            "--format", fmt, "--", parsed.geturl(),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=40, check=False)
            # Some extractors expose formats differently or temporarily reject quality filters.
            # Retry once with the extractor's default progressive format before returning an error.
            if result.returncode != 0 and mode == "video" and fmt != "best":
                fallback_command = [
                    sys.executable, "-m", "yt_dlp",
                    "--dump-single-json", "--no-warnings", "--no-playlist",
                    "--socket-timeout", "15", "--retries", "1", "--extractor-retries", "1",
                    "--format", "best", "--", parsed.geturl(),
                ]
                result = subprocess.run(fallback_command, capture_output=True, text=True, timeout=40, check=False)
            if result.returncode != 0:
                detail = re.sub(r"\s+", " ", result.stderr or result.stdout or "")[:500].lower()
                if "unsupported url" in detail:
                    message, code, status = "This URL type is not supported by the current resolver.", "UNSUPPORTED_URL", 422
                elif any(word in detail for word in ("private", "login", "sign in", "members-only")):
                    message, code, status = "This media appears private or requires a login. Vidown only supports public links.", "PRIVATE_MEDIA", 422
                elif "429" in detail or "too many requests" in detail:
                    message, code, status = "The source is temporarily rate-limiting downloads. Wait and try again.", "SOURCE_RATE_LIMITED", 429
                else:
                    message, code, status = "Could not resolve this link. The platform may be blocking automated requests or may have changed its format.", "RESOLVER_ERROR", 502
                self._send_json(status, {"ok": False, "error": {"code": code, "message": message}})
                return

            info = json.loads(result.stdout)
            media_url = info.get("url")
            if not media_url and info.get("requested_formats"):
                # Prefer a progressive format so the browser can download it without server-side merging.
                for item in info["requested_formats"]:
                    if item.get("url") and item.get("acodec") not in (None, "none") and item.get("vcodec") not in (None, "none"):
                        media_url = item["url"]
                        info["ext"] = item.get("ext", info.get("ext"))
                        break
            if not media_url:
                self._send_json(422, {"ok": False, "error": {"code": "NO_COMPATIBLE_FORMAT", "message": "No single-file download was available for this link. Try another quality or link."}})
                return

            title = info.get("title") or "Vidown media"
            filename = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title)[:150]
            self._send_json(200, {
                "ok": True,
                "title": title,
                "filename": filename,
                "mode": mode,
                "quality": info.get("format") or (f"{info.get('height')}p" if info.get("height") else (info.get("ext") or "Best available")),
                "ext": info.get("ext") or ("m4a" if mode == "audio" else "mp4"),
                "downloadUrl": media_url,
                "duration": info.get("duration"),
                "expiresQuickly": True,
                "notice": "Source download links can expire. Resolve the post again if needed."
            })
        except subprocess.TimeoutExpired:
            self._send_json(504, {"ok": False, "error": {"code": "RESOLVER_TIMEOUT", "message": "The source took too long to respond. Try again."}})
        except Exception:
            self._send_json(502, {"ok": False, "error": {"code": "RESOLVER_ERROR", "message": "The resolver could not process this link. Try again later."}})

    def log_message(self, format, *args):
        # Keep user URLs out of routine logs.
        return
