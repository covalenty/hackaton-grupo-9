"""Standalone: extract offers from a local image (JPG/PNG) using Stage 2 vision.

Useful for debugging vision extraction without needing the WhatsApp bridge.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/extract_image.py path/to/image.jpg
    python scripts/extract_image.py image.jpg --caption "$13,49 para 24un / $12,99 para 60un"
    python scripts/extract_image.py image.jpg --sender "Paulinho Navarro" --no-cache
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from agent.pipeline.stage_02_extract import extract  # noqa: E402
from agent.schemas import MessageType, RawMessage  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("image", help="Path to a JPG / PNG file")
    p.add_argument("--caption", default="", help="Text caption sent with the image")
    p.add_argument("--sender", default="Paulinho Navarro", help="Sender name (rep)")
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args()

    path = Path(args.image)
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2

    msg = RawMessage(
        message_id=f"img-{path.stem}",
        source_name=args.sender,
        received_at=datetime.now(tz=timezone.utc),
        body=args.caption,
        has_media=True,
        message_type=MessageType.IMAGE,
        media_paths=[str(path.resolve())],
    )

    print(f"[extract] {path.name} · sender={args.sender!r} · caption={args.caption!r}")
    result = extract(msg, use_cache=not args.no_cache)
    print()
    print(f"is_offer_message: {result.is_offer_message}")
    if result.skip_reason:
        print(f"skip_reason: {result.skip_reason}")
    print(f"offers: {len(result.offers)}")
    print()
    for i, o in enumerate(result.offers, 1):
        d = o.model_dump(exclude_none=True, exclude={"message_id", "source_phone", "received_at", "message_type"})
        print(f"--- offer {i} ---")
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
