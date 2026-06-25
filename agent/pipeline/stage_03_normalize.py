"""
Stage 3 — Normalization

Receives the structured extraction from Stage 2 (LLM output),
runs fuzzy match against gold_product_catalog_normalized,
and writes the result to cienty_silver.whatsapp_offers.
"""

from datetime import datetime, timezone
from google.cloud import bigquery
from agent.normalize import CatalogLookup

PROJECT_ID    = "cienty-data-platform"
OFFERS_TABLE  = f"{PROJECT_ID}.cienty_silver.whatsapp_offers"

# Shared catalog — loaded once per process
_catalog: CatalogLookup | None = None


def get_catalog(bq_client: bigquery.Client) -> CatalogLookup:
    global _catalog
    if _catalog is None:
        _catalog = CatalogLookup(bq_client)
    return _catalog


def run(extraction: dict, bq_client: bigquery.Client) -> dict:
    """
    Args:
        extraction: output from Stage 2 with keys:
            message_id, source_phone, received_at, message_type,
            product_name_raw, price_offered_brl, bonus_type, bonus_qty,
            min_qty, deadline
        bq_client: BigQuery client

    Returns:
        The full row dict written to silver_whatsapp_offers.
    """
    catalog = get_catalog(bq_client)
    match = catalog.normalize(extraction.get("product_name_raw", ""))

    row = {
        "_ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id":           extraction["message_id"],
        "source_phone":         extraction.get("source_phone"),
        "received_at":          extraction["received_at"].isoformat() if isinstance(extraction["received_at"], datetime) else extraction["received_at"],
        "message_type":         extraction.get("message_type", "text"),
        "product_name_raw":     extraction.get("product_name_raw"),
        "price_offered_brl":    extraction.get("price_offered_brl"),
        "bonus_type":           extraction.get("bonus_type"),
        "bonus_qty":            extraction.get("bonus_qty"),
        "min_qty":              extraction.get("min_qty"),
        "deadline":             extraction.get("deadline").isoformat() if isinstance(extraction.get("deadline"), datetime) else extraction.get("deadline"),
        "direction":            extraction.get("direction", "rep_offer"),
        "requested_qty":        extraction.get("requested_qty"),
        "ean_matched":          match.ean_matched,
        "canonical_name":       match.canonical_name,
        "confidence_score":     match.confidence_score,
        "match_status":         match.match_status,
    }

    errors = bq_client.insert_rows_json(OFFERS_TABLE, [row])
    if errors:
        raise RuntimeError(f"BQ insert error: {errors}")

    return row
