-- Buyer purchase history aggregates.
--
-- Joins orders × order_items × product_catalog_normalized for one buyer
-- (1+ CNPJs) over the last @days days. Returns per-EAN rollups so the
-- relevance module can score offers against actual buying behavior.
--
-- Parameters (named, bound by Python):
--   @cnpjs  ARRAY<STRING> — all CNPJs operated by this buyer
--   @days   INT64         — window in days (default 180)
--
-- Adjust table names to match cienty-data-platform conventions. The columns
-- below assume:
--   cienty_silver.orders(order_id, cnpj, created_at, gmv_brl)
--   cienty_silver.order_items(order_id, ean, qty, unit_price_brl)
--   cienty_gold.product_catalog_normalized(ean, therapeutic_category, canonical_name)

WITH win AS (
  SELECT
    o.order_id,
    o.cnpj,
    o.created_at,
    o.gmv_brl,
    i.ean,
    i.qty,
    i.unit_price_brl
  FROM `cienty-data-platform.cienty_silver.orders` o
  JOIN `cienty-data-platform.cienty_silver.order_items` i USING (order_id)
  WHERE o.cnpj IN UNNEST(@cnpjs)
    AND o.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
)
SELECT
  w.ean,
  cat.therapeutic_category,
  cat.canonical_name,
  SUM(w.qty)                     AS qty_total,
  SUM(w.qty * w.unit_price_brl)  AS gmv_brl,
  COUNT(DISTINCT w.order_id)     AS distinct_orders,
  MAX(w.created_at)              AS last_purchased_at
FROM win w
LEFT JOIN `cienty-data-platform.cienty_gold.product_catalog_normalized` cat
  ON cat.ean = w.ean
GROUP BY w.ean, cat.therapeutic_category, cat.canonical_name
ORDER BY qty_total DESC;
