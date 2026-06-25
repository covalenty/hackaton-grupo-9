-- ---------------------------------------------------------------------------
-- INIT — execução única para criar as 3 tabelas.
-- Após esse script, usar os SQLs individuais para reprocessar.
-- ---------------------------------------------------------------------------

-- 1. gold_product_catalog_normalized (ver gold_product_catalog_normalized.sql para o SQL completo)
-- Já criada e populada. Reprocessar rodando gold_product_catalog_normalized.sql diretamente.

-- 2. silver_whatsapp_offers (schema only — dados vêm do pipeline)
CREATE TABLE IF NOT EXISTS `cienty-data-platform.cienty_silver.whatsapp_offers`
(
  _ingestion_timestamp  TIMESTAMP NOT NULL,
  message_id            STRING    NOT NULL,
  source_phone          STRING,
  received_at           TIMESTAMP NOT NULL,
  message_type          STRING,
  product_name_raw      STRING,
  price_offered_brl     FLOAT64,
  bonus_type            STRING,
  bonus_qty             INT64,
  min_qty               INT64,
  deadline              TIMESTAMP,
  ean_matched           STRING,
  canonical_name        STRING,
  confidence_score      FLOAT64,
  match_status          STRING    NOT NULL
)
PARTITION BY DATE(received_at)
CLUSTER BY match_status, ean_matched
OPTIONS(description="Ofertas estruturadas extraídas de mensagens WhatsApp. Silver layer do Agente Captura.");

-- 3. gold_offer_comparison (schema only — populada por gold_offer_comparison.sql)
CREATE TABLE IF NOT EXISTS `cienty-data-platform.cienty_gold.offer_comparison`
(
  _ingestion_timestamp  TIMESTAMP NOT NULL,
  message_id            STRING    NOT NULL,
  received_at           TIMESTAMP NOT NULL,
  client_id             INT64     NOT NULL,
  ean                   STRING    NOT NULL,
  canonical_name        STRING,
  product_name_raw      STRING,
  confidence_score      FLOAT64,
  price_offered_brl     FLOAT64,
  price_cienty_brl      FLOAT64,
  economy_unit_brl      FLOAT64,
  economy_pct           FLOAT64,
  is_better_than_cienty BOOL,
  stock_available       BOOL,
  bonus_type            STRING,
  min_qty               INT64,
  deadline              TIMESTAMP,
  source_phone          STRING,
  urgency_class         STRING
)
OPTIONS(description="Comparação oferta WhatsApp vs. preço Cienty por farmácia. Gold layer do Agente Captura.");
