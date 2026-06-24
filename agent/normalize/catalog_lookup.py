"""
Stage 3 — Product catalog lookup for fuzzy normalization.

Loads gold_product_catalog_normalized from BigQuery once at startup,
then matches extracted product names against all known aliases using
token-sort fuzzy matching (rapidfuzz).

Thresholds:
  >= 0.85 → matched       (auto-accept, goes to comparison)
  >= 0.60 → low_confidence (goes to pending_review queue)
  <  0.60 → unmatched     (discarded, only logged)
"""

from dataclasses import dataclass
from google.cloud import bigquery

try:
    from rapidfuzz import fuzz, process as fuzz_process
except ImportError:
    raise ImportError("pip install rapidfuzz")

THRESHOLD_AUTO   = 85.0
THRESHOLD_REVIEW = 60.0

PROJECT_ID = "cienty-data-platform"
CATALOG_TABLE = f"{PROJECT_ID}.cienty_gold.product_catalog_normalized"


@dataclass
class NormalizeResult:
    ean_matched: str | None
    canonical_name: str | None
    confidence_score: float
    match_status: str  # matched | low_confidence | unmatched


class CatalogLookup:
    """
    Loads the product catalog once and exposes .normalize(product_name_raw).
    Instantiate once per process and reuse — BQ query runs only on __init__.
    """

    def __init__(self, bq_client: bigquery.Client | None = None):
        self._client = bq_client or bigquery.Client(project=PROJECT_ID)
        self._index: list[dict] = []
        self._alias_flat: list[str] = []
        self._alias_meta: list[dict] = []
        self._load()

    def _load(self):
        query = f"""
            SELECT ean, canonical_name, all_aliases
            FROM `{CATALOG_TABLE}`
            WHERE ean IS NOT NULL
        """
        rows = list(self._client.query(query).result())
        for row in rows:
            for alias in (row.all_aliases or []):
                self._alias_flat.append(alias)
                self._alias_meta.append({"ean": row.ean, "canonical_name": row.canonical_name})

    def normalize(self, product_name_raw: str) -> NormalizeResult:
        if not product_name_raw or not self._alias_flat:
            return NormalizeResult(None, None, 0.0, "unmatched")

        query_str = product_name_raw.lower().strip()
        result = fuzz_process.extractOne(
            query_str,
            self._alias_flat,
            scorer=fuzz.token_sort_ratio,
        )

        if result is None:
            return NormalizeResult(None, None, 0.0, "unmatched")

        _best_alias, score, idx = result
        meta = self._alias_meta[idx]

        if score >= THRESHOLD_AUTO:
            status = "matched"
        elif score >= THRESHOLD_REVIEW:
            status = "low_confidence"
        else:
            status = "unmatched"

        return NormalizeResult(
            ean_matched=meta["ean"] if score >= THRESHOLD_REVIEW else None,
            canonical_name=meta["canonical_name"],
            confidence_score=round(score / 100.0, 4),
            match_status=status,
        )
