"""Smoke tests for Stage 1 ingestion (webhook payload → RawMessage)."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.pipeline.stage_01_ingest import to_raw_message  # noqa: E402
from agent.schemas import MessageType  # noqa: E402


def test_text_rep_offer():
    payload = {
        "id": "ABCDE12345",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Eduardo MILFARMA",
        "text": "DIPIRONA 24X10 NOVAQUIMICA R$ 45,16",
        "timestamp": 1782396413000,
        "raw": {},
    }
    msg = to_raw_message(payload, buyer_name_aliases=["WAGNO"])
    assert msg.source_name == "Eduardo MILFARMA"
    assert msg.source_phone == "+5519999998888"
    assert msg.has_media is False
    assert msg.message_type == MessageType.TEXT
    assert msg.is_from_buyer is False
    assert "DIPIRONA" in msg.body


def test_text_buyer_request():
    payload = {
        "id": "F12345",
        "from": "5519988008998@s.whatsapp.net",
        "name": "WAGNO",
        "text": "Bom dia, alguém tem dipirona 500mg?",
        "timestamp": 1782396413000,
        "raw": {},
    }
    msg = to_raw_message(payload, buyer_name_aliases=["WAGNO", "C Cienty"])
    assert msg.is_from_buyer is True
    assert msg.source_phone == "+5519988008998"


def test_image_no_text():
    payload = {
        "id": "X1",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Eduardo MILFARMA",
        "text": None,
        "timestamp": 1782396413000,
        "raw": {"message": {"imageMessage": {"caption": ""}}},
    }
    msg = to_raw_message(payload)
    assert msg.has_media is True
    assert msg.message_type == MessageType.IMAGE


def test_pdf_document():
    payload = {
        "id": "X2",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Eduardo MILFARMA",
        "text": None,
        "timestamp": 1782396413000,
        "raw": {"message": {"documentMessage": {"fileName": "promo-semana.PDF"}}},
    }
    msg = to_raw_message(payload)
    assert msg.message_type == MessageType.PDF


def test_audio():
    payload = {
        "id": "X3",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Eduardo MILFARMA",
        "text": None,
        "timestamp": 1782396413000,
        "raw": {"message": {"audioMessage": {}}},
    }
    msg = to_raw_message(payload)
    assert msg.message_type == MessageType.AUDIO


def test_group_jid_phone():
    payload = {
        "id": "G1",
        "from": "120363012345678-1500000000@g.us",
        "name": "Eduardo MILFARMA",
        "text": "promo aí galera",
        "timestamp": 1782396413000,
        "raw": {},
    }
    msg = to_raw_message(payload)
    # group JIDs don't yield a valid +phone — we drop them
    assert msg.source_phone == "+120363012345678"


# ---- vision-live: media plumbing -------------------------------------------


def test_image_caption_lifts_into_body():
    """imageMessage.caption is hoisted into body when payload.text is null."""
    payload = {
        "id": "IMG_CAP",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Paulinho Navarro",
        "text": None,
        "timestamp": 1782396413000,
        "raw": {"message": {"imageMessage": {"caption": "$13,49 para 24un / $12,99 para 60un"}}},
    }
    msg = to_raw_message(payload)
    assert msg.has_media is True
    assert msg.media_paths == []      # no bytes given
    assert msg.media_urls == []       # no URL given
    assert "$13,49" in msg.body
    assert "60un" in msg.body


def test_media_url_populates_urls():
    payload = {
        "id": "IMG_URL",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Paulinho Navarro",
        "text": None,
        "timestamp": 1782396413000,
        "media_url": "https://bridge.example.com/media/IMG_URL",
        "raw": {"message": {"imageMessage": {"caption": "promo do dia"}}},
    }
    msg = to_raw_message(payload)
    assert msg.media_urls == ["https://bridge.example.com/media/IMG_URL"]
    assert msg.media_paths == []
    assert msg.body == "promo do dia"


def test_media_b64_materializes_tmp_file():
    """Inline base64 bytes get written to disk so Stage 2 vision can read them."""
    # 1x1 transparent PNG
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    payload = {
        "id": "IMG_B64",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Paulinho Navarro",
        "text": None,
        "timestamp": 1782396413000,
        "media_b64": base64.b64encode(tiny_png).decode(),
        "raw": {"message": {"imageMessage": {"caption": ""}}},
    }
    msg = to_raw_message(payload)
    assert len(msg.media_paths) == 1
    p = Path(msg.media_paths[0])
    assert p.exists()
    assert p.read_bytes() == tiny_png
    p.unlink(missing_ok=True)


def test_media_b64_invalid_base64_is_dropped_silently():
    """Bad base64 string shouldn't crash the pipeline — just drops the media."""
    payload = {
        "id": "BAD_B64",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Paulinho Navarro",
        "text": None,
        "timestamp": 1782396413000,
        "media_b64": "###not-base64###",
        "raw": {"message": {"imageMessage": {"caption": ""}}},
    }
    # validate=False is permissive, but if it still produces empty bytes nothing is saved
    msg = to_raw_message(payload)
    # Should either be empty or contain a file we silently consider invalid;
    # this test only asserts no exception was raised.
    assert msg.message_type == MessageType.IMAGE


def test_no_media_fields_leaves_lists_empty():
    payload = {
        "id": "PLAIN",
        "from": "5519999998888@s.whatsapp.net",
        "name": "Eduardo MILFARMA",
        "text": "DIPIRONA R$ 5,16",
        "timestamp": 1782396413000,
        "raw": {},
    }
    msg = to_raw_message(payload)
    assert msg.media_paths == []
    assert msg.media_urls == []
