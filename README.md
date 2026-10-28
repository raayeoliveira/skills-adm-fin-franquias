# Skills — Administrativo e Financeiro · BackOffice Franquias Seazone

Repositório oficial das skills da área de Administrativo e Financeiro do BackOffice Franquias.

**Owner da área (a partir de 31/10/2026):** Isabella (Coordenadora Adm/Fin)
**Gestora:** Rayanne Oliveira (BackOffice Franquias)
**Diretora:** Carol Espindola (Franquias)

---

## Como usar

Clone este repo na sua máquina e sincronize as skills com seu `~/.claude/skills/`:

```bash
git clone https://github.com/raayeoliveira/skills-adm-fin-franquias.git ~/skills-adm-fin-franquias

# linkar cada skill no diretório do Claude Code
for s in ~/skills-adm-fin-franquias/skills/*; do
  ln -sfn "$s" ~/.claude/skills/$(basename "$s")
done
```

Pra atualizar quando alguém publicar nova versão:

```bash
cd ~/skills-adm-fin-franquias && git pull
```

---

## Skills publicadas (lote 1 — herdadas de Rayanne, operadas pela área)

| Skill | O que faz | Cadência |
|---|---|---|
| `analise-faturamento-franquia` | Gera análise executiva do faturamento de uma franquia (últimos 12 meses, portfólio, diárias, reservas, taxa de limpeza, 8% + limpeza, despesas Sapron) | Sob demanda |
| `analise-comissao-enxoval` | Soma comissões Seazone do mês cruzando Matinali/RM + Lojinha + Jornada Enxoval | Mensal |
| `taxa-limpeza-antes` | Mostra a taxa de limpeza que cada imóvel cobrava ANTES dos ajustes da Calculadora 2026, com histórico de troca | Sob demanda |

## Skills a herdar do David (lote 2 — pendente de migração até 30/10/2026)

A inventariar e migrar durante o handover 48h (29-30/10/2026):

- [ ] `kpis-adm-fin-franquias` (David opera — lançamento diário dos KPIs da área)
- [ ] Skills de casos pontuais de precificação (triagem do form)
- [ ] Skills de conciliação de repasse
- [ ] Skills de monitoramento de inadimplência
- [ ] Skills de fechamento de comissão mensal
- [ ] Skills de recálculo de preço em lote
- [ ] Demais skills locais em `~/.claude/skills/` do David

**Procedimento de migração (David executa até 30/10):**

```bash
cd ~/skills-adm-fin-franquias
cp -r ~/.claude/skills/<nome-da-skill> skills/
git add skills/<nome-da-skill>
git commit -m "feat: migra skill <nome-da-skill> para repo oficial do time"
git push
```

## Permissões

Admin: Rayanne Oliveira, Isabella (Coord Adm/Fin), Carol Espindola

Qualquer alteração em `skills/` passa por PR com revisão da Isa.

---

**Última atualização:** 28/10/2026 · Rayanne Oliveira
