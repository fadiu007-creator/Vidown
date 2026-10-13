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
        command = [
            sys.executable, "-m", "yt_dlp",
            "--dump-single-json", "--skip-download", "--no-warnings", "--no-playlist",
            "--socket-timeout", "15", "--retries", "1", "--extractor-retries", "1",
            "--", parsed.geturl(),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=50, check=False)
            if result.returncode != 0:
                detail = re.sub(r"\\s+", " ", result.stderr or result.stdout or "")[:500].lower()
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
            formats = [item for item in (info.get("formats") or []) if item.get("url")]
            if mode == "audio":
                candidates = [item for item in formats if item.get("acodec") not in (None, "none") and item.get("vcodec") in (None, "none")]
                candidates.sort(key=lambda item: float(item.get("abr") or item.get("tbr") or 0), reverse=True)
            else:
                # Prefer progressive formats that already contain both video and audio.
                candidates = [item for item in formats if item.get("vcodec") not in (None, "none") and item.get("acodec") not in (None, "none")]
                candidates.sort(key=lambda item: (int(item.get("height") or 0), float(item.get("tbr") or 0)), reverse=True)
                if quality != "0":
                    within_quality = [item for item in candidates if not item.get("height") or int(item.get("height") or 0) <= int(quality)]
                    if within_quality:
                        candidates = within_quality

            chosen = candidates[0] if candidates else None
            separate_audio = None
            separate_streams = False
            if mode == "video" and not chosen:
                video_candidates = [item for item in formats if item.get("url") and item.get("vcodec") not in (None, "none")]
                audio_candidates = [item for item in formats if item.get("url") and item.get("acodec") not in (None, "none") and item.get("vcodec") in (None, "none")]
                video_candidates.sort(key=lambda item: (int(item.get("height") or 0), float(item.get("tbr") or 0)), reverse=True)
                if quality != "0":
                    within_quality = [item for item in video_candidates if not item.get("height") or int(item.get("height") or 0) <= int(quality)]
                    if within_quality:
                        video_candidates = within_quality
                audio_candidates.sort(key=lambda item: float(item.get("abr") or item.get("tbr") or 0), reverse=True)
                chosen = video_candidates[0] if video_candidates else None
                separate_audio = audio_candidates[0] if audio_candidates else None
                separate_streams = bool(chosen and separate_audio)
            if not chosen or not chosen.get("url"):
                self._send_json(422, {"ok": False, "error": {"code": "NO_COMPATIBLE_FORMAT", "message": "No downloadable media was found for this link. Try another public post."}})
                return

            title = info.get("title") or "Vidown media"
            filename = re.sub(r'[\\\\/:*?"<>|\\x00-\\x1f]', "_", title)[:150]
            self._send_json(200, {
                "ok": True,
                "title": title,
                "filename": filename,
                "mode": mode,
                "quality": (f"{chosen.get('height')}p" if chosen.get("height") else (f"{int(chosen.get('abr') or 0)} kbps" if mode == "audio" and chosen.get("abr") else (chosen.get("format_note") or chosen.get("ext") or "Best available"))),
                "ext": chosen.get("ext") or ("m4a" if mode == "audio" else "mp4"),
                "downloadUrl": chosen["url"],
                "audioUrl": separate_audio.get("url") if separate_audio else None,
                "audioExt": separate_audio.get("ext") if separate_audio else None,
                "separateStreams": separate_streams,
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
