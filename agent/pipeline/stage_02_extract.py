"""Stage 2 — LLM extraction.

Takes a RawMessage and returns an ExtractionResult (0..N offers/requests) using
Claude with a forced tool-call for guaranteed structured output.

Caches by message_id to avoid re-billing the same message during evals.
Output drops directly into cienty_silver.whatsapp_offers (Wesley's Stage 3 consumes).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from ..extract.prompts import EXTRACT_TOOL, SYSTEM_PROMPT, user_prompt
from ..schemas import ExtractedOffer, ExtractionResult, MessageType, RawMessage

MODEL = os.getenv("CIENTY_EXTRACT_MODEL", "claude-sonnet-4-6")
CACHE_DIR = Path(os.getenv("CIENTY_CACHE_DIR", ".cache/extract"))


def _cache_path(message_id: str) -> Path:
    return CACHE_DIR / f"{message_id}.json"


def _load_cache(message_id: str) -> Optional[dict]:
    p = _cache_path(message_id)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _save_cache(message_id: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(message_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _to_offer(message: RawMessage, raw: dict) -> ExtractedOffer:
    deadline = raw.get("deadline")
    if isinstance(deadline, str):
        try:
            from datetime import datetime as dt
            deadline = dt.fromisoformat(deadline.replace("Z", "+00:00"))
        except ValueError:
            deadline = None
    return ExtractedOffer(
        message_id=message.message_id,
        source_phone=message.source_phone,
        received_at=message.received_at,
        message_type=message.message_type,
        direction=raw.get("direction", "rep_offer"),
        product_name_raw=raw["product_name_raw"],
        price_offered_brl=raw.get("price_offered_brl"),
        bonus_type=raw.get("bonus_type", "none"),
        bonus_qty=raw.get("bonus_qty"),
        bonus_target_product=raw.get("bonus_target_product"),
        min_qty=raw.get("min_qty"),
        max_qty_per_cnpj=raw.get("max_qty_per_cnpj"),
        deadline=deadline,
        requested_qty=raw.get("requested_qty"),
        region=raw.get("region"),
        tier_pricing=raw.get("tier_pricing"),
        source_label=raw.get("source_label"),
        kit_items=raw.get("kit_items"),
        extraction_confidence=float(raw.get("extraction_confidence", 1.0)),
        extraction_notes=raw.get("extraction_notes"),
    )


def _build_user_content(message: RawMessage) -> list[dict] | str:
    """Build the Claude `messages` content payload.

    Returns a string when there's no media (text-only extraction).
    Returns a list of content blocks when images are present (vision).
    """
    text_block = user_prompt(
        message_id=message.message_id,
        sender=message.source_name,
        received_at=message.received_at.isoformat(),
        body=message.body,
        is_from_buyer=message.is_from_buyer,
    )

    if not message.media_paths and not message.media_urls:
        return text_block

    # Lazy import to avoid pulling httpx unless we actually need it
    from ..extract.vision import image_block_from_path, image_block_from_url

    blocks: list[dict] = []
    for p in message.media_paths:
        try:
            blocks.append(image_block_from_path(p))
        except Exception as e:  # noqa: BLE001
            print(f"[stage-02] failed to load image {p!r}: {e!r}")
    for url in message.media_urls:
        try:
            blocks.append(image_block_from_url(url))
        except Exception as e:  # noqa: BLE001
            print(f"[stage-02] failed to fetch image {url!r}: {e!r}")

    blocks.append({"type": "text", "text": text_block})
    return blocks


def extract(message: RawMessage, *, client: Optional[Anthropic] = None, use_cache: bool = True) -> ExtractionResult:
    """Run Stage 2 on a single message. Returns ExtractionResult."""
    if use_cache:
        cached = _load_cache(message.message_id)
        if cached is not None:
            return ExtractionResult(
                message_id=message.message_id,
                is_offer_message=cached["is_offer_message"],
                skip_reason=cached.get("skip_reason"),
                offers=[_to_offer(message, o) for o in cached.get("offers", [])],
            )

    has_media_sources = bool(message.media_paths or message.media_urls)
    if message.message_type not in (MessageType.TEXT, MessageType.IMAGE):
        # Audio / PDF / Excel — not yet supported via vision. Will land in a
        # follow-up PR (Whisper for audio, document extraction for PDF/Excel).
        result_payload = {
            "is_offer_message": False,
            "skip_reason": f"unsupported_media:{message.message_type.value}",
            "offers": [],
        }
        if use_cache:
            _save_cache(message.message_id, result_payload)
        return ExtractionResult(
            message_id=message.message_id,
            is_offer_message=False,
            skip_reason=result_payload["skip_reason"],
            offers=[],
        )
    if message.message_type == MessageType.IMAGE and not has_media_sources:
        # Webhook flagged image but no path / URL to fetch — bridge hasn't
        # exposed the media yet. Skip; will retry when bridge gives us /media/{id}.
        result_payload = {
            "is_offer_message": False,
            "skip_reason": "image_without_source",
            "offers": [],
        }
        if use_cache:
            _save_cache(message.message_id, result_payload)
        return ExtractionResult(
            message_id=message.message_id,
            is_offer_message=False,
            skip_reason=result_payload["skip_reason"],
            offers=[],
        )

    client = client or Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_offers"},
        messages=[
            {
                "role": "user",
                "content": _build_user_content(message),
            }
        ],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    payload = tool_block.input  # dict

    if use_cache:
        _save_cache(message.message_id, payload)

    return ExtractionResult(
        message_id=message.message_id,
        is_offer_message=payload["is_offer_message"],
        skip_reason=payload.get("skip_reason"),
        offers=[_to_offer(message, o) for o in payload.get("offers", [])],
    )
