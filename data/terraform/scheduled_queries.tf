# ─── product_catalog_normalized — diário 04:00 UTC ────────────────────────────
resource "google_bigquery_data_transfer_config" "product_catalog_normalized_daily" {
  project                = var.project_id
  location               = var.bq_location
  display_name           = "Silver → cienty_gold.product_catalog_normalized (daily)"
  data_source_id         = "scheduled_query"
  schedule               = "every day 04:00"
  disabled               = true  # habilitar após validação manual

  destination_dataset_id = ""  # multi-statement DML — deve ser vazio

  params = {
    query = file("${path.module}/../sql/gold_product_catalog_normalized.sql")
  }

  depends_on = [google_bigquery_table.product_catalog_normalized]
}

# ─── offer_comparison — a cada 30 min ─────────────────────────────────────────
resource "google_bigquery_data_transfer_config" "offer_comparison_30min" {
  project                = var.project_id
  location               = var.bq_location
  display_name           = "Silver → cienty_gold.offer_comparison (30min)"
  data_source_id         = "scheduled_query"
  schedule               = "every 30 mins"
  disabled               = true  # habilitar após validação manual

  destination_dataset_id = ""  # multi-statement DML — deve ser vazio

  params = {
    query = file("${path.module}/../sql/gold_offer_comparison.sql")
  }

  depends_on = [
    google_bigquery_table.offer_comparison,
    google_bigquery_table.whatsapp_offers,
    google_bigquery_table.product_catalog_normalized
  ]
}
