"""Format alert text for delivery via WhatsApp.

Design principles:
  - Lead with the benefit (R$ economy + %). That's the headline.
  - Two-price comparison in compact lines.
  - One CTA at the bottom, action-oriented.
  - On CIENTY_BETTER: include a clickable product link with UTM tracking,
    so a click on the Zap closes the loop straight into platform GMV.

WhatsApp markdown that survives: *bold*, _italic_. Plain URLs auto-link.
"""
from __future__ import annotations

import os
from typing import Optional

from ..schemas import ExtractedOffer, RelevanceBand, RelevanceScore


# Configurable via env so prod can point to the real Cienty domain without
# touching code. Default works for hackathon demo.
CIENTY_PRODUCT_URL_BASE = os.getenv("CIENTY_PRODUCT_URL_BASE", "https://app.cienty.com.br")


def _product_url(ean: Optional[str], message_id: Optional[str]) -> Optional[str]:
    """Build a deep-link to the product page with attribution params."""
    if not ean:
        return None
    qs = "utm_source=whatsapp&utm_medium=cienty-better-alert"
    if message_id:
        qs += f"&alert_id={message_id}"
    return f"{CIENTY_PRODUCT_URL_BASE}/produto/{ean}?{qs}"


def _fmt_brl(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{abs(value):.0%}"


def _extras_line(offer: ExtractedOffer) -> Optional[str]:
    """Compact one-liner for bonus / min / deadline. Returns None if all absent."""
    parts: list[str] = []
    if offer.bonus_type.value == "qty" and offer.bonus_qty:
        parts.append(f"bonus 1:{offer.bonus_qty}")
    elif offer.bonus_type.value == "cross" and offer.bonus_target_product:
        parts.append(f"+{offer.bonus_target_product}")
    elif offer.bonus_type.value == "pct":
        parts.append("desconto %")
    if offer.min_qty:
        parts.append(f"mín {offer.min_qty}un")
    if offer.deadline:
        parts.append(f"vence {offer.deadline.strftime('%d/%m %H:%M')}")
    return " · ".join(parts) if parts else None


def _format_rep_cheaper(
    *,
    offer: ExtractedOffer,
    canonical_name: Optional[str],
    price_cienty_brl: Optional[float],
    economy_unit_brl: Optional[float],
    economy_pct: Optional[float],
    rep_name: Optional[str],
) -> str:
    """URGENT/HIGH — rep is cheaper than Cienty. Lead with economy + CTA to act."""
    product = canonical_name or offer.product_name_raw
    lines: list[str] = []

    if economy_unit_brl is not None and economy_unit_brl > 0:
        head = f"🚨 *Economize {_fmt_brl(economy_unit_brl)}/un*"
        if economy_pct:
            head += f" · {_fmt_pct(economy_pct)}"
        lines.append(head)
    else:
        lines.append("🚨 *Oferta urgente*")

    lines.append("")
    lines.append(f"*{product}*")
    if offer.price_offered_brl is not None:
        rep = rep_name or "Rep"
        lines.append(f"{rep}: {_fmt_brl(offer.price_offered_brl)}/un")
    if price_cienty_brl is not None:
        lines.append(f"Cienty hoje: {_fmt_brl(price_cienty_brl)}/un")

    extras = _extras_line(offer)
    if extras:
        lines.append(extras)

    lines.append("")
    cta_rep = rep_name or "o rep"
    lines.append(f"👉 Vale fechar com {cta_rep}")
    return "\n".join(lines)


def _format_cienty_better(
    *,
    offer: ExtractedOffer,
    canonical_name: Optional[str],
    price_cienty_brl: Optional[float],
    economy_unit_brl: Optional[float],
    economy_pct: Optional[float],
    rep_name: Optional[str],
    ean: Optional[str],
) -> str:
    """CIENTY_BETTER — rep is pricier. Lead with the Cienty advantage + clickable CTA."""
    product = canonical_name or offer.product_name_raw
    gap = abs(economy_unit_brl) if economy_unit_brl is not None else None
    lines: list[str] = []

    if gap and gap > 0:
        head = f"💡 *Cienty {_fmt_brl(gap)}/un mais barato*"
        if economy_pct:
            head += f" · {_fmt_pct(economy_pct)}"
        lines.append(head)
    else:
        lines.append("💡 *Melhor pela Cienty*")

    lines.append("")
    lines.append(f"*{product}*")
    if offer.price_offered_brl is not None:
        rep = rep_name or "Rep"
        lines.append(f"{rep}: {_fmt_brl(offer.price_offered_brl)}/un")
    if price_cienty_brl is not None:
        lines.append(f"Cienty: {_fmt_brl(price_cienty_brl)}/un")

    url = _product_url(ean, offer.message_id)
    lines.append("")
    if url:
        lines.append("👉 *Comprar na Cienty:*")
        lines.append(url)
    else:
        lines.append("👉 Comprar pela Cienty")
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
    """Build the WhatsApp message body for one alert.

    Two flavors:
      - URGENT/HIGH (rep cheaper): "Economize R$ X — fechar com o rep"
      - CIENTY_BETTER (rep pricier): "Cienty R$ X mais barato — comprar pela Cienty"
    """
    if relevance.band == RelevanceBand.CIENTY_BETTER:
        return _format_cienty_better(
            offer=offer,
            canonical_name=canonical_name,
            price_cienty_brl=price_cienty_brl,
            economy_unit_brl=economy_unit_brl,
            economy_pct=economy_pct,
            rep_name=rep_name,
            ean=relevance.ean_matched,
        )
    return _format_rep_cheaper(
        offer=offer,
        canonical_name=canonical_name,
        price_cienty_brl=price_cienty_brl,
        economy_unit_brl=economy_unit_brl,
        economy_pct=economy_pct,
        rep_name=rep_name,
    )
