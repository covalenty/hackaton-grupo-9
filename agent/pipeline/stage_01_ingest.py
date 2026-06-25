"""Stage 1 — ingestão.

Converte payload do webhook do WhatsApp em RawMessage (entrada do Stage 2).
Lida com:
  - JID → source_phone (strip @s.whatsapp.net / @g.us)
  - text=null  →  has_media=True, message_type best-effort
  - timestamp ms → datetime
  - is_from_buyer via lista de aliases (do BuyerProfile)
  - dedup por id do webhook (mantém set in-memory)

Vision-live: when the webhook payload includes media we can fetch, Stage 2
runs vision. Two contracts supported (bridge picks one):

  A) media_url   — top-level URL the bridge promises is fetchable from us
                   (already decrypted by Baileys, exposed via the bridge).
                   Stage 2 fetches via httpx.

  B) media_b64   — top-level base64 string of the decrypted image bytes.
                   Stage 1 writes it to a tmp file and Stage 2 reads locally.

If neither field is set on an image payload we fall back to caption-only
extraction (the imageMessage's caption text is preserved as `body`).
"""
from __future__ import annotations

import base64
import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from ..schemas import MessageType, RawMessage


def _phone_from_jid(jid: Optional[str]) -> Optional[str]:
    """5511999998888@s.whatsapp.net → +5511999998888"""
    if not jid or "@" not in jid:
        return None
    digits = jid.split("@", 1)[0]
    # Group JIDs look like "1234567890-1500000000@g.us" — skip the hyphen part
    if "-" in digits:
        digits = digits.split("-", 1)[0]
    return f"+{digits}" if digits.isdigit() else None


def _is_group(jid: Optional[str]) -> bool:
    return bool(jid) and jid.endswith("@g.us")


def _infer_message_type(payload: dict) -> MessageType:
    """Best-effort: if text is null and raw exists, peek inside to classify."""
    if payload.get("text"):
        return MessageType.TEXT
    raw = payload.get("raw") or {}
    msg = raw.get("message") if isinstance(raw, dict) else None
    if not isinstance(msg, dict):
        return MessageType.IMAGE  # fallback when we know it's not text
    if "imageMessage" in msg or "stickerMessage" in msg:
        return MessageType.IMAGE
    if "audioMessage" in msg or "pttMessage" in msg:
        return MessageType.AUDIO
    if "documentMessage" in msg:
        doc = msg.get("documentMessage") or {}
        name = (doc.get("fileName") or "").lower()
        if name.endswith(".pdf"):
            return MessageType.PDF
        if name.endswith((".xlsx", ".xls", ".csv")):
            return MessageType.EXCEL
    return MessageType.IMAGE


def _make_message_id(webhook_id: Optional[str], received_at: datetime, sender: Optional[str], body: str) -> str:
    """Stable id. Prefer the webhook's id when present; otherwise hash content."""
    if webhook_id:
        return hashlib.sha1(f"wa:{webhook_id}".encode("utf-8")).hexdigest()[:16]
    seed = f"{received_at.isoformat()}|{sender or ''}|{body[:200]}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _extract_image_caption(payload: dict) -> str:
    """Pull the imageMessage caption out of the raw Baileys payload, if any.

    Reps usually attach the caption in the SAME bubble as the image
    ('R$ 9,69' under the tabela.jpg). That caption arrives at
    raw.message.imageMessage.caption — not at payload.text (which is null
    for non-text messages).
    """
    raw = payload.get("raw") or {}
    if not isinstance(raw, dict):
        return ""
    msg = raw.get("message")
    if not isinstance(msg, dict):
        return ""
    img = msg.get("imageMessage")
    if isinstance(img, dict):
        return (img.get("caption") or "").strip()
    doc = msg.get("documentMessage")
    if isinstance(doc, dict):
        return (doc.get("caption") or "").strip()
    return ""


def _media_paths_from_payload(payload: dict) -> tuple[list[str], list[str]]:
    """Return (media_paths, media_urls) extracted from the payload.

    - `media_url`  (top-level)  → URL that Stage 2 can fetch via httpx.
    - `media_b64`  (top-level)  → inline bytes; we materialize to a tmp file
                                  under $TMPDIR/cienty-captura/ so vision can
                                  read it as a local path.
    """
    media_paths: list[str] = []
    media_urls: list[str] = []

    url = payload.get("media_url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        media_urls.append(url)

    b64 = payload.get("media_b64")
    if isinstance(b64, str) and b64:
        try:
            data = base64.b64decode(b64, validate=False)
        except (ValueError, TypeError):
            data = b""
        if data:
            tmp_dir = Path(tempfile.gettempdir()) / "cienty-captura"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            mid = payload.get("id") or hashlib.sha1(data[:64]).hexdigest()[:16]
            ext = ".jpg"  # WhatsApp images are jpeg by default; vision handles png/webp too
            p = tmp_dir / f"{mid}{ext}"
            p.write_bytes(data)
            media_paths.append(str(p))

    return media_paths, media_urls


def to_raw_message(
    payload: dict,
    *,
    buyer_name_aliases: Iterable[str] = (),
    group_name_lookup: Optional[dict] = None,
) -> RawMessage:
    """Convert one webhook payload into a RawMessage ready for Stage 2."""
    aliases = {a.strip().lower() for a in buyer_name_aliases if a}
    text = payload.get("text") or ""
    sender_name = payload.get("name") or None
    jid = payload.get("from")
    ts = payload.get("timestamp") or 0
    received_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts else datetime.now(tz=timezone.utc)

    message_type = _infer_message_type(payload)
    has_media = message_type != MessageType.TEXT

    # When the message is image-like and has no top-level text, use the
    # imageMessage's caption so Stage 2 still has the inline caption to fuse
    # with the visual content.
    if has_media and not text:
        caption = _extract_image_caption(payload)
        if caption:
            text = caption

    media_paths, media_urls = _media_paths_from_payload(payload)

    is_from_buyer = bool(sender_name) and sender_name.strip().lower() in aliases

    group_name = None
    if _is_group(jid) and group_name_lookup:
        group_name = group_name_lookup.get(jid)

    return RawMessage(
        message_id=_make_message_id(payload.get("id"), received_at, sender_name, text),
        source_phone=_phone_from_jid(jid),
        source_name=sender_name,
        group_name=group_name,
        received_at=received_at,
        body=text,
        has_media=has_media,
        message_type=message_type,
        is_from_buyer=is_from_buyer,
        media_paths=media_paths,
        media_urls=media_urls,
    )
