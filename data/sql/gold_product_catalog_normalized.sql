-- ---------------------------------------------------------------------------
-- Gold: cienty_gold.product_catalog_normalized
-- Source: cienty_silver.latest_commercial_conditions
--
-- Grain: ean (1 linha por produto)
-- Strategy: TRUNCATE + INSERT (diário, roda após latest_commercial_conditions)
-- Cadência: diária às 04:00 UTC
--
-- Purpose: Lookup table para o Stage 3 (normalização) do Agente Captura WhatsApp.
--   Agrega todos os aliases conhecidos de cada EAN (internal_code,
--   distributor_product_code, distributor_product_code_other) para viabilizar
--   fuzzy matching entre o nome extraído pelo LLM e o EAN correto na base Cienty.
-- ---------------------------------------------------------------------------

TRUNCATE TABLE `cienty-data-platform.cienty_gold.product_catalog_normalized`;

INSERT INTO `cienty-data-platform.cienty_gold.product_catalog_normalized`
WITH base AS (
  SELECT DISTINCT
    ean,
    distributor_id,
    LOWER(TRIM(internal_code))                  AS internal_code,
    LOWER(TRIM(distributor_product_code))        AS dist_code,
    LOWER(TRIM(distributor_product_code_other))  AS dist_code_other
  FROM `cienty-data-platform.cienty_silver.latest_commercial_conditions`
  WHERE ean IS NOT NULL
    AND ean != ''
),

aliases AS (
  SELECT ean, internal_code AS alias FROM base WHERE internal_code  IS NOT NULL AND internal_code  != ''
  UNION DISTINCT
  SELECT ean, dist_code               FROM base WHERE dist_code      IS NOT NULL AND dist_code      != ''
  UNION DISTINCT
  SELECT ean, dist_code_other         FROM base WHERE dist_code_other IS NOT NULL AND dist_code_other != ''
),

alias_freq AS (
  SELECT
    ean,
    alias,
    COUNT(*) AS freq
  FROM aliases
  GROUP BY ean, alias
),

canonical AS (
  SELECT ean, alias AS canonical_name
  FROM (
    SELECT
      ean,
      alias,
      ROW_NUMBER() OVER (PARTITION BY ean ORDER BY freq DESC, alias) AS rn
    FROM alias_freq
  )
  WHERE rn = 1
)

SELECT
  CURRENT_TIMESTAMP()                              AS _ingestion_timestamp,
  b.ean,
  c.canonical_name,
  COUNT(DISTINCT b.distributor_id)                 AS n_distributors,
  ARRAY_AGG(DISTINCT a.alias ORDER BY a.alias)     AS all_aliases
FROM base b
LEFT JOIN aliases  a USING (ean)
LEFT JOIN canonical c USING (ean)
GROUP BY b.ean, c.canonical_name
;
