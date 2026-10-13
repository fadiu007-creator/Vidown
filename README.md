# Vidown

A responsive video/audio downloader for public media links.

## Architecture

- **Frontend:** static `index.html`, published with GitHub Pages.
- **Backend:** Python serverless functions on Vercel.
- **Resolver:** `yt-dlp`, installed from `requirements.txt`.
- **API health:** `/api/health`
- **Resolve endpoint:** `POST /api/resolve` with JSON `{"url":"https://…","mode":"video","quality":"720"}`.

The resolver validates supported public domains, limits request size and applies a basic per-instance rate limit. It returns a direct source URL rather than storing or proxying the whole media file, so links can expire and the browser downloads directly from the source. Video formats are selected as single-file/progressive formats where available; the server falls back to the source's default format if a requested quality filter is unavailable.

## Deploy

### Frontend (GitHub Pages)

In the repository, open **Settings → Pages**, select **Deploy from a branch**, choose `main` and `/(root)`, then save. The frontend URL is:

https://fadiu007-creator.github.io/Vidown/

### Backend (Vercel)

The Vercel project `vidown` is connected to this repository's `main` branch and deploys on commits. The frontend calls the project's public `/api/resolve` endpoint. The health endpoint is available at:

https://vidown-three.vercel.app/api/health

## Supported sources and limitations

The current allowlist includes YouTube, TikTok, Instagram, Facebook, X/Twitter, Reddit, Pinterest, Vimeo, Dailymotion, Twitch and Streamable. A domain being listed does not guarantee every post or format will work. Sites may change their playback systems, block automated requests, require login, or provide only separate video/audio streams. Private posts, login-only media, DRM-protected streams, removed videos, and paywalled content are not supported. Audio is returned in a source-available audio format; the server does not transcode files to MP3.

Direct media URLs can expire. If a download link stops working, resolve the original post again.

## Responsible use

Only download content you own or have permission to save. Respect copyright, privacy, and the terms of the relevant platforms. Vidown does not intentionally bypass private posts, paywalls, or DRM.
