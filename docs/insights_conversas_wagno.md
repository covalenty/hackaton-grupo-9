# Insights das conversas reais do Wagno (Farmaestra)
*Análise gerada em 25/06/2026 — Claude Opus 4.7 sobre histórico WhatsApp*

## Dados analisados
| Rep | Mensagens | % mídia | Áudios | Janela |
|-----|-----------|---------|--------|--------|
| Paulinho Navarro | 1.527 | 88% (1.339) | 42 | out/24–ago/25 |
| Fabio Medbras | 331 | 39% (129) | 0 | out/24–jun/26 |

## 5 insights críticos pro agente

### 1. Vision é hoje, não V2
88% das mensagens do Paulinho são imagem. V1 cobre só 12% do sinal do rep mais ativo. **Vision é pré-requisito, não feature futura.**

### 2. Imagem + caption são uma unidade
```
[14:05] <Mídia oculta>    ← imagem com tabela
[14:05] $9,69             ← caption com preço
[14:05] Limitado 60un SP  ← restrições
```
Caption isolado é incompreensível. Mensagem subsequente do mesmo sender em <60s deve ser fundida num evento só.

### 3. Schema do ExtractedOffer incompleto
Campos que faltam:
- `tier_pricing: [{qty, price}]` — ex: "$13,49/24un · $12,99/60un"
- `region: str` — ex: "por SP", "NAVARRO SP"
- `max_qty_per_cnpj: int` — ex: "Limitado em 60 unidades por SP"
- `kit_items: list` — ex: "30 NEOSORO + 10 METROPROLOL = R$ 275,20"
- `source_label: str` — ex: "PROMOÇÃO NAVARRO", "AÇÃO SP"
- `deadline: datetime` — ex: "Até amanhã 26/12" (LLM ainda não captura informal)

### 4. Direction precisa de 3 valores novos
Hoje: `rep_offer` | `buyer_request`. Nas conversas reais:
- `negotiation` — "Dom Pedro e Rondon, 3 de cada" → "Ok! Vlw" (compra fechada off-platform)
- `logistics` — "tem pedido do Mall que ainda não chegou?" (pull de status de entrega)
- `social` — link de notícia, futebol, sticker (noise — não alertar)

**gold.buyer_unmet_demand está superestimando** (qualquer texto não-oferta vira buyer_request).

### 5. Identidade de rep não é monolítica
Paulinho tem Thayane + Jamilly respondendo cotação por ele (jamily.alves@navarromed.com.br).
`rep_id` deve ser a entidade distribuidora, não o contato individual.
Padrão igual no Wagno: Camila Lbreal Servimed, Daniele Servimed, Jéssica COTY Servimed = todos Servimed.

---

## O que fica fora hoje

| Tipo | Exemplo | V1 | V2 (vision) | Schema novo |
|------|---------|-----|-------------|-------------|
| Imagem com tabela | foto JPG Paulinho | ❌ | ✅ | — |
| Caption isolado | "$9,69" | ⚠️ perde ctx | ✅ fusão img+text | — |
| Tier pricing | "$13,49/24un · $12,99/60un" | parcial | ✅ | tier_pricing |
| Restrição regional | "por SP", "NAVARRO SP" | ❌ | ✅ | region |
| Kit bundle | "30 NEOSORO + 10 METROPROLOL = R$275" | parcial | ✅ | kit_items |
| Áudio negociação | opus 30s | ❌ | ❌ (Whisper) | — |
| Closing/deal | "3 de cada / Ok! Vlw" | classifica errado | ✅ | Direction.negotiation |
| Logística pull | "tem pedido que não chegou?" | classifica errado | ✅ | Direction.logistics |
| Social/relação | link de notícia | ignora | ✅ | Direction.social |

---

## Insights pra Cienty (plataforma)

### 1. Quanto GMV vive fora? (a pergunta de US$)
Wagno fecha pedido com Paulinho via "Dom Pedro e Rondon, 3 de cada" e nunca toca Cienty.
Capturar esse momento + somar por mês = tamanho do mercado off-platform por cliente.
Sinal direto pro GTM e priorização de distribuidoras.

### 2. Top 3 distribuidoras off-platform pro Wagno
- **Navarro** — já está na Cienty (R$ 10.367 em 26 pedidos), mas compra off-platform via Zap. Motivo provável: preços melhores no canal direto, kits, "ação SP". Vale conversa comercial.
- **Medbras** — não está na Cienty. Próxima a integrar.
- **Milfarma** — não está na Cienty. Próxima a integrar.

### 3. Produtos que faltam no modelo
| Padrão fora | Por que não existe | Vale produto? |
|-------------|-------------------|---------------|
| Preço por região (SP/RJ) | Plataforma exibe preço único | Sim |
| Tier pricing (qty→preço) | Sem escalamento por volume | Sim — ticket cresce |
| Kit/bundle multi-SKU | Não suporta bundle | Sim — cross-sell |
| Action 24h | Catálogo de preço estável | Talvez — "ofertas relâmpago" |
| Promoção rotulada | Sem branding de campanha | Sim — diferenciação por distribuidora |

### 4. Service-as-product
Wagno pergunta status de pedido pelo WhatsApp. O agente já recebe esse sinal — pode virar resposta automática ("Pedido X, sai pra entrega 28/06"). Moat de UX vs comprar direto do distribuidor.

### 5. Fechamento de pedido = evento mais valioso (descartado hoje)
Capturando `NEGOTIATION` + `DEAL_CLOSED` → closed-loop tracking.
Sabemos o que cada farmácia comprou de cada rep no WhatsApp. **Esse é o dado que a indústria farma inteira gostaria de ter.**
