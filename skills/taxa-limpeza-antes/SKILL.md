---
name: taxa-limpeza-antes
description: >-
  Mostra a taxa de limpeza que cada imóvel cobrava ANTES dos ajustes pela nova Calculadora de Taxa
  de Limpeza 2026, lado a lado com a taxa de hoje e com cada troca feita depois (quando, de quanto
  para quanto e por onde entrou — Stays, automação da vistoria, Pipefy, ativação ou uma pessoa),
  a partir do histórico de cadastro do Sapron. Avisa quando a troca não deixou registro e só dá
  para saber a janela em que aconteceu. Serve para conferir um lote aplicado, responder o
  franqueado que pergunta "quanto era antes" ou levantar o valor para reverter. Use quando
  pedirem "qual era a taxa antes", "taxa antiga do imóvel X", "o que mudou na taxa da franquia X",
  "antes e depois do lote de ajuste", "o que foi ajustado hoje na taxa", "quanto o prédio X
  cobrava antes da calculadora", "reverter a taxa de limpeza", ou "/taxa-limpeza-antes".
---

# Taxa de limpeza antes da nova calculadora

**Responsável:** David Soares (Backoffice de Franquias)

Entrega a tabela **antes × depois** da taxa de limpeza. Para poucos imóveis, a resposta vai direto
no chat. Para lotes maiores, gera um HTML com um CSV ao lado. A fonte é o histórico de cadastro do
Sapron (`property_audit`), que grava uma foto do cadastro a cada alteração. Mas **o histórico não
registra todas as trocas**, e a skill diz isso sempre que acontece (ver "O que o histórico não
mostra").

## Pré-requisito

Acesso de leitura ao banco do Sapron por MCP: a ferramenta `consultar_banco` do servidor `sapron`.
Se ela não estiver disponível na sessão, pare e peça o acesso ao time de Tecnologia. Não tente
outro caminho.

## 1. Definir o corte e o recorte

**Corte padrão: `2026-09-14 00:00:00-03`**, o dia da primeira revisão de preço pela Calculadora
2026. Os ajustes em massa entraram pela Stays depois disso, em 17/09, 21/09 e 25/09. Antes de
17/09, o sync da Stays mexia em menos de 15 imóveis por dia. Se o pedido citar outra data ("antes
do lote de 21/09"), use essa data à meia-noite de Brasília.

O `{FILTRO}` é uma condição sobre `p` (`property_property`) e `u` (usuário do franqueado):

| Pedido | `{FILTRO}` |
|---|---|
| imóveis citados | `p.code IN ('ABC0101','XYZ0202')` |
| um franqueado | `p.status IN ('Active','Onboarding') AND trim(coalesce(u.first_name,'') \|\| ' ' \|\| coalesce(u.last_name,'')) = 'Nome Completo'` |
| um prédio | `p.status IN ('Active','Onboarding') AND p.code LIKE 'VST%'` |
| lote de um dia | `p.id IN (SELECT a.property_id FROM property_audit a WHERE a.changed_by_celery_task = 'dispatch_stays_sync_cleaning_fee' AND (a.changed_at AT TIME ZONE 'America/Sao_Paulo')::date = DATE 'AAAA-MM-DD')` |
| toda a base ativa | `p.status = 'Active' AND p.cleaning_fee > 0` |

- **Franqueado:** confirme antes o nome exato. Use
  `SELECT first_name, last_name FROM account_user WHERE first_name ILIKE '%...%' AND last_name ILIKE '%...%'`.
  Nome parecido engana, e um mesmo código de franquia pode ter dois franqueados. Por isso a
  atribuição é sempre por imóvel.
- **Não filtre só `Active`** quando o pedido é "os imóveis de alguém". Imóvel em Onboarding também
  tem taxa e muda.

## 2. Rodar a consulta

Leia `scripts/historico.sql`, troque `{CORTE}` e `{FILTRO}` e rode no `consultar_banco`.

- O filtro de segurança do MCP **recusa qualquer texto com palavras de escrita do SQL**, mesmo
  dentro de um nome de coluna ou de um literal. A query não usa essas palavras; não as introduza.
  Se você escrever uma consulta auxiliar, evite `operation = '...'` com o valor de edição e
  prefira `fields_changed`.
- Resultado grande é salvo em arquivo pela ferramenta. Use esse caminho no passo 3, sem copiar.

## 3. Entregar

**Até uns 15 imóveis:** responda no chat com a tabela
`Imóvel | Status | Antes | Depois | % | Quando e por onde`.

**Lote maior:**

```bash
python3 <pasta da skill>/scripts/gerar.py RESULTADO.json SAIDA.html \
  --corte "14/09/2026" --titulo "<frase com o número principal>" --recorte "<o que foi consultado>"
```

Salve o HTML na Área de Trabalho da pessoa, se ela existir (no WSL,
`/mnt/c/Users/<usuário>/Desktop`). Se não existir, use a pasta atual. O CSV sai com o mesmo nome.
Os imóveis ficam em cinco grupos: desceram, subiram, iguais, sem taxa hoje e sem taxa antes do
corte. Cada grupo tem um botão que copia `CÓDIGO, TAXA DE ANTES`, o formato para pedir reversão. O
script confere que a soma dos grupos bate com o total.

Se o recorte juntar mais de um lote, passe `--lotes lotes.json`, um JSON `{código: rótulo}`, e a
tabela ganha a coluna **Lote**. Para separar lotes do mesmo dia, use a hora da troca.

No resumo do chat, informe:

- quantos imóveis desceram e quantos subiram, com a mediana da diferença;
- quais mudaram mais de uma vez depois do corte;
- quais trocaram **sem registro**;
- se o total não bate com o que foi aplicado.

## O que o histórico não mostra

Leia antes de afirmar qualquer data ou autoria.

- **Troca sem registro nenhum.** Em 25/09/2026, 197 imóveis com taxa (114 de 3.441 Active e 83 de 180 Onboarding) estavam
  com taxa diferente da última foto do histórico. A query devolve `taxa_ult_foto` e
  `data_ult_foto`, e o gerador marca **"depois de DD/MM · sem registro no histórico"**. Diga que a
  troca foi depois dessa data e que **não dá para saber quando nem por onde pelo Sapron**.
- **Troca pega por uma foto posterior.** Às vezes a troca não gera linha própria e só aparece na
  foto seguinte, que registrou outro campo. O gerador mostra **"entre DD/MM e DD/MM · sem registro
  próprio"**: a troca aconteceu nessa janela, e a origem daquela linha não é a de quem mudou a
  taxa.
- **A taxa de antes pode estar errada** se houve uma troca sem registro antes do corte. Em resposta
  que vai para franqueado ou que embasa reversão, confirme com outra foto da base: um levantamento
  salvo, um export da calculadora ou a Stays.
- **A origem diz por onde a troca entrou, não quem pediu.** "Stays (sync)" é o valor que alguém
  mudou na Stays e o sync trouxe para o Sapron. Não afirme que foi ajuste da calculadora nem pedido
  do franqueado sem essa informação vir de quem pediu o levantamento.

## Armadilhas já medidas

- **O sync da Stays chega aos poucos.** Um lote aplicado na Stays às 18h ainda estava entrando no
  Sapron quase uma hora depois (71 de 128 às 18h55). Se o total não bater, diga quantos chegaram e
  até que horas. Não trate isso como falha.
- **O sync da Stays desfaz a automação da vistoria.** A vistoria grava no Sapron, e no ciclo
  seguinte o sync traz de volta o valor da Stays. Exemplo: 480 → 400 → 480 em 12 h, ou imóvel
  indo e voltando duas vezes em três dias. Imóvel com duas ou mais trocas merece menção.
- **Mesmo código, dois cadastros.** Na troca de franquia o Sapron abre cadastro novo com o mesmo
  código e deixa o antigo `Inactive`, com a taxa de antes. A query já trata: ignora o `Inactive` e
  busca o histórico pelo código. Sem isso saem linhas duplicadas e "sem taxa antes" falso.
- **Zero e vazio são ruído.** O sync da Stays grava `0` de passagem quando a taxa está embutida. A
  consulta ignora esses valores na sequência. Imóvel zerado hoje cai em "sem taxa hoje", e isso é
  fato a reportar.
- **Sem taxa antes do corte** é imóvel cadastrado ou precificado depois do corte. Não existe valor
  anterior: não o invente a partir da régua da calculadora.
- **Não corte o histórico por data para achar o valor anterior.** O valor anterior de uma troca
  pode estar meses antes. A query usa o histórico inteiro e só filtra as trocas depois do corte.

## Teste

`python3 tests/test_gerar.py` roda o gerador numa amostra com cada caso acima (troca registrada,
troca sem registro, troca pega por foto posterior, vai e volta, sem taxa antes, zerada) e confere
a classificação e os rótulos.
