"""Force a full end-to-end alert from an existing silver row.

Used for hackathon demo when the latest message landed as low_confidence
but we want to show Stage 4 + 5 producing a real alert.

Picks the most recent rep_offer in silver.whatsapp_offers that has an
ean_matched (even if confidence was below 0.85), pulls the comparison from
latest_commercial_conditions_realtime, and runs delivery against Wagno's profile.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from google.cloud import bigquery

from agent.pipeline.stage_05_deliver import deliver
from agent.profile.buyer_profile import load_profile
from agent.schemas import Direction, ExtractedOffer, MessageType


PROJECT = "cienty-data-platform"


def main() -> int:
    bq = bigquery.Client(project=PROJECT)
    buyer = load_profile(ROOT / "fixtures/profiles/wagno.yaml")

    # 1. Get the latest rep_offer in silver that has an EAN match (any confidence)
    sql_offer = """
      SELECT message_id, source_phone, received_at, product_name_raw,
             price_offered_brl, bonus_type, bonus_qty, min_qty, deadline,
             direction, requested_qty,
             ean_matched, canonical_name, confidence_score, match_status
      FROM `cienty-data-platform.cienty_silver.whatsapp_offers`
      WHERE ean_matched IS NOT NULL
        AND IFNULL(direction, 'rep_offer') = 'rep_offer'
      ORDER BY _ingestion_timestamp DESC
      LIMIT 1
    """
    row = next(iter(bq.query(sql_offer).result()), None)
    if not row:
        print("No rep_offer with ean_matched found in silver. Send a message first.")
        return 1
    print(f"[demo] using offer: {row.product_name_raw} @ R$ {row.price_offered_brl}")
    print(f"       matched EAN: {row.ean_matched} ({row.canonical_name})")
    print(f"       confidence: {row.confidence_score:.4f} ({row.match_status})")

    # 2. Pull the comparison straight from realtime (bypass threshold)
    sql_compare = """
      SELECT client_id, MIN(price_final_brl) AS price_cienty_brl, COUNT(*) AS n_offers
      FROM `cienty-data-platform.cienty_silver.latest_commercial_conditions_realtime`
      WHERE ean = @ean AND price_final_brl > 0
      GROUP BY client_id
      ORDER BY price_cienty_brl ASC
      LIMIT 3
    """
    job = bq.query(
        sql_compare,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("ean", "STRING", row.ean_matched)]
        ),
    )
    cienty_rows = list(job.result())
    if not cienty_rows:
        print(f"[demo] no Cienty price for EAN {row.ean_matched} — can't compare")
        return 1
    best = cienty_rows[0]
    economy_unit = round(float(best.price_cienty_brl) - float(row.price_offered_brl), 2)
    economy_pct = economy_unit / float(best.price_cienty_brl) if best.price_cienty_brl else 0
    print(f"[demo] Cienty best price: R$ {best.price_cienty_brl:.2f} "
          f"(across {len(cienty_rows)} clients shown)")
    print(f"[demo] economy: R$ {economy_unit:.2f}/un · {economy_pct:.1%}")

    # 3. Reconstruct an ExtractedOffer to feed stage_05_deliver
    offer = ExtractedOffer(
        message_id=row.message_id,
        source_phone=row.source_phone,
        received_at=row.received_at if isinstance(row.received_at, datetime)
                    else datetime.now(timezone.utc),
        message_type=MessageType.TEXT,
        direction=Direction.REP_OFFER,
        product_name_raw=row.product_name_raw,
        price_offered_brl=float(row.price_offered_brl),
        bonus_type=row.bonus_type or "none",
        bonus_qty=row.bonus_qty,
        min_qty=row.min_qty,
        deadline=row.deadline,
        extraction_confidence=1.0,
    )

    comparison = {
        "ean": row.ean_matched,
        "price_cienty_brl": float(best.price_cienty_brl),
        "economy_unit_brl": economy_unit,
        "economy_pct": economy_pct,
        "urgency_class": "urgent" if economy_pct > 0.10 else "standard",
    }

    # 4. Boost relevance: this is a demo — pretend buyer has bought this EAN before
    buyer.history = None  # ensure no stale history
    # set requested_eans so relevance fires even without history loaded
    buyer.requested_eans = {row.ean_matched}

    print("\n[demo] firing Stage 5 deliver...\n")
    score = deliver(
        offer=offer,
        comparison=comparison,
        buyer=buyer,
        canonical_name=row.canonical_name,
        therapeutic_category=None,
        rep_name="Miriam (demo)",
    )
    print(f"\n[demo] final score: {score.score} · band: {score.band.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
