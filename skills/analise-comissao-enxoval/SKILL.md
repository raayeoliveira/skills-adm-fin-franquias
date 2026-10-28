---
name: analise-comissao-enxoval
description: Soma as comissões Seazone do mês juntando as 3 fontes — planilhas Matinali/RM, lojinha (endpoint de NFs) e app Jornada Completa Enxoval
---

Calcule a soma das comissões Seazone do **mês atual** (ou o mês que o usuário pedir) juntando **três fontes**:

1. **Planilhas** Matinali e RM PF (fluxo antigo, ainda em uso no período de transição)
2. **Lojinha** — endpoint `nf-commissions` (Harus, IZY BRINDES, Loja do Guarda pó, Momento Amenities, Somar Malhas + NFs de Matinali/RM da lojinha)
3. **App Jornada Completa Enxoval** — novo fluxo, banco `enxoval` no Supabase `boaystsxsyntdvogdakn`

**REGRA DE DEDUPE (Henry, 21/08/2026):** pedido duplicado não deveria acontecer, mas se acontecer **a planilha vence**. Na prática: card do app só **não é somado** quando `origemPlanilha.linha` aponta para uma linha que a planilha **já somou no mês** (NF do mês na col V/X) — aí a comissão vem da coluna AB/AG.

**REGRA (Henry, 23/09/2026): NUNCA ignorar pedido em `enviado` criado pelo Agente de Adequação.** O agente grava `origemPlanilha` como metadado mesmo sem linha na planilha (`linha = null`, id `agente:M:...`/`agente:R:...`). Esses cards **entram pelo app**. Idem card com `linha` preenchida cuja linha está sem NF no mês na planilha. Em 09/2026 o dedupe antigo sumia com 35 pedidos (R$ 4.178,49).

**REGRA FIXA (Henry, 21/08/2026): a análise SEMPRE considera as 3 fontes juntas, com esse dedupe.**
Não existe modo "só planilha" ou "só app" — mesmo que uma fonte volte zero no mês, ela é consultada e reportada (zero explícito). Enquanto os dois fluxos coexistirem é isso que garante que nada some nem conte em dobro.

**Tudo read-only. NUNCA escrever nas planilhas nem no banco.**

## PASSO 1 — Mês alvo

`YYYY-MM` a partir do `currentDate` (ou o que o usuário pediu).

## PASSO 2 — Baixar as planilhas (CSV completo)

Via `mcp__claude_ai_Google_Drive__download_file_content`, `exportMimeType: "text/csv"`:

- Matinali: `1lt3WUwTOLIPWsD72_KKXcPmUwvoaALBB4sjB3Ss9qhs`
- RM PF: `1XRL8Ezx2f-OxxUPMHz24Ca9nma_LPDvj_8_yfonZXyE`

O retorno estoura o limite e é salvo em um `.txt` (JSON `{content: <base64 do csv>}`) — anote os dois caminhos e confirme qual é qual pelo campo `title`.

⚠️ NÃO usar `read_file_content` (trunca) nem `GOOGLESHEETS_VALUES_GET` por range (a numeração de colunas já está resolvida no script).

## PASSO 3 — Rodar o script (faz planilhas + lojinha + app de uma vez)

```bash
# credencial do app enxoval: SUPABASE_PAT (Management API) ou ENXOVAL_RO_DATABASE_URL (Postgres read-only, pedir ao Henry; precisa de psycopg2)
set -a; . ~/.enxoval_ro.env; set +a
python3 ~/.claude/skills/analise-comissao-enxoval/scripts/comissao_enxoval.py <YYYY-MM> <csv_matinali.txt> <csv_rm.txt>
```

O que ele faz:

- **Planilhas:** filtra pela coluna "Data da emissão da Nota Fiscal (Fornecedor)" (Matinali col. V / RM col. X) batendo `dd/MM/YYYY` do mês, soma "Comissão Seazone" (Matinali col. AB / RM col. AG).
- **Lojinha:** GET `nf-commissions?month=YYYY-MM` → usa `commission_by_supplier` (5%) para Harus, IZY BRINDES, Loja do Guarda pó, Matinali, Momento Amenities, RM Enxoval. Fornecedor ausente = R$ 0,00. `Seazone` e outros nomes fora do mapeamento aparecem como aviso e **não** entram na soma.
- **Somar Malhas:** NÃO é 5%. Pega os `order_id` das `invoices` do mês e cruza com `loja-full-export?table=order_items`, aplicando a tabela por `unit_price` (preços "sup" = R$ 0,00 / camiseta R$ 4,50 / moleton R$ 25,50). Preço fora da tabela → R$ 0,00 + aviso.
- **App:** query read-only em `enxoval.pedidos_kanban` (Management API do Supabase, `SUPABASE_PAT`) pegando os dois boards (`pedidos` e `recompras`) com `fase` começando em `enviado` e `campos->'nf-data-emissao'` dentro do mês. Comissão = **5% sobre o valor SEM frete** (`totalItensCents`, ou `totalCents − freteCents`) — mesma regra do `/relatorio` do app. Card com `origemPlanilha` só é descartado se a `linha` dele foi somada na planilha no mês (listado como dedupe); os do Agente de Adequação são somados e listados à parte.

## PASSO 4 — Apresentar

Monte a saída a partir do que o script imprimiu, nesta forma:

```
📊 Comissões Seazone — MM/YYYY

🏷️ Matinali
   Planilha (col AB):   R$ X.XXX,XX  (XX NFs)
   Lojinha (5% NFs):    R$ X.XXX,XX  (XX NFs)
   App (5% s/ frete):   R$ X.XXX,XX  (XX pedidos)
   Total Matinali:      R$ X.XXX,XX

🏷️ RM Enxoval
   Planilha (col AG):   R$ X.XXX,XX  (XX NFs)
   Lojinha (5% NFs):    R$ X.XXX,XX  (XX NFs)
   App (5% s/ frete):   R$ X.XXX,XX  (XX pedidos)
   Total RM Enxoval:    R$ X.XXX,XX

🏷️ Harus
   Lojinha (5% NFs):    R$ X.XXX,XX  (XX NFs)

🏷️ IZY BRINDES
   Lojinha (5% NFs):    R$ X.XXX,XX  (XX NFs)

🏷️ Loja do Guarda pó
   Lojinha (5% NFs):    R$ X.XXX,XX  (XX NFs)

🏷️ Momento Amenities
   Lojinha (5% NFs):    R$ X.XXX,XX  (XX NFs)

🏷️ Somar Malhas
   Pedidos no mês:      XX pedidos  (XX itens)
   Com comissão:        R$ X.XXX,XX
   Sem comissão (sup):  R$ 0,00  (XX itens)

📌 Totais
   Enxoval (Matinali + RM Enxoval):   R$ X.XXX,XX
   Comissão desconsiderando Enxoval:  R$ X.XXX,XX
   Comissão Geral:                    R$ X.XXX,XX

🔀 Transição planilha→app: XX card(s) do app somados (XX do Agente de Adequação), XX ignorado(s) por dedupe (linha já somada na planilha)
```

**REGRA (Henry, 07/09/2026): cada fornecedor em bloco próprio, nunca agrupar fornecedores numa linha só — mesmo os que zeraram no mês.**

Sempre incluir a linha de transição (mesmo que o app tenha somado 0) e os avisos de preço não mapeado / fornecedor fora do mapeamento, se houver. Valores em `R$ X.XXX,XX` (padrão BR).

## Notas de manutenção

- Quando a planilha for descontinuada de vez, é só parar de baixar os CSVs — o script aceita planilhas vazias e o dedupe deixa de ter efeito (nenhum card novo terá `origemPlanilha`).
- Fase do card no app é slug (`aguardando-link`, `pagamento-confirmado`, `enviado`, `cancelado`); o filtro usa `like 'enviado%'`.
- Comissão do app é 5% fixo hoje. Se virar tabela por fornecedor, mexer em `COMISSAO_APP_PCT` / `pedidos_app()` no script.
- Campo do card pode ser string (cards antigos) ou objeto com carimbo `{"valor": "...", "preenchidoEm": "..."}` (desde ~26/08/2026). O script lê com `coalesce(dados->'campos'->'<campo>'->>'valor', dados->'campos'->>'<campo>')`. Nunca usar `->>` puro: a comparação de data falha em silêncio e o app volta **zero pedidos** sem erro nenhum.
- Sanidade: se o app voltar 0 no mês, conferir na tela (`https://jornada-enxoval.seazone.com.br`) se realmente não há card enviado com NF no mês antes de reportar zero.
