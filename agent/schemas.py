"""Schemas for the WhatsApp capture pipeline.

Mirrors `cienty_silver.whatsapp_offers` so Stage 2 output drops straight in.

Important: rows have a `direction` field.
  - rep_offer:     rep is offering a product (typical push from MILFARMA, Eduardo, etc.)
  - buyer_request: the buyer (e.g. Wagno) is asking reps for a quote.

Both flow into the same silver table. Stage 4 (comparison) only acts on rep_offer rows.
buyer_request rows feed a separate gold view: "demanda que o cliente pede e a gente
não atende" — pure intent signal pra produto/comercial Cienty.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"
    EXCEL = "excel"
    AUDIO = "audio"


class Direction(str, Enum):
    REP_OFFER = "rep_offer"
    BUYER_REQUEST = "buyer_request"


class BonusType(str, Enum):
    NONE = "none"
    QTY = "qty"           # ex: 1:1, 1:2 — same SKU
    CROSS = "cross"       # ex: compra Cimegrip ganha Narix
    PCT = "pct"           # ex: 10% desconto


class RawMessage(BaseModel):
    """One line of a WhatsApp export, parsed."""
    message_id: str
    source_phone: Optional[str] = None
    source_name: Optional[str] = None      # ex: "Eduardo MILFARMA"
    group_name: Optional[str] = None       # ex: "PROMOÇÕES MILFARMA"
    received_at: datetime
    body: str
    has_media: bool = False
    message_type: MessageType = MessageType.TEXT
    is_from_buyer: bool = Field(
        False,
        description="True when the sender is the buyer (Wagno). Set by parser using known buyer aliases.",
    )


class ExtractedOffer(BaseModel):
    """One offer or request extracted from a message. Maps to silver.whatsapp_offers."""
    message_id: str
    source_phone: Optional[str] = None
    received_at: datetime
    message_type: MessageType = MessageType.TEXT
    direction: Direction = Direction.REP_OFFER

    product_name_raw: str = Field(..., description="Product name as written in the message, verbatim")

    # Rep-offer fields (null when direction=buyer_request)
    price_offered_brl: Optional[float] = Field(None, description="Unit price in BRL, decimal")
    bonus_type: BonusType = BonusType.NONE
    bonus_qty: Optional[int] = Field(None, description="Bonus quantity (e.g., 1 for 1:1)")
    bonus_target_product: Optional[str] = Field(None, description="For CROSS bonus, the gifted SKU")
    min_qty: Optional[int] = Field(None, description="Minimum order quantity")
    deadline: Optional[datetime] = Field(None, description="Offer validity end")

    # Buyer-request field (null when direction=rep_offer)
    requested_qty: Optional[int] = Field(None, description="Quantity the buyer is asking for, if mentioned")

    extraction_confidence: float = Field(1.0, ge=0.0, le=1.0)
    extraction_notes: Optional[str] = None


class ExtractionResult(BaseModel):
    """Full Stage 2 output for one message — zero, one, or many offers/requests."""
    message_id: str
    offers: list[ExtractedOffer] = Field(default_factory=list)
    is_offer_message: bool = Field(
        ...,
        description="True when offers list has at least one item (rep_offer OR buyer_request).",
    )
    skip_reason: Optional[str] = Field(
        None,
        description="If is_offer_message=False, brief reason (saudação | logística | confirmação | outro)",
    )


# ============================================================================
# Buyer profile + relevance — for alert filtering
# ============================================================================


class BuyerProfile(BaseModel):
    """Static-ish profile of a buyer (one farmácia). Multiple CNPJs possible."""
    buyer_id: str = Field(..., description="Stable internal id, e.g. 'farmaestra'")
    display_name: str
    cnpjs: list[str] = Field(default_factory=list, description="All CNPJs operated by this buyer")
    source_phones: list[str] = Field(
        default_factory=list,
        description="Phones the buyer SENDS FROM (used to detect is_from_buyer in incoming msgs).",
    )
    alert_destination_phone: Optional[str] = Field(
        None,
        description="Phone to RECEIVE alerts. For hackathon = same Cienty number "
                    "(self-chat demo). Production = the buyer's personal phone.",
    )
    buyer_name_aliases: list[str] = Field(
        default_factory=list,
        description="Names that appear as sender when this buyer is talking (e.g. 'WAGNO', 'C Cienty')",
    )


class RelevanceBand(str, Enum):
    URGENT = "urgent"                 # rep barato vs Cienty, alerta agora
    HIGH = "high"                     # rep barato vs Cienty, alerta padrão
    CIENTY_BETTER = "cienty_better"   # rep PIOR que Cienty — alerta a comprar via plataforma (defende GMV)
    MEDIUM = "medium"                 # preço similar, só entra no feed
    LOW = "low"                       # só registra
    SKIP = "skip"                     # ruído, não loga


class RelevanceScore(BaseModel):
    """Output of relevance scoring — used by stage 5 (delivery) to decide alert mode."""
    offer_message_id: str
    ean_matched: Optional[str] = None
    score: float = Field(..., ge=0.0, le=1.0)
    band: RelevanceBand
    signals: dict = Field(
        default_factory=dict,
        description="Breakdown: has_cienty_history, has_buyer_request, volume_band, category_match, economy_pct",
    )
    reason: str = Field(..., description="One-line human explanation")
