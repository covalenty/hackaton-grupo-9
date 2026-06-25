"""Format alert text for delivery via WhatsApp.

Takes the rep offer + Cienty comparison + relevance score and produces a
human-readable WhatsApp message in PT-BR.

WhatsApp formatting that survives: *bold*, _italic_, ```mono```. We use *bold*
sparingly for the bottom-line economy figure.

Two flavors:
  - URGENT/HIGH (rep cheaper than Cienty): "compra com o rep, vale a pena"
  - CIENTY_BETTER (rep more expensive): "compra pela Cienty, é mais barato" —
    defends Cienty GMV when the rep tries to lure the buyer with a worse price.
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
        RelevanceBand.CIENTY_BETTER: "💡",
        RelevanceBand.MEDIUM: "📌",
        RelevanceBand.LOW: "💬",
        RelevanceBand.SKIP: "·",
    }.get(band, "·")


def _band_header(band: RelevanceBand) -> str:
    return {
        RelevanceBand.URGENT: "URGENT",
        RelevanceBand.HIGH: "HIGH",
        RelevanceBand.CIENTY_BETTER: "MELHOR NA CIENTY",
        RelevanceBand.MEDIUM: "MEDIUM",
        RelevanceBand.LOW: "LOW",
        RelevanceBand.SKIP: "SKIP",
    }.get(band, band.value.upper())


def _format_cienty_better(
    *,
    offer: ExtractedOffer,
    canonical_name: Optional[str],
    price_cienty_brl: Optional[float],
    economy_unit_brl: Optional[float],
    economy_pct: Optional[float],
    relevance: RelevanceScore,
    rep_name: Optional[str],
) -> str:
    """Inverted alert — rep tried to sell, Cienty is cheaper."""
    product = canonical_name or offer.product_name_raw
    lines: list[str] = [f"{_band_emoji(relevance.band)} *{_band_header(relevance.band)}*"]
    if rep_name:
        lines[0] += f" · {rep_name} mandou oferta"
    lines.append("")
    lines.append(f"*{product}*")
    if canonical_name and canonical_name.lower() != offer.product_name_raw.lower():
        lines.append(f"_({offer.product_name_raw})_")
    lines.append("")
    if offer.price_offered_brl is not None and price_cienty_brl is not None:
        lines.append(f"{rep_name or 'Rep'}: {_fmt_brl(offer.price_offered_brl)}/un")
        lines.append(f"Cienty: *{_fmt_brl(price_cienty_brl)}/un* ← mais barato")
        if economy_unit_brl is not None:
            gap = abs(economy_unit_brl)
            pct = abs(economy_pct or 0)
            lines.append("")
            lines.append(f"*Você economiza {_fmt_brl(gap)}/un ({pct:.0%}) comprando pela Cienty*")
    lines.append("")
    lines.append("→ Bater o pedido pela Cienty")
    if relevance.reason:
        lines.append("")
        lines.append(f"_{relevance.reason}_")
    return "\n".join(lines)


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
    if relevance.band == RelevanceBand.CIENTY_BETTER:
        return _format_cienty_better(
            offer=offer,
            canonical_name=canonical_name,
            price_cienty_brl=price_cienty_brl,
            economy_unit_brl=economy_unit_brl,
            economy_pct=economy_pct,
            relevance=relevance,
            rep_name=rep_name,
        )

    # Standard rep-cheaper flow (URGENT/HIGH)
    emoji = _band_emoji(relevance.band)
    product = canonical_name or offer.product_name_raw
    lines: list[str] = []
    header = f"{emoji} *{_band_header(relevance.band)}*"
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
