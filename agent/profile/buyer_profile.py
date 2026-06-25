"""Buyer profile loader.

A profile maps one buyer (e.g. Wagno @ Farmaestra) to:
  - their CNPJs (1+ stores)
  - phones they use on WhatsApp
  - name aliases that appear as sender ("WAGNO", "C Cienty", "C Comprador")
  - cached purchase history features (from Cienty BQ)

The history features are loaded lazily — relevance scoring calls
`load_history_from_bq(profile, bq_client)` which runs the SQL in
`data/sql/buyer_history.sql` and caches the result.

For dev/eval without BQ access, you can pre-bake a YAML with a `history` block.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from ..schemas import BuyerProfile


class BuyerHistoryFeatures(BaseModel):
    """Per-buyer aggregates used by relevance scoring.

    Computed across all CNPJs of the buyer, last 180 days of Cienty orders.
    """
    top_eans: dict[str, int] = Field(
        default_factory=dict,
        description="EAN → total qty purchased in the window. Used to score 'they buy this'.",
    )
    top_categories: dict[str, int] = Field(
        default_factory=dict,
        description="therapeutic_category → total qty. Used to score 'they buy in this category'.",
    )
    monthly_gmv_brl: float = 0.0
    monthly_orders: int = 0
    distinct_eans: int = 0


class BuyerContext(BaseModel):
    """Profile + (optionally) loaded history features."""
    profile: BuyerProfile
    history: Optional[BuyerHistoryFeatures] = None
    requested_eans: set[str] = Field(
        default_factory=set,
        description="EANs the buyer has requested on WhatsApp (from buyer_request rows).",
    )

    model_config = {"arbitrary_types_allowed": True}


def load_profile(path: str | Path) -> BuyerContext:
    """Load a buyer profile from YAML. Includes baked history if present."""
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    profile = BuyerProfile(**data["profile"])
    history = BuyerHistoryFeatures(**data["history"]) if "history" in data else None
    return BuyerContext(profile=profile, history=history)


def load_history_from_bq(
    profile: BuyerProfile,
    bq_client: Any,
    days: int = 180,
    sql_path: str | Path = "data/sql/buyer_history.sql",
) -> BuyerHistoryFeatures:
    """Run buyer_history.sql against Cienty BQ and return aggregated features.

    Joins orders × order_items × product_catalog_normalized filtered by buyer
    CNPJs, in the last `days` window.
    """
    sql = Path(sql_path).read_text(encoding="utf-8")
    params = {
        "cnpjs": profile.cnpjs,
        "days": days,
    }
    result = bq_client.query(sql, params=params).result()
    top_eans, top_cats = {}, {}
    gmv, n_orders, n_eans = 0.0, 0, 0
    for row in result:
        top_eans[row.ean] = row.qty_total
        top_cats[row.therapeutic_category] = top_cats.get(row.therapeutic_category, 0) + row.qty_total
        gmv += row.gmv_brl
        n_orders = max(n_orders, row.distinct_orders)
        n_eans += 1
    return BuyerHistoryFeatures(
        top_eans=top_eans,
        top_categories=top_cats,
        monthly_gmv_brl=gmv / (days / 30),
        monthly_orders=int(n_orders / (days / 30)),
        distinct_eans=n_eans,
    )
