"""Generate a 'tabelão' image that looks like a real rep offer push.

Real rep messages on WhatsApp are typically images of price lists with:
  - Distributor / brand header (sometimes with logo)
  - Region tag ('SP', 'AÇÃO SP', 'PROMOÇÃO X')
  - Product rows with name + price + sometimes tier_pricing / bonus
  - A bottom note ('válido até', 'mín por CNPJ', ...)

This script produces one such image using PIL, ready to be sent to the
bridge as an offer for vision extraction (Stage 2 vision).

Output: runs/demo_offer_<ts>.jpg
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

# Tabelão dimensions — vertical phone-friendly format
W, H = 900, 1200
BG = (245, 247, 250)
HEADER_BG = (5, 60, 130)        # MILFARMA-like blue
HEADER_FG = (255, 255, 255)
ACCENT = (220, 50, 50)           # promo red
DARK = (20, 30, 45)
MUTED = (110, 120, 135)
GREEN = (28, 145, 90)
ROW_ALT = (235, 240, 248)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        ("arialbd.ttf", "arial.ttf"),
        ("calibrib.ttf", "calibri.ttf"),
        ("seguibd.ttf", "segoeui.ttf"),
    )
    for bold_name, regular in candidates:
        try:
            return ImageFont.truetype(bold_name if bold else regular, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


# 4 products with real EANs + price. Mix of URGENT (rep cheaper) and
# CIENTY_BETTER (rep pricier) so the agent has to use its head.
ROWS = [
    ("LOSARTANA POT. + HCTZ EMS 50/12,5MG  CX 30 CPR",   "R$  7,50", "bonus 1:1"),
    ("DIPIRONA SÓDICA NOVA QUÍMICA 500MG  CX 24X10",      "R$ 32,00", "mín 24un"),
    ("PARACETAMOL + CODEÍNA EUROFARMA 30MG  C/12 (A2)",   "R$ 13,50", ""),
    ("ATORVASTATINA CÁLCICA EMS 20MG  C/30 CPR",          "R$  9,80", ""),
    ("SINVASTATINA EMS 20MG  C/30 CPR",                   "R$  4,50", "bonus 2:1"),
    ("OMEPRAZOL EMS 20MG  C/28 CPR",                      "R$  3,90", ""),
]


def main(out: Path | None = None) -> Path:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Header strip
    d.rectangle([0, 0, W, 130], fill=HEADER_BG)
    d.text((40, 28), "🔥 PROMOÇÕES MILFARMA", fill=HEADER_FG, font=_font(36, bold=True))
    d.text((40, 80), "AÇÃO SP — válido até hoje 18h",
           fill=(180, 210, 255), font=_font(20))

    # Sub-header rule
    d.rectangle([40, 160, W - 40, 162], fill=DARK)
    d.text((40, 175), "Eduardo MILFARMA  ·  Distribuidora Milfarma", fill=MUTED, font=_font(18))

    # Rows
    y = 230
    row_h = 130
    for i, (name, price, tag) in enumerate(ROWS):
        if i % 2 == 0:
            d.rectangle([30, y, W - 30, y + row_h - 10], fill=ROW_ALT)
        # bullet
        d.ellipse([50, y + 32, 78, y + 60], fill=GREEN)
        d.text((57, y + 31), "✓", fill=(255, 255, 255), font=_font(22, bold=True))
        # product name (wrap if long)
        d.text((100, y + 18), name, fill=DARK, font=_font(22, bold=True))
        # price
        d.text((100, y + 60), price, fill=ACCENT, font=_font(40, bold=True))
        # tag
        if tag:
            d.text((420, y + 75), tag, fill=GREEN, font=_font(22, bold=True))
        y += row_h

    # Footer
    d.text((40, H - 90), "Mínimo por CNPJ: ver cada item.", fill=MUTED, font=_font(16))
    d.text((40, H - 60), "Bonificações sujeitas a estoque · Pedidos via WhatsApp",
           fill=MUTED, font=_font(16))
    d.text((40, H - 30), "Eduardo Silva  ·  (19) 9 8800-8990", fill=DARK, font=_font(18, bold=True))

    out = out or (ROOT / "runs" / f"demo_offer_{int(time.time())}.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=88)
    print(f"image saved: {out}")
    return out


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(out)
