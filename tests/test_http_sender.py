"""Tests for HTTPSender — phone number normalization for the bridge contract."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.deliver.sender import HTTPSender  # noqa: E402


def test_normalize_strips_plus():
    assert HTTPSender._normalize_number("+5519988008998") == "5519988008998"


def test_normalize_strips_jid_suffix():
    assert HTTPSender._normalize_number("5519988008998@s.whatsapp.net") == "5519988008998"
    assert HTTPSender._normalize_number("+5519988008998@s.whatsapp.net") == "5519988008998"


def test_normalize_strips_non_digits():
    assert HTTPSender._normalize_number("+55 (19) 98800-8998") == "5519988008998"


def test_normalize_handles_whitespace():
    assert HTTPSender._normalize_number("  +5519988008998  ") == "5519988008998"
