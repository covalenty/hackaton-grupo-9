"""Tests for Stage 5 — delivery."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.deliver.formatter import format_alert  # noqa: E402
from agent.deliver.sender import LogSender  # noqa: E402
from agent.pipeline.stage_05_deliver import deliver  # noqa: E402
from agent.profile.buyer_profile import BuyerContext, BuyerHistoryFeatures  # noqa: E402
from agent.schemas import (  # noqa: E402
    BuyerProfile,
    Direction,
    ExtractedOffer,
    MessageType,
    RelevanceBand,
    RelevanceScore,
)


class CaptureSender:
    """Test double that records send() calls instead of doing IO."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send(self, *, to: str, text: str, context: dict | None = None) -> bool:
        self.calls.append({"to": to, "text": text, "context": context or {}})
        return True


def _wagno_context_with_history(ean: str, qty: int = 240) -> BuyerContext:
    profile = BuyerProfile(
        buyer_id="farmaestra",
        display_name="Wagno · Farmaestra",
        cnpjs=["04.796.409/0001-17"],
        source_phones=["+5519988008998"],
        alert_destination_phone="+5519988008998",  # hackathon: self-chat
        buyer_name_aliases=["WAGNO"],
    )
    history = BuyerHistoryFeatures(
        top_eans={ean: qty},
        top_categories={"ANALGESICO": qty},
    )
    return BuyerContext(profile=profile, history=history)


def _offer(price: float = 45.16) -> ExtractedOffer:
    return ExtractedOffer(
        message_id="m1",
        source_phone="+5519999998888",
        received_at=datetime(2026, 6, 25, 22, 47),
        message_type=MessageType.TEXT,
        direction=Direction.REP_OFFER,
        product_name_raw="DIPIRONA 24X10 NOVAQUIMICA",
        price_offered_brl=price,
    )


def test_formatter_brl_and_economy():
    score = RelevanceScore(
        offer_message_id="m1",
        ean_matched="7891234567890",
        score=0.85,
        band=RelevanceBand.URGENT,
        reason="compra recorrente (240 un) · economia 15%",
    )
    text = format_alert(
        offer=_offer(45.16),
        canonical_name="Dipirona Sódica 500mg 24x10",
        price_cienty_brl=52.90,
        economy_unit_brl=7.74,
        economy_pct=0.146,
        relevance=score,
        rep_name="Eduardo MILFARMA",
    )
    assert "Economize" in text
    assert "Eduardo MILFARMA" in text
    assert "Dipirona" in text
    assert "R$ 45,16" in text          # BR format with comma
    assert "R$ 52,90" in text
    assert "R$ 7,74" in text
    assert "15%" in text
    assert "Vale fechar com Eduardo MILFARMA" in text  # CTA


def test_deliver_alerts_on_high_relevance():
    buyer = _wagno_context_with_history("7891234567890")
    sender = CaptureSender()
    score = deliver(
        offer=_offer(45.16),
        comparison={
            "ean": "7891234567890",
            "price_cienty_brl": 52.90,
            "economy_unit_brl": 7.74,
            "economy_pct": 0.146,
            "urgency_class": "urgent",
        },
        buyer=buyer,
        canonical_name="Dipirona Sódica 500mg 24x10",
        therapeutic_category="ANALGESICO",
        rep_name="Eduardo MILFARMA",
        sender=sender,
    )
    assert score.band in {RelevanceBand.URGENT, RelevanceBand.HIGH}
    assert len(sender.calls) == 1
    assert sender.calls[0]["to"] == "+5519988008998"  # default = first profile phone


def test_deliver_no_alert_for_unknown_product():
    buyer = _wagno_context_with_history("7891234567890")  # has history on a DIFFERENT EAN
    sender = CaptureSender()
    score = deliver(
        offer=_offer(45.16),
        comparison={
            "ean": "9999999999999",  # not in buyer's history
            "price_cienty_brl": 52.90,
            "economy_unit_brl": 7.74,
            "economy_pct": 0.146,
            "urgency_class": "urgent",
        },
        buyer=buyer,
        sender=sender,
    )
    assert score.band in {RelevanceBand.LOW, RelevanceBand.MEDIUM, RelevanceBand.SKIP}
    assert sender.calls == []  # noise filtered out


def test_deliver_skips_buyer_request():
    buyer = _wagno_context_with_history("7891234567890")
    sender = CaptureSender()
    offer = _offer()
    offer.direction = Direction.BUYER_REQUEST
    score = deliver(
        offer=offer,
        comparison={"ean": "7891234567890"},
        buyer=buyer,
        sender=sender,
    )
    assert score.band == RelevanceBand.SKIP
    assert sender.calls == []


def test_deliver_cienty_better_when_rep_pricier():
    """Rep offer is MORE expensive than Cienty + buyer has history → CIENTY_BETTER alert."""
    buyer = _wagno_context_with_history("7891234567890")
    sender = CaptureSender()
    score = deliver(
        offer=_offer(45.16),  # rep offer
        comparison={
            "ean": "7891234567890",
            "price_cienty_brl": 42.21,   # Cienty cheaper
            "economy_unit_brl": -2.95,    # negative = rep more expensive
            "economy_pct": -0.070,
            "urgency_class": "standard",
        },
        buyer=buyer,
        canonical_name="Dipirona Nova Quimica 500Mg com 240",
        therapeutic_category="ANALGESICO",
        rep_name="Eduardo MILFARMA",
        sender=sender,
    )
    assert score.band == RelevanceBand.CIENTY_BETTER
    assert len(sender.calls) == 1
    text = sender.calls[0]["text"]
    assert "Cienty" in text
    assert "mais barato" in text
    assert "Comprar na Cienty" in text
    # clickable product link with the EAN + tracking params
    assert "/produto/7891234567890" in text
    assert "utm_source=whatsapp" in text
    assert "utm_medium=cienty-better-alert" in text


def test_deliver_no_cienty_better_alert_without_buyer_signal():
    """Rep pricier but buyer has no history/request → don't bother with the alert."""
    buyer = _wagno_context_with_history("7891234567890")  # history on different EAN
    sender = CaptureSender()
    score = deliver(
        offer=_offer(45.16),
        comparison={
            "ean": "9999999999999",        # not in buyer history
            "price_cienty_brl": 42.21,
            "economy_unit_brl": -2.95,
            "economy_pct": -0.070,
            "urgency_class": "standard",
        },
        buyer=buyer,
        sender=sender,
    )
    assert score.band != RelevanceBand.CIENTY_BETTER
    assert sender.calls == []


def test_logsender_persists_jsonl(tmp_path):
    log_path = tmp_path / "alerts.jsonl"
    sender = LogSender(jsonl_path=log_path)
    sender.send(to="+551199", text="hello", context={"k": "v"})
    sender.send(to="+551199", text="world")
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    import json
    rec = json.loads(lines[0])
    assert rec["text"] == "hello"
    assert rec["context"] == {"k": "v"}
