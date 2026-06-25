"""Demo runner for client showcase — fires a curated sequence of alerts.

Tells a story over ~20 seconds:
  1. URGENT — generic analgesic, mid economy. The "happy path" save.
  2. URGENT — with bonus + deadline. Shows scarcity capture.
  3. CIENTY_BETTER — rep tries to slip in pricier offer. Cienty defends GMV.
  4. CIENTY_BETTER — another category, makes the pattern feel general.

Each alert uses a real EAN that exists in the Cienty catalog so the
search link in the message resolves to a real product page.

Usage:
    python scripts/demo_client.py                  # send 4 alerts, ~3s apart
    python scripts/demo_client.py --interval 5     # slower for screen recording
    python scripts/demo_client.py --only 3         # just scenario #3
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from agent.deliver.sender import HTTPSender
from agent.pipeline.stage_05_deliver import deliver
from agent.profile.buyer_profile import BuyerHistoryFeatures, load_profile
from agent.schemas import BonusType, Direction, ExtractedOffer, MessageType


BRIDGE_SEND_URL = "https://used-pad-interstate-smithsonian.trycloudflare.com/send"


# Real EANs from cienty_gold.product_catalog_normalized, with median Cienty
# prices from latest_commercial_conditions_realtime. Picked for recognizable
# product families and dramatic-but-honest economy in either direction.
SCENARIOS = [
    {
        "label": "URGENT · Losartana",
        "ean": "7896004713922",
        "canonical": "Losartana + Hidroclorotiazida EMS 50/12,5mg cx 30",
        "category": "ANTIHIPERTENSIVO",
        "rep_name": "Eduardo MILFARMA",
        "rep_phone": "+5519988008990",
        "raw": "Losartana Potass+HCTZ EMS 50 cx30 R$ 12,00",
        "price_offered": 12.00,
        "price_cienty": 15.70,
        "bonus": BonusType.NONE,
        "bonus_qty": None,
        "min_qty": 30,
        "deadline": None,
    },
    {
        "label": "URGENT · Cimegrip (com bonificação + prazo)",
        "ean": "7891317005917",
        "canonical": "Carisoprodol + Diclofenaco + Paracetamol + Cafeína 30cpr",
        "category": "ANALGESICO",
        "rep_name": "Daniele Servimed",
        "rep_phone": "+5511987776666",
        "raw": "Carisoprodol 30cpr R$ 4,90 · cinema 1:1 · vence amanhã 12h",
        "price_offered": 4.90,
        "price_cienty": 6.62,
        "bonus": BonusType.QTY,
        "bonus_qty": 1,
        "min_qty": 60,
        "deadline": datetime.now(timezone.utc) + timedelta(hours=18),
    },
    {
        "label": "CIENTY_BETTER · Paracetamol + Codeína",
        "ean": "7891317000110",
        "canonical": "Paracetamol + Codeína Eurofarma 30mg c/12 (A2)",
        "category": "ANALGESICO",
        "rep_name": "Patricia Nogueira",
        "rep_phone": "+5519988007777",
        "raw": "Paraceta+Codeina Euro 30mg c/12 R$ 13,50",
        "price_offered": 13.50,
        "price_cienty": 10.53,
        "bonus": BonusType.NONE,
        "bonus_qty": None,
        "min_qty": None,
        "deadline": None,
    },
    {
        "label": "CIENTY_BETTER · Losartana segunda marca",
        "ean": "7891317445287",
        "canonical": "Losartana + Hidroclorotiazida Eurofarma 50/12,5mg",
        "category": "ANTIHIPERTENSIVO",
        "rep_name": "Rogério Mantiqueira",
        "rep_phone": "+5519988005555",
        "raw": "Losartana Euro 50/12.5 R$ 12,80",
        "price_offered": 12.80,
        "price_cienty": 9.85,
        "bonus": BonusType.NONE,
        "bonus_qty": None,
        "min_qty": None,
        "deadline": None,
    },
]


def _make_offer(s: dict) -> ExtractedOffer:
    return ExtractedOffer(
        message_id=f"demo-{int(time.time())}-{s['ean'][-4:]}",
        source_phone=s["rep_phone"],
        received_at=datetime.now(timezone.utc),
        message_type=MessageType.TEXT,
        direction=Direction.REP_OFFER,
        product_name_raw=s["raw"],
        price_offered_brl=s["price_offered"],
        bonus_type=s["bonus"],
        bonus_qty=s["bonus_qty"],
        min_qty=s["min_qty"],
        deadline=s["deadline"],
    )


def _build_buyer(s: dict):
    """Buyer w/ baked history so every scenario fires above MEDIUM."""
    buyer = load_profile(ROOT / "fixtures/profiles/wagno.yaml")
    buyer.history = BuyerHistoryFeatures(
        top_eans={s["ean"]: 180},
        top_categories={s["category"]: 600},
        monthly_gmv_brl=16000.0,
        monthly_orders=18,
        distinct_eans=320,
    )
    buyer.requested_eans = {s["ean"]}
    return buyer


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=float, default=3.0, help="Seconds between alerts.")
    p.add_argument("--only", type=int, default=None, help="Run only scenario N (1-indexed).")
    p.add_argument("--send-url", default=BRIDGE_SEND_URL)
    args = p.parse_args()

    sender = HTTPSender(args.send_url)

    todo = SCENARIOS if args.only is None else [SCENARIOS[args.only - 1]]
    for i, s in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {s['label']}")
        offer = _make_offer(s)
        buyer = _build_buyer(s)
        economy = round(s["price_cienty"] - s["price_offered"], 2)
        comparison = {
            "ean": s["ean"],
            "price_cienty_brl": s["price_cienty"],
            "economy_unit_brl": economy,
            "economy_pct": economy / s["price_cienty"] if s["price_cienty"] else 0,
        }
        score = deliver(
            offer=offer,
            comparison=comparison,
            buyer=buyer,
            canonical_name=s["canonical"],
            therapeutic_category=s["category"],
            rep_name=s["rep_name"],
            sender=sender,
        )
        print(f"        band={score.band.value} · score={score.score}")
        if i < len(todo) and args.interval > 0:
            time.sleep(args.interval)

    print("\n[demo] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
