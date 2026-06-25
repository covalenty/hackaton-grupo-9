-- ---------------------------------------------------------------------------
-- Gold: cienty_gold.product_catalog_normalized
-- Sources:
--   - cienty_silver.latest_commercial_conditions  (EANs disponíveis na plataforma)
--   - covalenty-prod.covalenty_product_ean        (EAN → product_id)
--   - covalenty-prod.covalenty_product            (product_id → name, categoria)
--
-- Grain: ean (1 linha por produto)
-- Strategy: CREATE OR REPLACE (primeira execução) / TRUNCATE+INSERT (recorrente)
-- Cadência: diária às 04:00 UTC
--
-- canonical_name: nome real do produto (covalenty_product.name).
--   Fallback: distributor_product_code se o produto não existir na tabela de produtos.
--
-- all_aliases: union de name + distributor codes em lowercase para fuzzy match.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TABLE `cienty-data-platform.cienty_gold.product_catalog_normalized`
OPTIONS(
  description = "Lookup EAN → nome real + aliases para fuzzy match no Stage 3 do Agente Captura WhatsApp.",
  labels = [("domain","whatsapp_agent"),("platform","agente-captura")]
)
AS
WITH eans_na_plataforma AS (
  SELECT DISTINCT
    ean,
    distributor_id,
    LOWER(TRIM(internal_code))                  AS internal_code,
    LOWER(TRIM(distributor_product_code))        AS dist_code,
    LOWER(TRIM(distributor_product_code_other))  AS dist_code_other
  FROM `cienty-data-platform.cienty_silver.latest_commercial_conditions`
  WHERE ean IS NOT NULL AND ean != '' AND ean != 'null'
),

produto_nome AS (
  SELECT
    pe.ean,
    TRIM(p.name)                AS product_name,
    LOWER(TRIM(p.name))         AS product_name_lower,
    p.categoria,
    p.therapeutic_category
  FROM `covalenty-prod.app_database_aws_br_covalenty.covalenty_product_ean` pe
  INNER JOIN `covalenty-prod.app_database_aws_br_covalenty.covalenty_product` p
    ON pe.product_id = p.product_id
  WHERE pe.ean IS NOT NULL
    AND TRIM(p.name) != ''
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pe.ean ORDER BY p.product_id) = 1
),

aliases AS (
  SELECT ean, product_name_lower AS alias FROM produto_nome WHERE product_name_lower IS NOT NULL
  UNION DISTINCT
  SELECT ean, internal_code  FROM eans_na_plataforma WHERE internal_code  IS NOT NULL AND internal_code  != ''
  UNION DISTINCT
  SELECT ean, dist_code       FROM eans_na_plataforma WHERE dist_code      IS NOT NULL AND dist_code      != ''
  UNION DISTINCT
  SELECT ean, dist_code_other FROM eans_na_plataforma WHERE dist_code_other IS NOT NULL AND dist_code_other != ''
)

SELECT
  CURRENT_TIMESTAMP()                                                                AS _ingestion_timestamp,
  e.ean,
  COALESCE(ANY_VALUE(n.product_name), ANY_VALUE(e.dist_code), ANY_VALUE(e.internal_code)) AS canonical_name,
  ANY_VALUE(n.categoria)                                                             AS categoria,
  ANY_VALUE(n.therapeutic_category)                                                 AS therapeutic_category,
  COUNT(DISTINCT e.distributor_id)                                                  AS n_distributors,
  ARRAY_AGG(DISTINCT a.alias ORDER BY a.alias)                                      AS all_aliases
FROM eans_na_plataforma e
LEFT JOIN produto_nome n USING (ean)
LEFT JOIN aliases a USING (ean)
GROUP BY e.ean
;
