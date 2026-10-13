# Vidown

A responsive, mobile-friendly video/audio downloader interface for public social-media links.

## Current status

The GitHub Pages frontend is a static website. It submits URLs to the Cobalt API at `https://api.cobalt.tools/` to resolve downloadable media. The public API may change, rate-limit requests, block browser-origin requests, or require a separately configured instance. Therefore this frontend does **not** guarantee every platform will work at all times.

## Run locally

Open `index.html` in a browser, or serve this directory with any static web server.

## GitHub Pages

In the repository, open **Settings → Pages**, choose **Deploy from a branch**, select **main** and **/(root)**, then save. Once GitHub finishes publishing, the site should be available at:

https://fadiu007-creator.github.io/Vidown/

## Platform support

The backend service determines which sites and media types are supported. The interface includes YouTube, TikTok, Instagram, Facebook, X/Twitter, Reddit, Pinterest and other public links. Support is not guaranteed for private/restricted content, login-only posts, DRM-protected streams, or removed media.

## Production recommendation

For a reliable public service, run a backend you control and configure a supported media resolver there. Do not put API secrets in browser JavaScript. Add rate limits, request-size limits, abuse protection, timeouts, and safe URL validation; do not expose arbitrary server-side URL fetching that could enable SSRF.

## Responsible use

Only save media you own or have permission to download. Respect copyright, privacy, and the terms of the relevant platforms. Vidown does not intentionally bypass private posts, paywalls, or DRM.
