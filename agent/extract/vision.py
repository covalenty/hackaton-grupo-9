"""Vision helpers for Stage 2 — load images locally or fetch from the bridge,
turn them into Anthropic image content blocks.

The Claude messages API accepts two image source types:
  - base64: { type:"base64", media_type:"image/jpeg", data:"<b64>" }
  - url:    { type:"url", url:"https://..." }

For hackathon V1 we use base64 (works with local JPGs we have from WhatsApp
exports and with any private bridge endpoint). URL mode is wired in but
expects a publicly fetchable URL on Anthropic's side, so reserved for later.

Media types supported by Claude vision: image/jpeg, image/png, image/gif, image/webp.
PDF support is separate (different content block type), so document parsing
lands in its own helper.
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Optional

import httpx


# Anthropic vision accepts these. Others get rejected at API time.
ALLOWED_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _guess_media_type(path: Path) -> str:
    guess, _ = mimetypes.guess_type(str(path))
    if guess in ALLOWED_IMAGE_MEDIA_TYPES:
        return guess
    # WhatsApp images are usually JPG; fall back when extension is missing.
    return "image/jpeg"


def image_block_from_path(path: str | Path) -> dict:
    """Read a local file and return an Anthropic image content block (base64)."""
    p = Path(path)
    data = p.read_bytes()
    media_type = _guess_media_type(p)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


def image_block_from_bytes(data: bytes, media_type: str = "image/jpeg") -> dict:
    if media_type not in ALLOWED_IMAGE_MEDIA_TYPES:
        media_type = "image/jpeg"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


def image_block_from_url(
    url: str,
    *,
    bearer_token: Optional[str] = None,
    timeout: float = 15.0,
) -> dict:
    """Fetch the bytes ourselves and embed as base64.

    Why not pass {"type":"url", url} directly? Anthropic would need to fetch
    from THEIR side, which fails for bridge endpoints behind cloudflare-tunnel
    auth. Embedding base64 sidesteps that.
    """
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    media_type = r.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip()
    return image_block_from_bytes(r.content, media_type=media_type)
