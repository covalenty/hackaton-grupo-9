"""
Stage 4 — Real-time price comparison

For a given message_id (already in silver_whatsapp_offers with match_status='matched'),
queries latest_commercial_conditions_realtime and computes economy_brl + urgency_class
for every eligible pharmacy.

Returns the comparison rows so Stage 5 can classify and dispatch alerts.
The same result is persisted to gold_offer_comparison by the 30-min scheduled query,
but this function gives Stage 5 immediate access without waiting for the schedule.
"""

from google.cloud import bigquery

PROJECT_ID = "cienty-data-platform"


def run(message_id: str, bq_client: bigquery.Client) -> list[dict]:
    """
    Returns list of comparison dicts, one per eligible pharmacy.
    Each dict has: client_id, ean, economy_unit_brl, economy_pct,
                   is_better_than_cienty, stock_available, urgency_class, ...
    """
    query = """
        WITH offer AS (
          SELECT
            message_id,
            received_at,
            ean_matched       AS ean,
            canonical_name,
            product_name_raw,
            confidence_score,
            price_offered_brl,
            bonus_type,
            min_qty,
            deadline,
            source_phone
          FROM `cienty-data-platform.cienty_silver.whatsapp_offers`
          WHERE message_id   = @message_id
            AND match_status = 'matched'
            AND IFNULL(direction, 'rep_offer') = 'rep_offer'
          LIMIT 1
        ),

        cienty_best AS (
          SELECT
            client_id,
            ean,
            MIN(price_final_brl)                          AS price_cienty_brl,
            MAX(stock)                                    AS max_stock
          FROM `cienty-data-platform.cienty_silver.latest_commercial_conditions_realtime`
          WHERE price_final_brl > 0
          GROUP BY client_id, ean
        )

        SELECT
          o.message_id,
          o.received_at,
          p.client_id,
          o.ean,
          o.canonical_name,
          o.product_name_raw,
          o.confidence_score,
          o.price_offered_brl,
          p.price_cienty_brl,
          ROUND(p.price_cienty_brl - o.price_offered_brl, 2)   AS economy_unit_brl,
          ROUND(
            SAFE_DIVIDE(p.price_cienty_brl - o.price_offered_brl, p.price_cienty_brl) * 100,
            1
          )                                                      AS economy_pct,
          o.price_offered_brl < p.price_cienty_brl              AS is_better_than_cienty,
          COALESCE(p.max_stock > 0, FALSE)                       AS stock_available,
          o.bonus_type,
          o.min_qty,
          o.deadline,
          o.source_phone,
          CASE
            WHEN o.price_offered_brl < p.price_cienty_brl
              AND COALESCE(p.max_stock > 0, FALSE)
              AND (o.deadline IS NULL OR o.deadline > CURRENT_TIMESTAMP())
            THEN 'urgent'
            WHEN o.price_offered_brl < p.price_cienty_brl
            THEN 'standard'
            ELSE 'informative'
          END AS urgency_class
        FROM offer o
        INNER JOIN cienty_best p USING (ean)
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("message_id", "STRING", message_id)
        ]
    )

    return [dict(row) for row in bq_client.query(query, job_config=job_config).result()]
