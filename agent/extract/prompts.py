"""Stage 2 extraction prompt — handles both rep offers and buyer requests."""

SYSTEM_PROMPT = """Você extrai informações estruturadas de mensagens de WhatsApp entre \
representantes de distribuidoras farmacêuticas e compradores de farmácia.

Uma mensagem pode ter duas DIREÇÕES:

  rep_offer
    Representante OFERECENDO produto pra comprador. Tem preço.
    Exemplos: "DIPIRONA 24X10 NOVAQUIMICA R$ 45,16" / lista diária de promoções.

  buyer_request
    Comprador PEDINDO cotação/produto pros reps. Não tem preço (o preço vai vir
    depois nas respostas individuais). Pode mencionar quantidade.
    Exemplo: "Bom dia, alguém tem Luvas Látex sem pó tamanhos P/M/G? 200 de cada."

REGRAS

1. Uma mensagem pode conter ZERO, UMA ou VÁRIAS extrações.
   - Saudação pura ("Bom dia") → zero, is_offer_message=false, skip_reason="saudação"
   - Push do MILFARMA com 50 produtos → 50 rep_offer
   - Wagno perguntando "alguém tem luva e máscara?" → 2 buyer_request

2. Como decidir a direção:
   - Sender é um rep/distribuidora (Eduardo MILFARMA, Daniele Servimed, etc.)
     E há preço/menção comercial → rep_offer
   - Sender é o comprador (WAGNO, C Cienty, C Comprador) → buyer_request
     mesmo que ele mencione um preço (ele tá perguntando "fulano me passou R$ X, vocês têm melhor?")
   - Quando há lista de produtos sem preço vinda do comprador → buyer_request, um por produto

3. Para rep_offer extraia:
   - product_name_raw: nome do produto EXATAMENTE como aparece, verbatim, sem normalizar
   - price_offered_brl: preço unitário em REAIS, decimal (R$ 4,80 → 4.80)
   - bonus_type: "qty" (1:1, 1:2 mesmo SKU) | "cross" (ganha OUTRO produto) |
                 "pct" (desconto %) | "none"
   - bonus_qty: quantidade bonificada (1:1 → 1)
   - bonus_target_product: pra cross, qual é o brinde
   - min_qty: pedido mínimo (se mencionado)
   - max_qty_per_cnpj: LIMITE por CNPJ (cap, não floor). Ex: "Limitado em 60 unidades" → 60.
   - deadline: validade da oferta (ISO 8601 se houver data+hora)
   - region: restrição regional. "por SP", "NAVARRO SP", "AÇÃO SP" → "SP".
             "Livre" ou sem menção → null (nacional).
   - source_label: nome de campanha quando explícito. "PROMOÇÃO NAVARRO", "AÇÃO SP",
                   "Promoções Neo Química". Útil pra agrupar push do mesmo rep.
   - tier_pricing: quando o rep dá PREÇO ESCALONADO por volume:
       "$13,49 para 24 unidades / $12,99 para 60 unidades"
       → [{"min_qty": 24, "unit_price_brl": 13.49},
          {"min_qty": 60, "unit_price_brl": 12.99}]
       Quando tier_pricing está preenchido, price_offered_brl deve ser o
       preço da PRIMEIRA faixa (entry-level).
   - kit_items: quando a oferta é um KIT/BUNDLE multi-produto com preço total:
       "30 NEOSORO AD R$ 2,99 + 10 METOPROLOL 25mg R$ 18,55 = TOTAL R$ 275,20"
       → kit_items = [{"qty": 30, "product": "NEOSORO AD", "unit_price_brl": 2.99},
                      {"qty": 10, "product": "METOPROLOL 25mg", "unit_price_brl": 18.55}]
       E price_offered_brl = 275.20 (total do kit).
       product_name_raw vira "Kit Navarro: NEOSORO + METOPROLOL" ou similar.

4. Para buyer_request extraia:
   - product_name_raw: nome do produto que o comprador está pedindo, verbatim
   - requested_qty: quantidade pedida (se mencionada)
   - Os demais campos (price, bonus, min_qty, deadline) ficam NULL.

5. Preço em formato BR (R$ 45,16) → decimal com ponto (45.16).

6. NUNCA invente preço ou produto. Se incompleto, deixe price=null e confidence baixa.

VISÃO (quando a mensagem inclui imagem):
A imagem geralmente é uma TABELA com produtos e preços, OU um cartaz de promoção.
Trate o texto da mensagem (caption) como ENRIQUECIMENTO da imagem — preço ou
restrição que aparece SÓ no caption ("Limitado em 60 unidades por SP" abaixo da
foto) vale pra TODOS os produtos da imagem, a menos que a imagem deixe claro
o contrário. Extraia um rep_offer POR LINHA da tabela.

7. Marque is_offer_message=false e offers=[] para:
   - saudações ("bom dia", "tudo bem")
   - logística do comprador ("liberei a cotação", "fechamento amanhã 16h")
   - confirmações ("ok", "obrigado")
   - mensagens de sistema do WhatsApp
   - propaganda sem produto/preço específico ("melhor preço do mercado")

FORMATO DE SAÍDA

Use a ferramenta `extract_offers`. Retorne SEMPRE, mesmo quando não houver extração.
"""


def user_prompt(message_id: str, sender: str | None, received_at: str, body: str, is_from_buyer: bool) -> str:
    role_hint = (
        "O sender é o COMPRADOR — provavelmente buyer_request."
        if is_from_buyer
        else "O sender é um REPRESENTANTE — provavelmente rep_offer."
    )
    return f"""MENSAGEM PARA EXTRAIR

message_id: {message_id}
sender: {sender or "(desconhecido)"}
received_at: {received_at}

{role_hint}
---
{body}
---

Extraia seguindo as regras."""


EXTRACT_TOOL = {
    "name": "extract_offers",
    "description": "Extrai ofertas estruturadas (rep_offer ou buyer_request) de uma mensagem de WhatsApp.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_offer_message": {
                "type": "boolean",
                "description": "True se a mensagem contém ao menos um item (rep_offer OU buyer_request).",
            },
            "skip_reason": {
                "type": ["string", "null"],
                "description": "Se is_offer_message=false: saudação | logística | confirmação | sistema | propaganda | outro",
            },
            "offers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["rep_offer", "buyer_request"],
                        },
                        "product_name_raw": {"type": "string"},
                        "price_offered_brl": {"type": ["number", "null"]},
                        "bonus_type": {
                            "type": "string",
                            "enum": ["none", "qty", "cross", "pct"],
                        },
                        "bonus_qty": {"type": ["integer", "null"]},
                        "bonus_target_product": {"type": ["string", "null"]},
                        "min_qty": {"type": ["integer", "null"]},
                        "max_qty_per_cnpj": {
                            "type": ["integer", "null"],
                            "description": "Hard cap per CNPJ. 'Limitado em 60 unidades' → 60.",
                        },
                        "deadline": {
                            "type": ["string", "null"],
                            "description": "ISO 8601 if a date+time is mentioned, else null",
                        },
                        "requested_qty": {
                            "type": ["integer", "null"],
                            "description": "For buyer_request, quantity the buyer is asking for.",
                        },
                        "region": {
                            "type": ["string", "null"],
                            "description": "BR state code restriction (e.g., 'SP', 'RJ'). "
                                           "Null = national/no restriction.",
                        },
                        "source_label": {
                            "type": ["string", "null"],
                            "description": "Marketing label / campaign name when explicit "
                                           "('PROMOÇÃO NAVARRO', 'AÇÃO SP', 'Promoções Neo Química').",
                        },
                        "tier_pricing": {
                            "type": ["array", "null"],
                            "description": "Volume-tiered prices. Each entry: "
                                           "{'min_qty': int, 'unit_price_brl': number}. "
                                           "When present, price_offered_brl = price of first (lowest qty) tier.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "min_qty": {"type": "integer"},
                                    "unit_price_brl": {"type": "number"},
                                },
                                "required": ["min_qty", "unit_price_brl"],
                            },
                        },
                        "kit_items": {
                            "type": ["array", "null"],
                            "description": "Multi-product bundle items. "
                                           "When present, price_offered_brl = total kit price.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "qty": {"type": "integer"},
                                    "product": {"type": "string"},
                                    "unit_price_brl": {"type": ["number", "null"]},
                                },
                                "required": ["qty", "product"],
                            },
                        },
                        "extraction_confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "extraction_notes": {"type": ["string", "null"]},
                    },
                    "required": [
                        "direction",
                        "product_name_raw",
                        "bonus_type",
                        "extraction_confidence",
                    ],
                },
            },
        },
        "required": ["is_offer_message", "offers"],
    },
}
