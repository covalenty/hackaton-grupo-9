-- Buyer exposure features — proxy for "has Cienty history" when no
-- transactions table is available.
--
-- For one buyer (1+ client_ids) over the last @days days, returns per-EAN
-- and per-category rollups of how many days the EAN was visible with a
-- price across that buyer's distributor portfolio.
--
-- High exposure_days = recurring purchase pattern. Used by relevance.scorer
-- to set has_cienty_history=True when a rep offer matches a known EAN.
--
-- Parameters (named, bound by Python):
--   @client_ids   ARRAY<INT64> — all client_ids operated by this buyer
--   @days         INT64        — window in days (default 90)

WITH win AS (
  SELECT
    cc.client_id,
    cc.ean,
    cc.distributor_id,
    cc.snapshot_date,
    cc.price_final_brl
  FROM `cienty-data-platform.cienty_silver.commercial_conditions` cc
  WHERE cc.client_id IN UNNEST(@client_ids)
    AND cc.snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
    AND cc.price_final_brl IS NOT NULL
    AND cc.price_final_brl > 0
)
SELECT
  w.ean,
  cat.canonical_name,
  cat.therapeutic_category,
  COUNT(DISTINCT w.snapshot_date)  AS exposure_days,
  COUNT(DISTINCT w.distributor_id) AS n_distributors,
  MIN(w.price_final_brl)           AS min_price_seen_brl,
  AVG(w.price_final_brl)           AS avg_price_seen_brl
FROM win w
LEFT JOIN `cienty-data-platform.cienty_gold.product_catalog_normalized` cat
  ON cat.ean = w.ean
GROUP BY w.ean, cat.canonical_name, cat.therapeutic_category
HAVING exposure_days >= 10  -- drop long-tail noise (< 10 days exposure)
ORDER BY exposure_days DESC, n_distributors DESC;
