"""Relevance scoring — turns a raw offer into an alert decision.

Sits between Stage 4 (comparison) and Stage 5 (delivery). Stage 4 tells us
"this offer is R$ 7,74/un melhor que a Cienty". Relevance tells us "the buyer
ACTUALLY CARES about this product" — without it, we'd alert Wagno about every
DAPAGLIFLOZINA promo even though he never bought it.

Inputs:
  - ExtractedOffer (rep_offer, normalized to an EAN)
  - economy_pct from Stage 4 (how much cheaper than Cienty)
  - BuyerContext (profile + history + requested EANs)
  - product metadata (therapeutic_category from catalog)

Output: RelevanceScore with band ∈ {urgent, high, medium, low, skip}.

Scoring philosophy: combine binary signals into a 0..1 score, then bucketize.
Heuristic v1 — easy to tune. Calibrate from Wagno feedback ("alertou demais"
or "deixou passar isso").
"""
from __future__ import annotations

from typing import Optional

from ..profile.buyer_profile import BuyerContext
from ..schemas import (
    Direction,
    ExtractedOffer,
    RelevanceBand,
    RelevanceScore,
)


# --- tunables ----------------------------------------------------------------

W_HISTORY_DIRECT = 0.45   # buyer bought this EAN from Cienty before
W_REQUEST = 0.30          # buyer asked for this EAN on WhatsApp (didn't buy from us)
W_CATEGORY = 0.15         # buyer buys in this therapeutic_category
W_ECONOMY = 0.10          # how cheap is the offer vs Cienty

ECONOMY_THRESHOLD_HIGH = 0.15  # 15%+ economy ⇒ full economy signal
TOP_K_DIRECT_FLOOR = 1         # buyer must have bought ≥ this qty to count as direct

BAND_THRESHOLDS = [
    (0.75, RelevanceBand.URGENT),
    (0.50, RelevanceBand.HIGH),
    (0.30, RelevanceBand.MEDIUM),
    (0.10, RelevanceBand.LOW),
]


def score_offer(
    offer: ExtractedOffer,
    *,
    ean: Optional[str],
    therapeutic_category: Optional[str],
    economy_pct: Optional[float],
    buyer: BuyerContext,
) -> RelevanceScore:
    """Score a single rep_offer for one buyer.

    economy_pct: positive when offer is cheaper than Cienty. None when no Cienty price.
    """
    if offer.direction != Direction.REP_OFFER:
        return RelevanceScore(
            offer_message_id=offer.message_id,
            ean_matched=ean,
            score=0.0,
            band=RelevanceBand.SKIP,
            reason="not a rep offer",
        )

    signals: dict = {}

    # 1. Direct history — they bought this EAN from Cienty
    has_direct = False
    if ean and buyer.history is not None:
        qty = buyer.history.top_eans.get(ean, 0)
        has_direct = qty >= TOP_K_DIRECT_FLOOR
        signals["history_qty"] = qty
    signals["has_cienty_history"] = has_direct

    # 2. Buyer request — they asked for this EAN on WhatsApp
    has_request = bool(ean and ean in buyer.requested_eans)
    signals["has_buyer_request"] = has_request

    # 3. Category match — they buy in this category from Cienty
    has_category = False
    if therapeutic_category and buyer.history is not None:
        has_category = buyer.history.top_categories.get(therapeutic_category, 0) > 0
    signals["category_match"] = has_category

    # 4. Economy — the discount itself
    econ = 0.0
    if economy_pct is not None and economy_pct > 0:
        econ = min(1.0, economy_pct / ECONOMY_THRESHOLD_HIGH)
    signals["economy_pct"] = economy_pct
    signals["economy_signal"] = round(econ, 3)

    score = (
        (W_HISTORY_DIRECT if has_direct else 0.0)
        + (W_REQUEST if has_request else 0.0)
        + (W_CATEGORY if has_category else 0.0)
        + (W_ECONOMY * econ)
    )

    band = RelevanceBand.LOW
    for threshold, b in BAND_THRESHOLDS:
        if score >= threshold:
            band = b
            break
    else:
        band = RelevanceBand.SKIP if score < 0.1 else RelevanceBand.LOW

    # Reason — pick the strongest signal
    reasons = []
    if has_direct:
        reasons.append(f"compra recorrente ({signals['history_qty']} un)")
    if has_request:
        reasons.append("pediu cotação no Zap")
    if has_category:
        reasons.append("categoria que compra")
    if econ > 0.5:
        reasons.append(f"economia {economy_pct:.0%}")
    reason = " · ".join(reasons) if reasons else "produto que o buyer não tem histórico"

    return RelevanceScore(
        offer_message_id=offer.message_id,
        ean_matched=ean,
        score=round(score, 3),
        band=band,
        signals=signals,
        reason=reason,
    )
