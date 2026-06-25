"""Tests for the vision helpers and the Stage 2 multimodal content builder."""
from __future__ import annotations

import base64
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.extract.vision import (  # noqa: E402
    ALLOWED_IMAGE_MEDIA_TYPES,
    image_block_from_bytes,
    image_block_from_path,
)
from agent.pipeline.stage_02_extract import _build_user_content  # noqa: E402
from agent.schemas import MessageType, RawMessage  # noqa: E402


# 1x1 transparent PNG (smallest valid PNG)
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_image_block_from_bytes_is_anthropic_shape():
    block = image_block_from_bytes(TINY_PNG, media_type="image/png")
    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/png"
    # b64 round-trip
    assert base64.b64decode(block["source"]["data"]) == TINY_PNG


def test_image_block_rejects_invalid_media_type():
    block = image_block_from_bytes(TINY_PNG, media_type="application/octet-stream")
    # falls back to jpeg (the most common case for WhatsApp images)
    assert block["source"]["media_type"] == "image/jpeg"


def test_image_block_from_path(tmp_path):
    p = tmp_path / "tiny.png"
    p.write_bytes(TINY_PNG)
    block = image_block_from_path(p)
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"
    assert base64.b64decode(block["source"]["data"]) == TINY_PNG


def test_allowed_types_include_common_formats():
    assert "image/jpeg" in ALLOWED_IMAGE_MEDIA_TYPES
    assert "image/png" in ALLOWED_IMAGE_MEDIA_TYPES
    assert "image/webp" in ALLOWED_IMAGE_MEDIA_TYPES


def test_build_user_content_text_only_returns_string():
    msg = RawMessage(
        message_id="m1",
        source_name="Eduardo MILFARMA",
        received_at=datetime.now(tz=timezone.utc),
        body="DIPIRONA 24X10 NOVAQUIMICA R$ 45,16",
        has_media=False,
        message_type=MessageType.TEXT,
    )
    content = _build_user_content(msg)
    assert isinstance(content, str)
    assert "DIPIRONA" in content


def test_build_user_content_with_image_returns_multimodal_blocks(tmp_path):
    p = tmp_path / "promo.png"
    p.write_bytes(TINY_PNG)
    msg = RawMessage(
        message_id="m2",
        source_name="Paulinho Navarro",
        received_at=datetime.now(tz=timezone.utc),
        body="$13,49 para 24 unidades",
        has_media=True,
        message_type=MessageType.IMAGE,
        media_paths=[str(p)],
    )
    content = _build_user_content(msg)
    assert isinstance(content, list)
    assert len(content) == 2  # 1 image + 1 text
    assert content[0]["type"] == "image"
    assert content[1]["type"] == "text"
    # caption preserved in text block
    assert "$13,49" in content[1]["text"]
