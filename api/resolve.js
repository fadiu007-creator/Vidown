import youtubedl from "yt-dlp-exec";

const ALLOWED_PROTOCOLS = new Set(["http:", "https:"]);
const PRIVATE_HOSTS = /(^localhost$|^127\.|^10\.|^192\.168\.|^172\.(1[6-9]|2\d|3[01])\.|^169\.254\.|\.local$)/i;
const MAX_URL_LENGTH = 4096;

function sendError(res, status, message, code = "RESOLVE_FAILED") {
  return res.status(status).json({ ok: false, error: { code, message } });
}

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Cache-Control", "no-store");

  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return sendError(res, 405, "Use POST to resolve a public media URL.", "METHOD_NOT_ALLOWED");

  const body = typeof req.body === "string" ? (() => { try { return JSON.parse(req.body); } catch { return {}; } })() : (req.body || {});
  const rawUrl = typeof body.url === "string" ? body.url.trim() : "";
  if (!rawUrl || rawUrl.length > MAX_URL_LENGTH) return sendError(res, 400, "Enter a valid public video URL.", "INVALID_URL");

  let parsed;
  try { parsed = new URL(rawUrl); } catch { return sendError(res, 400, "The URL is not valid.", "INVALID_URL"); }
  if (!ALLOWED_PROTOCOLS.has(parsed.protocol) || PRIVATE_HOSTS.test(parsed.hostname) || !parsed.hostname.includes(".")) {
    return sendError(res, 400, "Only public HTTP/HTTPS links are supported.", "URL_NOT_ALLOWED");
  }

  const mode = body.mode === "audio" ? "audio" : "video";
  const qualityInput = String(body.quality || "720");
  const quality = ["1080", "720", "480", "360"].includes(qualityInput) ? Number(qualityInput) : 0;

  try {
    const args = {
      dumpSingleJson: true,
      noWarnings: true,
      noPlaylist: true,
      noCheckCertificates: false,
      socketTimeout: 15,
      retries: 1,
      extractorRetries: 1,
      format: mode === "audio"
        ? "bestaudio/best"
        : (quality ? `best[height<=${quality}][protocol^=https][ext=mp4]/best[height<=${quality}][protocol^=https]/best[height<=${quality}]/best` : "best[protocol^=https][ext=mp4]/best[protocol^=https]/best"),
    };
    const info = await youtubedl(parsed.href, args, { timeout: 45000 });
    if (!info || !Array.isArray(info.formats) && !info.url) {
      return sendError(res, 422, "No downloadable media was found for this link.", "NO_MEDIA");
    }

    let chosen;
    if (info.url && (!info.formats || !info.formats.length)) {
      chosen = { url: info.url, ext: info.ext || "mp4", format_note: info.format || "Media" };
    } else if (mode === "audio") {
      chosen = (info.formats || []).filter(f => f.url && f.acodec && f.acodec !== "none" && (!f.vcodec || f.vcodec === "none"))
        .sort((a, b) => (b.abr || b.tbr || 0) - (a.abr || a.tbr || 0))[0];
    } else {
      const cap = quality || Infinity;
      chosen = (info.formats || []).filter(f => f.url && f.vcodec && f.vcodec !== "none" && f.acodec && f.acodec !== "none" && (!f.height || f.height <= cap))
        .sort((a, b) => (Number(b.height || 0) - Number(a.height || 0)) || (Number(b.tbr || 0) - Number(a.tbr || 0)))[0];
      if (!chosen) chosen = (info.formats || []).filter(f => f.url && f.vcodec && f.vcodec !== "none" && f.acodec && f.acodec !== "none")
        .sort((a, b) => Number(b.tbr || 0) - Number(a.tbr || 0))[0];
    }

    if (!chosen || !chosen.url) return sendError(res, 422, "This source did not provide a single-file download in the requested mode. Try another quality or link.", "NO_COMPATIBLE_FORMAT");

    return res.status(200).json({
      ok: true,
      title: info.title || "Vidown media",
      filename: (info.title || "vidown-download").replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").slice(0, 150),
      mode,
      quality: chosen.height ? `${chosen.height}p` : (mode === "audio" ? (chosen.ext || "audio").toUpperCase() : "Best available"),
      ext: chosen.ext || (mode === "audio" ? "m4a" : "mp4"),
      downloadUrl: chosen.url,
      duration: info.duration || null,
      expiresQuickly: true,
      notice: "The source may expire this direct link. If it fails, resolve the post again."
    });
  } catch (error) {
    const details = String(error?.stderr || error?.message || "Unknown resolver error").replace(/\s+/g, " ").slice(0, 500);
    const lower = details.toLowerCase();
    if (lower.includes("unsupported url")) return sendError(res, 422, "This platform or URL type is not supported by the current resolver.", "UNSUPPORTED_URL");
    if (lower.includes("private") || lower.includes("login") || lower.includes("sign in") || lower.includes("members-only")) return sendError(res, 422, "This media appears private or requires a login. Vidown only supports public links.", "PRIVATE_MEDIA");
    if (lower.includes("429") || lower.includes("too many requests")) return sendError(res, 429, "The source is temporarily rate-limiting downloads. Wait and try again.", "SOURCE_RATE_LIMITED");
    return sendError(res, 502, "Could not resolve this link. The platform may be blocking automated requests or may have changed its format. Try again later.", "RESOLVER_ERROR");
  }
}
