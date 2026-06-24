data "google_bigquery_dataset" "silver" {
  project    = var.project_id
  dataset_id = "cienty_silver"
}

data "google_bigquery_dataset" "gold" {
  project    = var.project_id
  dataset_id = "cienty_gold"
}

# ─── gold_product_catalog_normalized ───────────────────────────────────────────
resource "google_bigquery_table" "product_catalog_normalized" {
  project             = var.project_id
  dataset_id          = data.google_bigquery_dataset.gold.dataset_id
  table_id            = "product_catalog_normalized"
  deletion_protection = false
  description         = "Lookup de EAN → aliases para fuzzy match no Stage 3 do Agente Captura WhatsApp. Gold layer."

  labels = {
    domain      = "whatsapp_agent"
    load_mode   = "overwrite_daily"
    schedule    = "daily"
    platform    = "agente-captura"
    environment = var.environment
  }

  schema = jsonencode([
    { name = "_ingestion_timestamp", type = "TIMESTAMP", mode = "REQUIRED", description = "Quando foi carregado" },
    { name = "ean",                  type = "STRING",    mode = "REQUIRED", description = "Código EAN do produto" },
    { name = "canonical_name",       type = "STRING",    mode = "NULLABLE", description = "Nome canônico — alias mais frequente na base" },
    { name = "n_distributors",       type = "INTEGER",   mode = "NULLABLE", description = "Nº de distribuidores que oferecem esse EAN" },
    {
      name = "all_aliases", type = "STRING", mode = "REPEATED",
      description = "Todos os aliases conhecidos (internal_code + distributor_product_code + other) em lowercase"
    }
  ])
}

# ─── silver_whatsapp_offers ────────────────────────────────────────────────────
resource "google_bigquery_table" "whatsapp_offers" {
  project             = var.project_id
  dataset_id          = data.google_bigquery_dataset.silver.dataset_id
  table_id            = "whatsapp_offers"
  deletion_protection = false
  description         = "Ofertas estruturadas extraídas de mensagens WhatsApp por LLM. Silver layer do Agente Captura."

  labels = {
    domain      = "whatsapp_agent"
    load_mode   = "append"
    schedule    = "realtime"
    platform    = "agente-captura"
    environment = var.environment
  }

  time_partitioning {
    type  = "DAY"
    field = "received_at"
  }

  clustering = ["match_status", "ean_matched"]

  schema = jsonencode([
    { name = "_ingestion_timestamp", type = "TIMESTAMP", mode = "REQUIRED", description = "Quando o registro foi inserido no BQ" },
    { name = "message_id",           type = "STRING",    mode = "REQUIRED", description = "ID único da mensagem WhatsApp" },
    { name = "source_phone",         type = "STRING",    mode = "NULLABLE", description = "Número do remetente" },
    { name = "received_at",          type = "TIMESTAMP", mode = "REQUIRED", description = "Timestamp de recebimento — campo de partição" },
    { name = "message_type",         type = "STRING",    mode = "NULLABLE", description = "text | image | audio | document" },
    { name = "product_name_raw",     type = "STRING",    mode = "NULLABLE", description = "Nome do produto como veio na mensagem" },
    { name = "price_offered_brl",    type = "FLOAT64",   mode = "NULLABLE", description = "Preço ofertado em BRL" },
    { name = "bonus_type",           type = "STRING",    mode = "NULLABLE", description = "Tipo de bonificação: 1:1, 1:2, 10%, NULL se sem bônus" },
    { name = "bonus_qty",            type = "INTEGER",   mode = "NULLABLE", description = "Qtd do bônus" },
    { name = "min_qty",              type = "INTEGER",   mode = "NULLABLE", description = "Qtd mínima de pedido" },
    { name = "deadline",             type = "TIMESTAMP", mode = "NULLABLE", description = "Validade da oferta" },
    { name = "ean_matched",          type = "STRING",    mode = "NULLABLE", description = "EAN resolvido pelo fuzzy match" },
    { name = "canonical_name",       type = "STRING",    mode = "NULLABLE", description = "Nome canônico na base Cienty" },
    { name = "confidence_score",     type = "FLOAT64",   mode = "NULLABLE", description = "Score 0.0–1.0 do fuzzy match" },
    { name = "match_status",         type = "STRING",    mode = "REQUIRED", description = "matched | low_confidence | unmatched | pending_review" }
  ])
}

# ─── gold_offer_comparison ─────────────────────────────────────────────────────
resource "google_bigquery_table" "offer_comparison" {
  project             = var.project_id
  dataset_id          = data.google_bigquery_dataset.gold.dataset_id
  table_id            = "offer_comparison"
  deletion_protection = false
  description         = "Comparação de ofertas WhatsApp vs. preço Cienty por farmácia elegível. Gold layer do Agente Captura."

  labels = {
    domain      = "whatsapp_agent"
    load_mode   = "rolling_24h"
    schedule    = "30min"
    platform    = "agente-captura"
    environment = var.environment
  }

  schema = jsonencode([
    { name = "_ingestion_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "message_id",           type = "STRING",    mode = "REQUIRED" },
    { name = "received_at",          type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "client_id",            type = "INTEGER",   mode = "REQUIRED", description = "ID da farmácia" },
    { name = "ean",                  type = "STRING",    mode = "REQUIRED" },
    { name = "canonical_name",       type = "STRING",    mode = "NULLABLE" },
    { name = "product_name_raw",     type = "STRING",    mode = "NULLABLE" },
    { name = "confidence_score",     type = "FLOAT64",   mode = "NULLABLE" },
    { name = "price_offered_brl",    type = "FLOAT64",   mode = "NULLABLE" },
    { name = "price_cienty_brl",     type = "FLOAT64",   mode = "NULLABLE", description = "Menor preço Cienty para esse EAN e farmácia" },
    { name = "economy_unit_brl",     type = "FLOAT64",   mode = "NULLABLE", description = "Economia por unidade em BRL" },
    { name = "economy_pct",          type = "FLOAT64",   mode = "NULLABLE", description = "Economia percentual vs. Cienty" },
    { name = "is_better_than_cienty",type = "BOOLEAN",   mode = "NULLABLE" },
    { name = "stock_available",      type = "BOOLEAN",   mode = "NULLABLE" },
    { name = "bonus_type",           type = "STRING",    mode = "NULLABLE" },
    { name = "min_qty",              type = "INTEGER",   mode = "NULLABLE" },
    { name = "deadline",             type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "source_phone",         type = "STRING",    mode = "NULLABLE" },
    { name = "urgency_class",        type = "STRING",    mode = "NULLABLE", description = "urgent | standard | informative" }
  ])

  depends_on = [
    google_bigquery_table.whatsapp_offers,
    google_bigquery_table.product_catalog_normalized
  ]
}
