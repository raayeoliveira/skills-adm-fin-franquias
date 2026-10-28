---
name: analise-faturamento-franquia
description: Gera análise executiva do faturamento de uma franquia Seazone dado APENAS o nome do franqueado (host). Consolida os últimos 12 meses com portfólio, diárias ocupadas, valor de reservas, taxa de limpeza, faturamento da franquia (8% da reserva + limpeza) e despesas lançadas no Sapron. Ative com "/analise-faturamento-franquia <nome>", "análise de faturamento da franquia <nome>", "faturamento do franqueado <nome>", "quanto faturou a franquia <nome>", "receita da franquia <nome>".
---

# Análise de Faturamento — Franquia Seazone

## Quando usar
- Pedidos como "faz uma análise de faturamento da franquia <nome>", "quanto faturou o franqueado <nome>", "receita da franquia <nome>", "quanto a franquia <nome> gerou nos últimos 12 meses".
- Ativação por slash: `/analise-faturamento-franquia <nome>` ou `/analise-faturamento-franquia <nome sobrenome>`.
- Preparação de 1:1 com franqueado, revisão de saúde da carteira, checagem antes de renovação/desligamento.

## Entrada
- **Nome do franqueado** (case-insensitive, aceita nome parcial). Ex.: `Itatiana`, `Itatiana Marques`, `marques de moura`.
- Se ambíguo (>1 host encontrado), listar as opções (nome + host_id + city) e pedir confirmação antes de rodar.
- Se nada encontrado, sugerir busca alternativa (`LIKE '%<primeiro_nome>%'`).

## Fórmula do faturamento da franquia
```
fat_franquia_mes = 0,08 × valor_reservas + taxa_limpeza
```
- `valor_reservas` = `reservation_avg_full_price − reservation_avg_cleaning_fee` (bruto sem taxa de limpeza).
- `taxa_limpeza` = `reservation_avg_cleaning_fee` (repassada integralmente à franquia).
- Comparar sempre 12 meses cheios (ex.: hoje = 2026-08-11 → janela `2025-09-01` até `2026-09-01`).

## Fontes obrigatórias
| Dado | Source | Database | Tabela |
|---|---|---|---|
| Portfólio + host_id | sirius (Athena) | `saprondata-*` | `listing_franchises` (state='current') |
| Receita diária por imóvel | sirius (Athena) | `revenuedata-*` | `daily_revenue_sapron` |
| Despesas / ressarcimentos | Sapron (Postgres via `mcp__sapron__consultar_banco`) | `public` | `financial_expenses` × `property_property` |

⚠️ Nomes dos databases sirius têm sufixo aleatório — SEMPRE resolver via `mcp__data-lake__list_databases(source='sirius')` antes de query.

## Passos (obrigatórios, nesta ordem)

### 1. Achar a franquia
```sql
-- source='sirius', database='saprondata-<sufixo>'
SELECT DISTINCT host_id, "anfitrião" AS anfitriao, city, estado, COUNT(*) OVER (PARTITION BY host_id) AS total_imoveis
FROM "saprondata-<sufixo>".listing_franchises
WHERE state='current' AND LOWER("anfitrião") LIKE LOWER('%<nome>%')
```
- 0 linhas → erro amigável e sugerir variação.
- >1 host_id → listar e pedir confirmação.
- 1 host_id → prosseguir.

### 2. Levantar todos os imóveis do host
```sql
SELECT code, status
FROM "saprondata-<sufixo>".listing_franchises
WHERE state='current' AND host_id = <host_id>
ORDER BY status, code
```
Contar por status: Active, Inactive, Onboarding.

### 3. Faturamento mensal (últimos 12 meses)
Considera **apenas imóveis que efetivamente faturaram** no mês (`valor_reservas > 0`).
```sql
-- source='sirius'
WITH imv AS (
  SELECT code FROM "saprondata-<sufixo>".listing_franchises
  WHERE state='current' AND host_id = <host_id>
),
por_imovel AS (
  SELECT date_trunc('month', dr.date) AS mes, dr.listing,
         SUM(COALESCE(dr.reservation_avg_full_price,0) - COALESCE(dr.reservation_avg_cleaning_fee,0)) AS valor_reservas,
         SUM(COALESCE(dr.reservation_avg_cleaning_fee,0)) AS taxa_limpeza,
         SUM(CASE WHEN dr.occupied=true THEN 1 ELSE 0 END) AS diarias_ocup
  FROM "revenuedata-<sufixo>".daily_revenue_sapron dr
  JOIN imv i ON dr.listing = i.code
  WHERE dr.date >= DATE '<inicio_12m>' AND dr.date < DATE '<hoje_mes_prox>'
  GROUP BY 1, 2
)
SELECT mes,
       COUNT(DISTINCT CASE WHEN valor_reservas > 0 THEN listing END) AS imoveis_com_receita,
       SUM(diarias_ocup) AS diarias_ocup,
       ROUND(SUM(valor_reservas),2) AS valor_reservas,
       ROUND(SUM(taxa_limpeza),2) AS taxa_limpeza,
       ROUND(SUM(valor_reservas)*0.08,2) AS comissao_8pct,
       ROUND(SUM(valor_reservas)*0.08 + SUM(taxa_limpeza),2) AS fat_franquia
FROM por_imovel
GROUP BY mes ORDER BY mes
```

### 4. Despesas lançadas (Sapron)
```sql
-- mcp__sapron__consultar_banco
SELECT date_trunc('month', fe.expense_date)::date AS mes,
       ROUND(SUM(CASE WHEN fe.expense_status='Approved' THEN fe.value ELSE 0 END)::numeric,2) AS despesas_aprovadas,
       COUNT(*) FILTER (WHERE fe.expense_status='Approved') AS qtd_aprov,
       ROUND(SUM(CASE WHEN fe.expense_status='Pending' THEN fe.value ELSE 0 END)::numeric,2) AS despesas_pendentes
FROM financial_expenses fe
JOIN property_property pp ON pp.id = fe.property_id
WHERE pp.code IN (<lista_codes>)
  AND fe.expense_date >= '<inicio_12m>' AND fe.expense_date < '<hoje_mes_prox>'
GROUP BY 1 ORDER BY 1
```
- Categoria 17 do `financial_expenses_category` = Ressarcimento (destacar se houver).
- Se despesas < 2% do faturamento em portfólio > 20 imóveis, mencionar risco de subregistro (verificar Pipefy Pipe 14 Manutenção como fonte paralela).

## Saída (no chat, em Markdown)
Ordem fixa:

1. **Cabeçalho** — nome do franqueado · host_id · cidade/UF · portfólio (X ativos / Y inativos / Z onboarding).
2. **Tabela mensal** com colunas: Mês · Imóveis c/ receita · Diárias · Comissão 8% · Taxa Limpeza · **Fat. Franquia** (destaque em negrito) · Despesas · Fat. Líquido.
3. **Linha Total 12M** somando as colunas e contando imóveis únicos que faturaram no período.
4. **Leitura executiva** (2-4 bullets):
   - Concentração sazonal (% dos top-3 meses).
   - Cauda longa: quantos imóveis nunca faturaram / % de capacidade ociosa.
   - Sinal de subregistro de despesas.
   - Top 3 imóveis por faturamento (se solicitado ou se >20 imóveis no portfólio).
5. **Oferta de HTML** — perguntar se quer o padrão visual Seazone (não gerar sem confirmação — respeita a regra Slack/execução).

## Formatação de valores
- R$ com separador de milhar `.` e decimal `,` (`R$ 55.644,07`).
- Mês em `Mmm/AAAA` (`Jan/2026`).
- Mês corrente marcado com `*` e nota "parcial (até DD/MM/AAAA)".

## Erros comuns a evitar
- ❌ Colocar `anfitrião` sem aspas no SQL Athena → erro de parser (cedilha/acento). Use `"anfitrião"`.
- ❌ Contar `imoveis_com_receita` pelo `daily_revenue_sapron` cru → conta imóveis com linha (mesmo bloqueados sem venda). Filtrar `valor_reservas > 0` por imóvel/mês.
- ❌ Somar `reservation_avg_full_price` como "bruto sem limpeza". `full_price` INCLUI limpeza; subtraia `reservation_avg_cleaning_fee`.
- ❌ Usar `daily_revenue_sapron_active` para franquia com imóveis inativos recentes — perde histórico. Use `daily_revenue_sapron` (versão completa).
- ❌ Rodar sem `list_databases(source='sirius')` primeiro — sufixos dos databases mudam.
- ❌ Enviar/rascunhar Slack ou gerar HTML sem confirmação explícita.

## Exemplo de invocação
```
/analise-faturamento-franquia Itatiana Marques de Moura
→ host_id 115, São Miguel dos Milagres/AL, 36 imóveis (18 ativos, 13 inativos, 3 onboarding)
→ Tabela 12M Set/2025–Ago/2026, Fat. Franquia total R$ 224.557,21, despesas R$ 4.057,90
```

## Extensões (sob demanda)
- **HTML padrão Seazone**: só quando a usuária pedir print/apresentação/relatório.
- **Top imóveis do ano**: acrescentar bloco com ranking dos 5 imóveis por faturamento e ocupação.
- **Comparação com concorrentes**: usar `competitors_plus` + `daily_revenue_competitors` (só se pedido).
- **Curva de reservas / booking pace**: usar `rm_booking_pace` do lake.
