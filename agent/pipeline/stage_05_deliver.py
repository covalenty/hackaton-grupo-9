"""Stage 5 — delivery.

Inputs:
  - one ExtractedOffer (rep_offer, already normalized via Stage 3)
  - the comparison row from Stage 4 (urgency_class, economy_unit_brl, ean_matched, ...)
  - BuyerContext (profile + history + requested_eans)
  - the canonical product info from the catalog (canonical_name, therapeutic_category)
  - a WhatsAppSender impl
  - a destination phone for alerts

Decides if it should alert via `agent.relevance.score_offer`, then formats
and ships. Returns the RelevanceScore so the caller can log/persist.

Only ever sends rep_offers — buyer_request rows are skipped here (they feed
the unmet_demand view, not alerts).
"""
from __future__ import annotations

from typing import Optional

from ..deliver.formatter import format_alert
from ..deliver.sender import LogSender, WhatsAppSender
from ..profile.buyer_profile import BuyerContext
from ..relevance.scorer import score_offer
from ..schemas import Direction, ExtractedOffer, RelevanceBand, RelevanceScore


ALERT_BANDS = {RelevanceBand.URGENT, RelevanceBand.HIGH}


def deliver(
    *,
    offer: ExtractedOffer,
    comparison: dict,
    buyer: BuyerContext,
    canonical_name: Optional[str] = None,
    therapeutic_category: Optional[str] = None,
    rep_name: Optional[str] = None,
    sender: Optional[WhatsAppSender] = None,
    to_phone: Optional[str] = None,
) -> RelevanceScore:
    """Score → decide → format → send. Returns the score for logging.

    `comparison` is the Stage 4 row dict. Expected keys:
      ean, price_cienty_brl, economy_unit_brl, economy_pct, urgency_class.
    """
    sender = sender or LogSender()

    if offer.direction != Direction.REP_OFFER:
        return RelevanceScore(
            offer_message_id=offer.message_id,
            ean_matched=comparison.get("ean"),
            score=0.0,
            band=RelevanceBand.SKIP,
            reason="buyer_request — não alerta, vai pro unmet_demand",
        )

    score = score_offer(
        offer,
        ean=comparison.get("ean"),
        therapeutic_category=therapeutic_category,
        economy_pct=comparison.get("economy_pct"),
        buyer=buyer,
    )

    if score.band not in ALERT_BANDS:
        return score

    if not to_phone:
        # Use first phone in profile as default destination
        if buyer.profile.source_phones:
            to_phone = buyer.profile.source_phones[0]
        else:
            print("[deliver] no destination phone configured — skipping send")
            return score

    text = format_alert(
        offer=offer,
        canonical_name=canonical_name,
        price_cienty_brl=comparison.get("price_cienty_brl"),
        economy_unit_brl=comparison.get("economy_unit_brl"),
        economy_pct=comparison.get("economy_pct"),
        relevance=score,
        rep_name=rep_name,
    )
    sender.send(
        to=to_phone,
        text=text,
        context={
            "message_id": offer.message_id,
            "ean": score.ean_matched,
            "band": score.band.value,
            "score": score.score,
        },
    )
    return score
