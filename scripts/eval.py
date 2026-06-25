"""Evaluate Stage 2 against fixtures/gold.jsonl.

Usage:
    python scripts/eval.py

Prints per-fixture pass/fail and a final summary. Exit code 1 if any fail.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.schemas import RawMessage  # noqa: E402
from agent.pipeline.stage_02_extract import extract  # noqa: E402


def _make_id(received_at: datetime, sender: str | None, body: str) -> str:
    seed = f"{received_at.isoformat()}|{sender or ''}|{body[:200]}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _check_prices(offers, expected_prices: dict) -> tuple[int, int, list[str]]:
    """Check that each expected product+price appears in offers (loose match on name)."""
    hits, misses, errors = 0, 0, []
    for expected_name, expected_price in expected_prices.items():
        match = None
        for o in offers:
            if any(word.lower() in o.product_name_raw.lower() for word in expected_name.split()[:2]):
                if o.price_offered_brl is not None and abs(o.price_offered_brl - expected_price) < 0.01:
                    match = o
                    break
        if match:
            hits += 1
        else:
            misses += 1
            best = next(
                (o for o in offers if expected_name.split()[0].lower() in o.product_name_raw.lower()),
                None,
            )
            got_price = best.price_offered_brl if best else None
            errors.append(f"  miss · {expected_name} → expected R$ {expected_price} got R$ {got_price}")
    return hits, misses, errors


def evaluate_fixture(fx: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    received_at = datetime.fromisoformat(fx["received_at"])
    msg = RawMessage(
        message_id=_make_id(received_at, fx["sender"], fx["body"]),
        source_name=fx["sender"],
        received_at=received_at,
        body=fx["body"],
        is_from_buyer=fx.get("is_from_buyer", False),
    )
    result = extract(msg, use_cache=True)
    expected = fx["expected"]

    if result.is_offer_message != expected["is_offer_message"]:
        issues.append(
            f"  is_offer_message: expected {expected['is_offer_message']} got {result.is_offer_message}"
        )

    if "skip_reason_contains" in expected and result.skip_reason:
        if not any(needle.lower() in (result.skip_reason or "").lower() for needle in expected["skip_reason_contains"]):
            issues.append(
                f"  skip_reason '{result.skip_reason}' didn't match any of {expected['skip_reason_contains']}"
            )

    if "n_offers" in expected:
        if len(result.offers) != expected["n_offers"]:
            issues.append(f"  n_offers: expected {expected['n_offers']} got {len(result.offers)}")
    if "n_offers_min" in expected:
        if len(result.offers) < expected["n_offers_min"]:
            issues.append(f"  n_offers: expected >= {expected['n_offers_min']} got {len(result.offers)}")

    if "products_must_contain" in expected:
        names = " | ".join(o.product_name_raw for o in result.offers).lower()
        for product in expected["products_must_contain"]:
            if product.lower() not in names:
                issues.append(f"  missing product: {product}")

    if "prices" in expected:
        hits, misses, errors = _check_prices(result.offers, expected["prices"])
        if misses:
            issues.extend(errors)

    if "direction_all" in expected:
        wrong = [o for o in result.offers if o.direction.value != expected["direction_all"]]
        if wrong:
            issues.append(f"  direction: expected all={expected['direction_all']} got {[o.direction.value for o in wrong]}")

    if "requested_qty_must_appear" in expected:
        target = expected["requested_qty_must_appear"]
        if not any(o.requested_qty == target for o in result.offers):
            issues.append(f"  no offer with requested_qty={target}")

    return (len(issues) == 0, issues)


def main() -> int:
    fixtures_path = ROOT / "fixtures" / "gold.jsonl"
    fixtures = [json.loads(line) for line in fixtures_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    passed, failed = 0, 0
    print(f"Running {len(fixtures)} fixtures...\n")
    for fx in fixtures:
        ok, issues = evaluate_fixture(fx)
        if ok:
            print(f"  ✓ {fx['id']}")
            passed += 1
        else:
            print(f"  ✕ {fx['id']}")
            for line in issues:
                print(line)
            failed += 1

    print(f"\n{passed} passed · {failed} failed · {len(fixtures)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
