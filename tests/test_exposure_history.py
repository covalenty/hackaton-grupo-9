"""Tests for exposure_eans signal — proxy for has_cienty_history when
Cienty doesn't have transactional data.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.profile.buyer_profile import BuyerContext, BuyerHistoryFeatures
from agent.relevance.scorer import score_offer
from agent.schemas import (
    BuyerProfile,
    Direction,
    ExtractedOffer,
    MessageType,
    RelevanceBand,
)


def _buyer_with_exposure(ean: str, days: int) -> BuyerContext:
    profile = BuyerProfile(
        buyer_id="farmaestra",
        display_name="Wagno · Farmaestra",
        cnpjs=["04.796.409/0001-17"],
        source_phones=["+5511936199146"],
        alert_destination_phone="+5511936199146",
        buyer_name_aliases=["WAGNO"],
    )
    history = BuyerHistoryFeatures(
        exposure_eans={ean: days},
        top_categories={"M1A1": days},
    )
    return BuyerContext(profile=profile, history=history)


def _offer(price: float = 5.00) -> ExtractedOffer:
    return ExtractedOffer(
        message_id="m1",
        received_at=datetime(2026, 6, 25, 22, 47),
        message_type=MessageType.TEXT,
        direction=Direction.REP_OFFER,
        product_name_raw="DIPIRONA 24X10 NOVAQUIMICA",
        price_offered_brl=price,
    )


def test_exposure_above_threshold_triggers_history_signal():
    """40 dias de exposure (>= 30 threshold) → has_cienty_history=True."""
    ean = "7891234567890"
    buyer = _buyer_with_exposure(ean, days=40)
    score = score_offer(
        _offer(price=4.30),
        ean=ean,
        therapeutic_category="M1A1",
        economy_pct=0.10,
        buyer=buyer,
    )
    assert score.signals["has_cienty_history"] is True
    assert score.signals["exposure_days"] == 40
    assert score.band in {RelevanceBand.URGENT, RelevanceBand.HIGH}
    assert "produto core do mix" in score.reason
    assert "40d expostos" in score.reason


def test_exposure_below_threshold_is_not_signal():
    """20 dias (< 30 threshold) — não é forte o suficiente."""
    ean = "7891234567890"
    buyer = _buyer_with_exposure(ean, days=20)
    score = score_offer(
        _offer(),
        ean=ean,
        therapeutic_category="M1A1",
        economy_pct=0.10,
        buyer=buyer,
    )
    assert score.signals["has_cienty_history"] is False
    # category still hits → medium-ish, but no "compra recorrente"
    assert "produto core" not in score.reason
    assert "compra recorrente" not in score.reason


def test_top_eans_purchases_still_win_over_exposure_when_present():
    """When transactions land in BQ (top_eans populated), reason uses qty not exposure."""
    ean = "7891234567890"
    profile = BuyerProfile(
        buyer_id="farmaestra",
        display_name="Wagno",
        source_phones=["+551199"],
        alert_destination_phone="+551199",
        buyer_name_aliases=["WAGNO"],
    )
    history = BuyerHistoryFeatures(
        top_eans={ean: 240},       # real purchases
        exposure_eans={ean: 47},   # also seen
        top_categories={"M1A1": 240},
    )
    ctx = BuyerContext(profile=profile, history=history)
    score = score_offer(
        _offer(price=4.30),
        ean=ean,
        therapeutic_category="M1A1",
        economy_pct=0.10,
        buyer=ctx,
    )
    assert "compra recorrente (240 un)" in score.reason
    # exposure phrasing should NOT appear when we have real purchases
    assert "produto core do mix" not in score.reason
