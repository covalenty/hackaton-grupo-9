"""Smoke tests for the WhatsApp export parser."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.extract.parser import iter_messages  # noqa: E402
from agent.schemas import MessageType  # noqa: E402


SAMPLE = """16/01/2026 12:59 - As mensagens e ligações são protegidas com a criptografia de ponta a ponta.
16/01/2026 12:59 - ‎Eduardo MILFARMA criou o grupo "PROMOÇÕES MILFARMA"
16/01/2026 15:02 - Eduardo MILFARMA: ✅️SALICETIL 50x10  R$ 27.67

✅️DIPIRONA 24X10 NOVAQUIMICA R$ 45.16
21/01/2026 11:19 - Eduardo MILFARMA: <Mídia oculta>
06/11/2024 11:18 - WAGNO: Bom dia pessoal, espero que estejam bem,

Vou liberar a cotação.
"""


def test_parser_basic(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text(SAMPLE, encoding="utf-8")
    msgs = list(iter_messages(path, group_name="PROMOÇÕES MILFARMA", buyer_name_aliases=["WAGNO"]))

    assert len(msgs) == 3, f"expected 3 user messages, got {len(msgs)}"

    push = msgs[0]
    assert push.source_name == "Eduardo MILFARMA"
    assert "SALICETIL" in push.body
    assert "DIPIRONA" in push.body
    assert push.has_media is False
    assert push.message_type == MessageType.TEXT
    assert push.group_name == "PROMOÇÕES MILFARMA"
    assert push.is_from_buyer is False

    media = msgs[1]
    assert media.has_media is True
    assert media.message_type == MessageType.IMAGE

    wagno = msgs[2]
    assert wagno.source_name == "WAGNO"
    assert wagno.is_from_buyer is True
    assert "cotação" in wagno.body


def test_parser_skips_system_messages(tmp_path):
    sample = """16/01/2026 12:59 - As mensagens e ligações são protegidas
16/01/2026 12:59 - ‎Eduardo MILFARMA criou o grupo "X"
16/01/2026 12:59 - ‎Eduardo MILFARMA adicionou você
"""
    path = tmp_path / "sys.txt"
    path.write_text(sample, encoding="utf-8")
    msgs = list(iter_messages(path))
    assert msgs == []
