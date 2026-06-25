"""End-to-end pipeline: WhatsApp webhook → silver.whatsapp_offers + comparison.

Modes:
  --mode sse     subscribe to /stream (recommended, real-time)
  --mode poll    poll /messages every N seconds

Flags to stage out:
  --no-extract   stage 1 only (echo what's coming, no LLM, no BQ)
  --no-bq        skip stages 3 + 4 (silver write + comparison) — useful for dev

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export GOOGLE_APPLICATION_CREDENTIALS=...   # optional, only for stages 3/4
    python scripts/run_pipeline.py --mode sse --profile fixtures/profiles/wagno.yaml
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Force UTF-8 on stdout/stderr so PT-BR (Patrícia, é, ç) doesn't get mangled
# when redirected to log files on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ingest.webhook_client import DEFAULT_BASE, iter_sse, poll  # noqa: E402
from agent.pipeline.stage_01_ingest import to_raw_message  # noqa: E402
from agent.profile.buyer_profile import load_profile  # noqa: E402


def _summarize_extraction(result, msg) -> str:
    if not result.is_offer_message:
        return f"  skip ({result.skip_reason})"
    parts = []
    for o in result.offers:
        if o.direction.value == "buyer_request":
            qty = f" x{o.requested_qty}" if o.requested_qty else ""
            parts.append(f"    REQ: {o.product_name_raw}{qty}")
        else:
            price = f" R$ {o.price_offered_brl:.2f}" if o.price_offered_brl else ""
            bonus = f" [{o.bonus_type.value}]" if o.bonus_type.value != "none" else ""
            parts.append(f"    OFFER: {o.product_name_raw}{price}{bonus}")
    return "\n".join(parts)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=DEFAULT_BASE, help="Webhook base URL")
    p.add_argument("--mode", choices=["sse", "poll"], default="sse")
    p.add_argument("--interval", type=float, default=2.0, help="Polling interval (poll mode)")
    p.add_argument("--profile", default="fixtures/profiles/wagno.yaml", help="Buyer profile YAML")
    p.add_argument("--no-extract", action="store_true", help="Stage 1 only — print payloads, no LLM")
    p.add_argument("--no-bq", action="store_true", help="Skip Stage 3+4 (silver write + comparison)")
    p.add_argument("--no-deliver", action="store_true", help="Skip Stage 5 (alert delivery)")
    p.add_argument(
        "--send-url",
        default=None,
        help="POST endpoint for sending WhatsApp alerts (HTTPSender). "
             "Falls back to LogSender when omitted.",
    )
    p.add_argument("--limit", type=int, default=0, help="Stop after N messages (0 = forever)")
    args = p.parse_args()

    buyer = load_profile(ROOT / args.profile) if Path(ROOT / args.profile).exists() else None
    aliases = buyer.profile.buyer_name_aliases if buyer else []
    if buyer:
        print(f"[pipeline] buyer profile: {buyer.profile.display_name} · "
              f"{len(buyer.profile.cnpjs)} CNPJ(s) · aliases={aliases}")
    print(f"[pipeline] webhook: {args.base} · mode={args.mode}")

    # Lazy imports — only when needed
    extract_fn = None
    if not args.no_extract:
        from agent.pipeline.stage_02_extract import extract as extract_fn  # noqa: E402,F811

    bq_client = None
    stage_03 = stage_04 = None
    if not args.no_bq:
        try:
            from google.cloud import bigquery
            from agent.pipeline import stage_03_normalize as stage_03  # noqa: F811
            from agent.pipeline import stage_04_compare as stage_04  # noqa: F811
            bq_client = bigquery.Client()
            print(f"[pipeline] BQ client ok · project={bq_client.project}")
        except Exception as e:  # noqa: BLE001
            print(f"[pipeline] BQ unavailable ({e!r}) — running without stages 3/4")
            bq_client = None

    # Stage 5 setup — alert delivery. Works even without BQ (we'll still
    # log the offer; once Stage 4 is plugged we get full alerts with economy.)
    deliver_fn = None
    sender = None
    if not args.no_deliver and buyer is not None:
        from agent.deliver.sender import HTTPSender, LogSender
        from agent.pipeline.stage_05_deliver import deliver as deliver_fn  # noqa: F811
        if args.send_url:
            sender = HTTPSender(args.send_url)
            print(f"[pipeline] sender: HTTPSender → {args.send_url}")
        else:
            sender = LogSender()
            print(f"[pipeline] sender: LogSender (runs/alerts.jsonl)")

    stream = iter_sse(args.base) if args.mode == "sse" else poll(args.base, interval=args.interval)
    processed = 0
    started = time.time()
    for payload in stream:
        if args.limit and processed >= args.limit:
            break
        msg = to_raw_message(payload, buyer_name_aliases=aliases)
        from_label = msg.source_name or msg.source_phone or "?"
        head = f"[{msg.received_at.strftime('%H:%M:%S')}] {from_label}: {msg.body[:80] or '<media>'}"
        print(head)

        if args.no_extract or extract_fn is None:
            processed += 1
            continue

        try:
            result = extract_fn(msg)
        except Exception as e:  # noqa: BLE001
            print(f"  [extract error] {e!r}")
            processed += 1
            continue

        print(_summarize_extraction(result, msg))

        if bq_client and stage_03 and stage_04 and result.is_offer_message:
            for offer in result.offers:
                if offer.direction.value != "rep_offer":
                    continue
                try:
                    row = stage_03.run(offer.model_dump(), bq_client)
                    if not row or row.get("match_status") != "matched":
                        continue
                    comps = stage_04.run(offer.message_id, bq_client) or []
                    for comp in comps:
                        if deliver_fn and buyer:
                            score = deliver_fn(
                                offer=offer,
                                comparison=comp,
                                buyer=buyer,
                                canonical_name=row.get("canonical_name"),
                                therapeutic_category=row.get("therapeutic_category"),
                                rep_name=msg.source_name,
                                sender=sender,
                            )
                            if score.band.value in ("urgent", "high"):
                                print(f"    ✓ alerted · {score.band.value} · score={score.score}")
                except Exception as e:  # noqa: BLE001
                    print(f"  [bq error] {e!r}")

        processed += 1
        if processed % 25 == 0:
            rate = processed / (time.time() - started)
            print(f"[pipeline] {processed} msgs · {rate:.2f}/s")

    elapsed = time.time() - started
    print(f"\n[pipeline] done · {processed} msgs in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
