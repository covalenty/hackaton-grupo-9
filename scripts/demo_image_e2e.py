"""End-to-end demo: real image → vision extract → (optional BQ) → format → send.

Goes Paulinho's promo JPG all the way to a real WhatsApp message on the bridge.

When BQ is reachable, runs Stage 3 (normalize EAN) + Stage 4 (compare with
Cienty price) for each extracted offer. When not, falls back to a synthetic
comparison so the alert chain still renders.

Usage:
    export ANTHROPIC_API_KEY=...
    python scripts/demo_image_e2e.py path/to/promo.jpg \\
        --sender "Paulinho Navarro" \\
        --send-url https://used-pad-interstate-smithsonian.trycloudflare.com/send
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from agent.deliver.formatter import format_alert
from agent.deliver.sender import HTTPSender, LogSender
from agent.pipeline.stage_02_extract import extract
from agent.profile.buyer_profile import load_profile
from agent.relevance.scorer import score_offer
from agent.schemas import Direction, MessageType, RawMessage, RelevanceBand


def _bq_compare(offer, bq_client, client_ids=None):
    """Run Stage 3 + Stage 4 and return the first comparison row (or None)."""
    from agent.pipeline import stage_03_normalize, stage_04_compare
    row = stage_03_normalize.run(offer.model_dump(), bq_client)
    if not row or row.get("match_status") != "matched":
        return None, row
    comps = stage_04_compare.run(offer.message_id, bq_client, client_ids=client_ids) or []
    return (comps[0] if comps else None), row


def _synthetic_comparison(offer) -> dict:
    """Used when BQ isn't reachable or product didn't match the catalog.

    Treats the rep price as ~12% better than a fake Cienty price so the
    formatter has a realistic urgency story to render. Marked clearly.
    """
    rep_price = offer.price_offered_brl or 0.0
    fake_cienty = round(rep_price / 0.88, 2) if rep_price else None
    economy_unit = round(fake_cienty - rep_price, 2) if fake_cienty else None
    return {
        "ean": None,
        "price_cienty_brl": fake_cienty,
        "economy_unit_brl": economy_unit,
        "economy_pct": 0.12 if rep_price else None,
        "urgency_class": "urgent",
        "_synthetic": True,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("image", help="Path to a JPG/PNG")
    p.add_argument("--caption", default="", help="Caption alongside the image")
    p.add_argument("--sender", default="Paulinho Navarro")
    p.add_argument("--profile", default="fixtures/profiles/wagno.yaml")
    p.add_argument("--send-url", default=None, help="Bridge POST endpoint (e.g. https://.../send)")
    p.add_argument("--no-bq", action="store_true", help="Skip Stage 3/4 — use synthetic comparison")
    p.add_argument("--no-send", action="store_true", help="Render alerts but don't POST")
    p.add_argument("--max-alerts", type=int, default=1, help="Limit alerts (avoid flooding the Zap)")
    args = p.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"file not found: {img_path}", file=sys.stderr)
        return 2

    buyer = load_profile(ROOT / args.profile)
    aliases = buyer.profile.buyer_name_aliases
    print(f"[demo] buyer: {buyer.profile.display_name} · alert→ {buyer.profile.alert_destination_phone}")

    # Stage 1 — synthesize a RawMessage as if it came from the bridge
    msg = RawMessage(
        message_id=f"img-{img_path.stem}",
        source_name=args.sender,
        received_at=datetime.now(tz=timezone.utc),
        body=args.caption,
        has_media=True,
        message_type=MessageType.IMAGE,
        media_paths=[str(img_path.resolve())],
        is_from_buyer=args.sender.lower() in {a.lower() for a in aliases},
    )

    # Stage 2 — vision extraction
    print(f"[stage-02] extracting from {img_path.name}...")
    result = extract(msg, use_cache=True)
    if not result.is_offer_message:
        print(f"  skip: {result.skip_reason}")
        return 0
    print(f"  -> {len(result.offers)} offer(s) extracted")

    # Sender
    sender = LogSender() if not args.send_url else HTTPSender(args.send_url)
    if args.send_url:
        print(f"[deliver] HTTPSender -> {args.send_url}")

    # Optional BQ
    bq_client = None
    if not args.no_bq:
        try:
            from google.cloud import bigquery
            bq_client = bigquery.Client(project="cienty-data-platform")
            print(f"[deliver] BQ ok (project={bq_client.project})")
        except Exception as e:  # noqa: BLE001
            print(f"[deliver] BQ unavailable ({e!r}) — synthetic comparison")

    alerts_sent = 0
    for i, offer in enumerate(result.offers, 1):
        if offer.direction != Direction.REP_OFFER or offer.price_offered_brl is None:
            continue
        if alerts_sent >= args.max_alerts:
            print(f"[deliver] limit reached ({args.max_alerts}) — stopping")
            break

        # Stage 3 + Stage 4 (or synthetic)
        comp, row = None, None
        if bq_client:
            try:
                comp, row = _bq_compare(offer, bq_client, client_ids=buyer.profile.client_ids)
            except Exception as e:  # noqa: BLE001
                print(f"  [bq error] {e!r}")
        if not comp:
            comp = _synthetic_comparison(offer)
            print(f"  offer {i}: '{offer.product_name_raw}' -> synthetic comparison")
            # When the BQ match wasn't high-confidence we drop canonical_name to
            # avoid showing the wrong product name in the alert.
            if row and row.get("match_status") != "matched":
                row = None
        else:
            print(f"  offer {i}: '{offer.product_name_raw}' -> matched EAN {row.get('ean_matched')}")

        # Relevance (with empty history fallback so demo can fire)
        score = score_offer(
            offer,
            ean=comp.get("ean"),
            therapeutic_category=row.get("therapeutic_category") if row else None,
            economy_pct=comp.get("economy_pct"),
            buyer=buyer,
        )
        if score.band == RelevanceBand.SKIP:
            # demo override — push as HIGH so the alert renders end-to-end
            print(f"  -> relevance SKIP, forcing HIGH for demo")
            from agent.schemas import RelevanceScore
            score = RelevanceScore(
                offer_message_id=offer.message_id,
                ean_matched=comp.get("ean"),
                score=0.55,
                band=RelevanceBand.HIGH,
                reason="demo · sem histórico ainda do Wagno",
            )

        text = format_alert(
            offer=offer,
            canonical_name=(row.get("canonical_name") if row else None),
            price_cienty_brl=comp.get("price_cienty_brl"),
            economy_unit_brl=comp.get("economy_unit_brl"),
            economy_pct=comp.get("economy_pct"),
            relevance=score,
            rep_name=args.sender,
        )

        if args.no_send:
            print("\n----- ALERT (preview, not sent) -----")
            print(text)
            print("-------------------------------------\n")
        else:
            sender.send(
                to=buyer.profile.alert_destination_phone,
                text=text,
                context={
                    "message_id": offer.message_id,
                    "band": score.band.value,
                    "image": img_path.name,
                },
            )
        alerts_sent += 1

    print(f"\n[demo] done · alerts={alerts_sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
