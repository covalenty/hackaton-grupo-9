"""Build a buyer's history block by querying BigQuery.

Reads the buyer profile YAML, looks up client_ids via buyer_phone_cnpj_map
(fallback to CNPJ lookup), runs the exposure query, and writes the result
back into the YAML's `history:` block.

Usage:
    python scripts/build_buyer_history.py fixtures/profiles/wagno.yaml
    python scripts/build_buyer_history.py fixtures/profiles/wagno.yaml --days 90 --top-n 200
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from google.cloud import bigquery
import yaml

from agent.profile.buyer_profile import load_profile


def _clean_cnpj(cnpj: str) -> str:
    return "".join(ch for ch in cnpj if ch.isdigit())


def _lookup_client_ids(bq: bigquery.Client, cnpjs: list[str]) -> list[tuple[int, str]]:
    """Return (client_id, client_name) tuples for the buyer's CNPJs."""
    clean = [_clean_cnpj(c) for c in cnpjs]
    q = """
    SELECT DISTINCT client_id, client_name, cnpj
    FROM `cienty-data-platform.cienty_silver.buyer_phone_cnpj_map`
    WHERE REGEXP_REPLACE(cnpj, r'[^0-9]', '') IN UNNEST(@cnpjs)
    """
    job = bq.query(
        q,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("cnpjs", "STRING", clean)]
        ),
    )
    return [(r.client_id, r.client_name) for r in job.result() if r.client_id is not None]


def _run_exposure(bq: bigquery.Client, client_ids: list[int], days: int) -> list[dict]:
    sql_path = ROOT / "data" / "sql" / "buyer_exposure.sql"
    sql = sql_path.read_text(encoding="utf-8")
    job = bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("client_ids", "INT64", client_ids),
                bigquery.ScalarQueryParameter("days", "INT64", days),
            ]
        ),
    )
    return [dict(r) for r in job.result()]


def _build_history_block(rows: list[dict], top_n: int) -> dict:
    rows = rows[:top_n]
    exposure_eans: dict[str, int] = {}
    top_categories: dict[str, int] = {}
    for r in rows:
        ean = r.get("ean")
        if not ean:
            continue
        exposure = int(r.get("exposure_days") or 0)
        exposure_eans[ean] = exposure
        cat = r.get("therapeutic_category")
        if cat:
            top_categories[cat] = top_categories.get(cat, 0) + exposure
    return {
        "exposure_eans": exposure_eans,
        "top_categories": top_categories,
        "distinct_eans": len(rows),
        # Empty fields kept for forward-compat — transactions table will fill these later.
        "top_eans": {},
        "monthly_gmv_brl": 0.0,
        "monthly_orders": 0,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("profile", help="Path to a buyer profile YAML")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--top-n", type=int, default=200, help="Keep the top N EANs by exposure")
    p.add_argument("--dry-run", action="store_true", help="Print result, don't write back")
    args = p.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = ROOT / profile_path

    ctx = load_profile(profile_path)
    print(f"[build-history] buyer: {ctx.profile.display_name}")
    print(f"[build-history] CNPJs: {ctx.profile.cnpjs}")

    bq = bigquery.Client(project="cienty-data-platform")

    cnpj_to_client = _lookup_client_ids(bq, ctx.profile.cnpjs)
    if not cnpj_to_client:
        print("ERROR: no client_ids found for these CNPJs in buyer_phone_cnpj_map", file=sys.stderr)
        return 2
    client_ids = sorted({cid for cid, _ in cnpj_to_client})
    for cid, name in cnpj_to_client:
        print(f"  → client_id={cid} ({name})")

    print(f"[build-history] running exposure query (days={args.days})...")
    rows = _run_exposure(bq, client_ids, args.days)
    print(f"  -> {len(rows)} EANs with >= 10 days exposure")

    history = _build_history_block(rows, top_n=args.top_n)
    print(f"  kept top {len(history['exposure_eans'])} EANs · {len(history['top_categories'])} categories")
    if history["top_categories"]:
        top_cats = sorted(history["top_categories"].items(), key=lambda kv: -kv[1])[:5]
        print(f"  top categories: {top_cats}")

    if args.dry_run:
        print("\n--- history block (dry-run) ---")
        print(yaml.safe_dump({"history": history}, allow_unicode=True, sort_keys=False)[:1200])
        return 0

    data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    data["history"] = history
    profile_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"\n[build-history] wrote history block to {profile_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
