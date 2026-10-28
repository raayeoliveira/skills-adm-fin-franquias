-- Taxa de limpeza ANTES dos ajustes pela Calculadora 2026 × taxa de hoje, com o histórico de mudanças.
-- Troque os dois marcadores antes de rodar no MCP do Sapron (ferramenta consultar_banco):
--   {CORTE}  → instante do corte, ex.: 2026-09-14 00:00:00-03
--   {FILTRO} → condição sobre p (property_property) e u (account_user do franqueado), ver SKILL.md
-- O filtro de segurança do MCP recusa qualquer texto que contenha as palavras de escrita do SQL
-- (inclusive dentro de nomes de coluna). Esta query não as usa; não as introduza.
WITH alvo AS (
  SELECT p.id, p.code, p.status, p.cleaning_fee AS taxa_hoje,
         trim(coalesce(u.first_name,'') || ' ' || coalesce(u.last_name,'')) AS franqueado
  FROM property_property p
  LEFT JOIN account_host h ON h.id = p.host_id
  LEFT JOIN account_user u ON u.id = h.user_id
  WHERE p.code NOT LIKE 'TST%' AND p.status <> 'Inactive' AND ({FILTRO})
),
-- Cada linha do property_audit é uma FOTO do cadastro inteiro. Busca pelo CÓDIGO, não pelo id: na
-- troca de franquia o Sapron abre cadastro novo com o mesmo código e o antigo fica Inactive.
antes AS (
  SELECT DISTINCT ON (a.code) a.code, a.cleaning_fee AS taxa_antes
  FROM property_audit a JOIN alvo ON alvo.code = a.code
  WHERE a.changed_at < TIMESTAMPTZ '{CORTE}' AND a.cleaning_fee > 0
  ORDER BY a.code, a.changed_at DESC, a.id DESC
),
serie AS (
  -- 0 e nulo são ruído do sync da Stays (taxa embutida): ficam fora da sequência de valores
  SELECT a.code, a.changed_at, a.cleaning_fee,
         coalesce(nullif(a.changed_by_celery_task,''), u.email, 'desconhecido') AS origem,
         -- troca que não foi registrada na hora aparece na foto seguinte, com outro campo alterado:
         -- aí a data é só o limite, e a troca aconteceu entre a foto anterior e esta
         (coalesce(a.fields_changed,'') ILIKE '%cleaning_fee%') AS registrada,
         lag(a.cleaning_fee) OVER w AS anterior,
         lag(a.changed_at) OVER w AS desde
  FROM property_audit a JOIN alvo ON alvo.code = a.code
  LEFT JOIN account_user u ON u.id = a.changed_by_user_id
  WHERE a.cleaning_fee > 0
  WINDOW w AS (PARTITION BY a.code ORDER BY a.changed_at, a.id)
),
hist AS (
  SELECT code, count(*) AS mudancas,
         string_agg(to_char(changed_at AT TIME ZONE 'America/Sao_Paulo','DD/MM/YYYY HH24:MI')
                    || ';' || anterior::int || ';' || cleaning_fee::int || ';' || origem
                    || ';' || CASE WHEN registrada THEN 'r' ELSE 'f' END
                    || ';' || to_char(desde AT TIME ZONE 'America/Sao_Paulo','DD/MM/YYYY'),
                    '|' ORDER BY changed_at) AS historico
  FROM serie
  WHERE changed_at >= TIMESTAMPTZ '{CORTE}' AND anterior IS NOT NULL AND cleaning_fee <> anterior
  GROUP BY code
),
ult AS (
  -- última foto do histórico. Se a taxa dela difere da de hoje, a troca não deixou rastro nenhum
  -- (medido em 25/09/2026: 197 imóveis Active/Onboarding com taxa nessa situação)
  SELECT DISTINCT ON (a.code) a.code, a.cleaning_fee AS taxa_ult_foto,
         to_char(a.changed_at AT TIME ZONE 'America/Sao_Paulo','DD/MM/YYYY') AS data_ult_foto
  FROM property_audit a JOIN alvo ON alvo.code = a.code
  WHERE a.cleaning_fee > 0   -- 0 de passagem do sync não é foto válida: geraria troca sem registro falsa
  ORDER BY a.code, a.changed_at DESC, a.id DESC
)
SELECT alvo.code, alvo.franqueado, alvo.status,
       antes.taxa_antes::int AS taxa_antes, alvo.taxa_hoje::int AS taxa_hoje,
       coalesce(hist.mudancas, 0) AS mudancas, hist.historico,
       ult.taxa_ult_foto::int AS taxa_ult_foto, ult.data_ult_foto
FROM alvo
LEFT JOIN antes ON antes.code = alvo.code
LEFT JOIN hist ON hist.code = alvo.code
LEFT JOIN ult ON ult.code = alvo.code
ORDER BY alvo.code
