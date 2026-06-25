"""Format alert text for delivery via WhatsApp.

Takes the rep offer + Cienty comparison + relevance score and produces a
human-readable WhatsApp message in PT-BR.

WhatsApp formatting that survives: *bold*, _italic_, ```mono```. We use *bold*
sparingly for the bottom-line economy figure.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import ExtractedOffer, RelevanceBand, RelevanceScore


def _fmt_brl(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _band_emoji(band: RelevanceBand) -> str:
    return {
        RelevanceBand.URGENT: "🚨",
        RelevanceBand.HIGH: "⚡",
        RelevanceBand.MEDIUM: "📌",
        RelevanceBand.LOW: "💬",
        RelevanceBand.SKIP: "·",
    }.get(band, "·")


def format_alert(
    *,
    offer: ExtractedOffer,
    canonical_name: Optional[str],
    price_cienty_brl: Optional[float],
    economy_unit_brl: Optional[float],
    economy_pct: Optional[float],
    relevance: RelevanceScore,
    rep_name: Optional[str] = None,
) -> str:
    """Build the WhatsApp message body for one alert."""
    emoji = _band_emoji(relevance.band)
    product = canonical_name or offer.product_name_raw
    lines: list[str] = []
    header = f"{emoji} *{relevance.band.value.upper()}*"
    if rep_name:
        header += f" · {rep_name}"
    lines.append(header)
    lines.append("")
    lines.append(f"*{product}*")
    if canonical_name and canonical_name.lower() != offer.product_name_raw.lower():
        lines.append(f"_({offer.product_name_raw})_")

    if offer.price_offered_brl is not None:
        lines.append(f"Oferta: {_fmt_brl(offer.price_offered_brl)}/un")
    if price_cienty_brl is not None:
        lines.append(f"Cienty hoje: {_fmt_brl(price_cienty_brl)}/un")

    if offer.bonus_type.value != "none":
        bonus_line = "Bonificação: "
        if offer.bonus_type.value == "qty" and offer.bonus_qty:
            bonus_line += f"1:{offer.bonus_qty}"
        elif offer.bonus_type.value == "cross" and offer.bonus_target_product:
            bonus_line += f"+{offer.bonus_target_product}"
        elif offer.bonus_type.value == "pct":
            bonus_line += "desconto %"
        else:
            bonus_line += offer.bonus_type.value
        lines.append(bonus_line)

    if offer.min_qty:
        lines.append(f"Mínimo: {offer.min_qty} un")
    if offer.deadline:
        lines.append(f"Válido até: {offer.deadline.strftime('%d/%m %H:%M')}")

    if economy_unit_brl is not None and economy_unit_brl > 0:
        lines.append("")
        savings = f"*Economia: {_fmt_brl(economy_unit_brl)}/un"
        if economy_pct:
            savings += f" ({economy_pct:.0%})"
        savings += "*"
        lines.append(savings)

    if relevance.reason:
        lines.append("")
        lines.append(f"_{relevance.reason}_")

    return "\n".join(lines)
