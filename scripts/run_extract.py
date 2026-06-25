"""End-to-end runner: WhatsApp export → Stage 2 extraction → JSONL output.

Usage:
    python scripts/run_extract.py \
        --input "../whatsapp-samples/milfarma/Conversa do WhatsApp com PROMO+ç+òES MILFARMA.txt" \
        --output runs/milfarma.jsonl \
        --group "PROMOÇÕES MILFARMA" \
        --limit 100

Requires ANTHROPIC_API_KEY env var.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.extract.parser import iter_messages  # noqa: E402
from agent.pipeline.stage_02_extract import extract  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="WhatsApp export .txt path")
    p.add_argument("--output", required=True, help="Output JSONL path")
    p.add_argument("--group", default=None, help="Group/list name for these messages")
    p.add_argument("--limit", type=int, default=0, help="Max messages to process (0 = all)")
    p.add_argument("--skip-media", action="store_true", help="Skip messages with media attachments")
    p.add_argument("--no-cache", action="store_true", help="Bypass cache")
    p.add_argument(
        "--buyer-aliases",
        default="WAGNO,C Cienty,C Comprador",
        help="Comma-separated buyer name aliases to flag is_from_buyer.",
    )
    args = p.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    aliases = [a.strip() for a in args.buyer_aliases.split(",") if a.strip()]
    total = 0
    offers_total = 0
    skipped = 0
    started = time.time()

    with out_path.open("w", encoding="utf-8") as out:
        for msg in iter_messages(args.input, group_name=args.group, buyer_name_aliases=aliases):
            if args.limit and total >= args.limit:
                break
            if args.skip_media and msg.has_media:
                skipped += 1
                continue
            try:
                result = extract(msg, use_cache=not args.no_cache)
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] {msg.message_id}: {e}", file=sys.stderr)
                continue
            offers_total += len(result.offers)
            total += 1
            out.write(result.model_dump_json() + "\n")
            if total % 25 == 0:
                elapsed = time.time() - started
                rate = total / elapsed if elapsed else 0
                print(f"... {total} msgs · {offers_total} offers · {rate:.1f} msg/s")

    elapsed = time.time() - started
    print(
        f"\nDone. {total} messages processed in {elapsed:.1f}s "
        f"({offers_total} offers extracted, {skipped} skipped). Output: {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
