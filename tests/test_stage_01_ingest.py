"""Smoke tests for Stage 1 ingestion (webhook payload → RawMessage)."""
from __future__ import annotations

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
