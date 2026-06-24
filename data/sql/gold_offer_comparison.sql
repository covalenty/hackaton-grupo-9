-- ---------------------------------------------------------------------------
-- Gold: cienty_gold.offer_comparison
--
-- Sources:
--   - cienty_silver.whatsapp_offers           (Stage 3 output)
--   - cienty_silver.latest_commercial_conditions_realtime  (preço real-time)
--   - cienty_gold.recent_stock                (disponibilidade de estoque)
--
-- Grain: (message_id, client_id)
-- Strategy: DELETE últimas 24h + INSERT (idempotente, roda de hora em hora)
-- Cadência: a cada 30 min (scheduled query)
--
-- Purpose: Alimenta o Stage 5 (classificação + alerta) com economia calculada
--   por farmácia. Uma oferta pode gerar N linhas — uma por farmácia elegível
--   que tenha o produto disponível na plataforma Cienty.
--
-- urgency_class:
--   urgent      — oferta melhor que Cienty, estoque ok, dentro do prazo → alerta imediato
--   standard    — melhor que Cienty mas sem urgência de prazo → feed do dia
--   informative — preço similar ou pior → só registra, vira dado de mercado
-- ---------------------------------------------------------------------------

DECLARE cutoff_ts TIMESTAMP;
SET cutoff_ts = TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR);

DELETE FROM `cienty-data-platform.cienty_gold.offer_comparison`
WHERE received_at >= cutoff_ts;

INSERT INTO `cienty-data-platform.cienty_gold.offer_comparison`
WITH offers AS (
  SELECT
    message_id,
    source_phone,
    received_at,
    product_name_raw,
    ean_matched           AS ean,
    canonical_name,
    confidence_score,
    price_offered_brl,
    bonus_type,
    min_qty,
    deadline
  FROM `cienty-data-platform.cienty_silver.whatsapp_offers`
  WHERE received_at       >= cutoff_ts
    AND match_status       = 'matched'
    AND ean_matched        IS NOT NULL
    AND price_offered_brl  > 0
),

cienty_best AS (
  SELECT
    client_id,
    ean,
    MIN(price_final_brl)                                AS price_cienty_brl,
    MIN(IF(stock > 0, price_final_brl, NULL))           AS price_cienty_in_stock_brl,
    MAX(stock)                                          AS max_stock
  FROM `cienty-data-platform.cienty_silver.latest_commercial_conditions_realtime`
  WHERE price_final_brl > 0
  GROUP BY client_id, ean
)

SELECT
  CURRENT_TIMESTAMP()                                                     AS _ingestion_timestamp,
  o.message_id,
  o.received_at,
  p.client_id,
  o.ean,
  o.canonical_name,
  o.product_name_raw,
  o.confidence_score,
  o.price_offered_brl,
  p.price_cienty_brl,
  ROUND(p.price_cienty_brl - o.price_offered_brl, 2)                     AS economy_unit_brl,
  ROUND(
    SAFE_DIVIDE(p.price_cienty_brl - o.price_offered_brl, p.price_cienty_brl) * 100,
    1
  )                                                                        AS economy_pct,
  o.price_offered_brl < p.price_cienty_brl                                AS is_better_than_cienty,
  COALESCE(p.max_stock > 0, FALSE)                                         AS stock_available,
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
  END                                                                      AS urgency_class
FROM offers o
INNER JOIN cienty_best p USING (ean)
;
