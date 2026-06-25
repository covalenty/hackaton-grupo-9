-- Demanda não atendida: produtos que o buyer PERGUNTOU no Zap e
-- NÃO comprou na Cienty no mesmo período.
--
-- Saída deste view alimenta o produto + comercial Cienty:
--   "esses são os EANs que o cliente quer e a gente não está vendendo pra ele".
--
-- Cria como view gold:
--   cienty_gold.buyer_unmet_demand

CREATE OR REPLACE VIEW `cienty-data-platform.cienty_gold.buyer_unmet_demand` AS
WITH requests AS (
  SELECT
    r.source_phone,
    r.ean_matched               AS ean,
    COUNT(*)                    AS n_requests,
    SUM(IFNULL(r.requested_qty, 0)) AS qty_requested_total,
    MIN(r.received_at)          AS first_requested_at,
    MAX(r.received_at)          AS last_requested_at
  FROM `cienty-data-platform.cienty_silver.whatsapp_offers` r
  WHERE r.direction = 'buyer_request'
    AND r.match_status = 'matched'
  GROUP BY r.source_phone, r.ean_matched
),
buyer_purchases AS (
  SELECT DISTINCT o.cnpj, i.ean
  FROM `cienty-data-platform.cienty_silver.orders` o
  JOIN `cienty-data-platform.cienty_silver.order_items` i USING (order_id)
  WHERE o.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
),
phone_to_cnpj AS (
  -- Maps source_phone → CNPJs of that buyer. Populated by Cienty's buyer-profile
  -- registry (see fixtures/profiles/*.yaml).
  SELECT phone AS source_phone, cnpj
  FROM `cienty-data-platform.cienty_silver.buyer_phone_cnpj_map`
)
SELECT
  r.source_phone,
  m.cnpj,
  r.ean,
  cat.canonical_name,
  cat.therapeutic_category,
  r.n_requests,
  r.qty_requested_total,
  r.first_requested_at,
  r.last_requested_at,
  (bp.ean IS NULL) AS is_unmet
FROM requests r
LEFT JOIN phone_to_cnpj m ON m.source_phone = r.source_phone
LEFT JOIN buyer_purchases bp ON bp.cnpj = m.cnpj AND bp.ean = r.ean
LEFT JOIN `cienty-data-platform.cienty_gold.product_catalog_normalized` cat ON cat.ean = r.ean
WHERE bp.ean IS NULL;  -- only the unmet ones
