-- ---------------------------------------------------------------------------
-- Silver: cienty_silver.whatsapp_offers
--
-- Grain: message_id (1 linha por mensagem processada)
-- Strategy: APPEND — dados inseridos pelo pipeline do agente após Stage 3
-- Partição: received_at (DAY)
-- Clustering: match_status, ean_matched
--
-- Purpose: Persistir o output estruturado do LLM (Stage 2 → 3).
--   Cada mensagem WhatsApp recebida vira 1 linha com produto extraído,
--   EAN normalizado, preço, bonificação e score de confiança do match.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `cienty-data-platform.cienty_silver.whatsapp_offers`
(
  _ingestion_timestamp  TIMESTAMP NOT NULL    OPTIONS(description="Quando o registro foi inserido no BQ"),
  message_id            STRING    NOT NULL    OPTIONS(description="ID único da mensagem WhatsApp"),
  source_phone          STRING                OPTIONS(description="Número do remetente — rep ou distribuidor"),
  received_at           TIMESTAMP NOT NULL    OPTIONS(description="Timestamp de recebimento — campo de partição"),
  message_type          STRING                OPTIONS(description="text | image | audio | document"),

  -- Extração (Stage 2 — LLM output)
  product_name_raw      STRING                OPTIONS(description="Nome do produto exatamente como veio na mensagem"),
  price_offered_brl     FLOAT64               OPTIONS(description="Preço ofertado em BRL"),
  bonus_type            STRING                OPTIONS(description="Tipo de bonificação: 1:1, 1:2, 10%, NULL se sem bônus"),
  bonus_qty             INT64                 OPTIONS(description="Qtd do bônus — ex: 1 para 1:1, 2 para 1:2"),
  min_qty               INT64                 OPTIONS(description="Qtd mínima de pedido"),
  deadline              TIMESTAMP             OPTIONS(description="Validade da oferta — NULL se não informada"),

  -- Normalização (Stage 3 — fuzzy match contra gold_product_catalog_normalized)
  ean_matched           STRING                OPTIONS(description="EAN resolvido — NULL se não encontrou match acima do corte"),
  canonical_name        STRING                OPTIONS(description="Nome canônico na base Cienty após normalização"),
  confidence_score      FLOAT64               OPTIONS(description="Score 0.0–1.0 do fuzzy match. >= 0.85: automático; >= 0.60: revisão; < 0.60: descartado"),
  match_status          STRING    NOT NULL    OPTIONS(description="matched | low_confidence | unmatched | pending_review")
)
PARTITION BY DATE(received_at)
CLUSTER BY match_status, ean_matched
OPTIONS(
  description="Ofertas estruturadas extraídas de mensagens WhatsApp. Silver layer do Agente Captura."
);
