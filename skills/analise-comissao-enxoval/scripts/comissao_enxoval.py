#!/usr/bin/env python3
"""Comissoes Seazone de enxoval/lojinha: planilhas + lojinha (endpoint NFs) + app Jornada Enxoval.

Uso:
  python3 comissao_enxoval.py <YYYY-MM> <csv_matinali.txt> <csv_rm.txt>

Os dois arquivos sao os resultados do download_file_content do Google Drive
(JSON {content: <base64 do csv>}). Nada e escrito em lugar nenhum: read-only.
"""
import base64
import collections
import csv
import io
import json
import os
import re
import sys
import urllib.request

NF_URL = "https://qzucnqbmuqozkhfltgcl.supabase.co/functions/v1/nf-commissions?month={mes}"
ITENS_URL = "https://qzucnqbmuqozkhfltgcl.supabase.co/functions/v1/loja-full-export?table=order_items"
SUPABASE_PROJETO = "boaystsxsyntdvogdakn"
SUPABASE_QUERY_URL = f"https://api.supabase.com/v1/projects/{SUPABASE_PROJETO}/database/query"
UA = "Mozilla/5.0"

# planilha -> (col NF 0-based na planilha inteira, col Comissao Seazone)
PLANILHAS = {"Matinali": (21, 27), "RM Enxoval": (23, 32)}
FORNECEDORES_5PCT = ["Harus", "IZY BRINDES", "Loja do Guarda po", "Loja do Guarda pó",
                     "Matinali", "Momento Amenities", "RM Enxoval"]
COMISSAO_APP_PCT = 0.05
PLANILHA_DO_FORNECEDOR = {"Matinali": "Matinali", "RM Enxoval": "RM Enxoval", "RM": "RM Enxoval"}

SOMAR_TAB = {24.5: 0.0, 29.5: 0.0, 34.5: 0.0, 78.5: 0.0, 86.5: 0.0, 92.5: 0.0,
             35.0: 4.5, 40.0: 4.5, 45.0: 4.5, 110.0: 25.5, 118.0: 25.5, 124.0: 25.5}


def brl(v):
    s = f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {s}"


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def sql(query):
    """Management API (SUPABASE_PAT) e, se falhar, Postgres read-only (ENXOVAL_RO_DATABASE_URL)."""
    pat = os.environ.get("SUPABASE_PAT")
    if pat:
        try:
            body = json.dumps({"query": query, "read_only": True}).encode()
            req = urllib.request.Request(SUPABASE_QUERY_URL, data=body, headers={
                "Authorization": f"Bearer {pat}", "Content-Type": "application/json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"[APP] Management API falhou ({e}) — tentando Postgres read-only")

    dsn = os.environ.get("ENXOVAL_RO_DATABASE_URL")
    if not dsn:
        raise RuntimeError("sem SUPABASE_PAT valido e sem ENXOVAL_RO_DATABASE_URL "
                           "(source ~/.enxoval_ro.env)")
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(dsn + "?sslmode=require")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def ler_planilha(caminho, idx_nf, idx_com, mes):
    ano, mm = mes.split("-")
    pad = re.compile(r"\d{2}/" + mm + "/" + ano)
    d = json.load(open(caminho))
    txt = base64.b64decode(d["content"]).decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(txt)))
    total, n, linhas = 0.0, 0, []
    for i, row in enumerate(rows[1:], start=2):  # linha 1 = cabecalho
        if len(row) <= max(idx_nf, idx_com):
            continue
        if not pad.fullmatch(row[idx_nf].strip()):
            continue
        v = row[idx_com].replace("R$", "").replace(".", "").replace(",", ".").strip()
        try:
            val = float(v)
        except ValueError:
            continue
        total += val
        n += 1
        linhas.append(i)
    return {"titulo": d.get("title"), "total": total, "nfs": n, "linhas": linhas}


def somar_malhas(nf, mes):
    pedidos = {i["order_id"] for i in nf.get("invoices", [])
               if i.get("supplier_name") == "Somar Malhas"}
    if not pedidos:
        return {"total": 0.0, "pedidos": 0, "itens": 0, "sem_comissao_itens": 0, "nao_mapeados": {}}
    bruto = get_json(ITENS_URL)
    itens = bruto if isinstance(bruto, list) else (bruto.get("data") or bruto.get("order_items") or [])
    total, qtd_itens, sem_com = 0.0, 0, 0
    nao_map = collections.Counter()
    for it in itens:
        if str(it.get("supplier_name", "")).lower() != "somar malhas":
            continue
        if it.get("order_id") not in pedidos:
            continue
        up = float(it["unit_price"])
        q = float(it.get("quantity") or 0)
        qtd_itens += q
        if up in SOMAR_TAB:
            total += SOMAR_TAB[up] * q
            if SOMAR_TAB[up] == 0:
                sem_com += q
        else:
            nao_map[up] += q
    return {"total": total, "pedidos": len(pedidos), "itens": int(qtd_itens),
            "sem_comissao_itens": int(sem_com), "nao_mapeados": dict(nao_map)}


def pedidos_app(mes, plan):
    """Pedidos enviados no app com NF emitida no mes. Dedupe: so ignora o card quando
    origemPlanilha.linha aponta para uma linha que a PLANILHA ja somou no mes (planilha vence).
    Card do Agente de Adequacao (origemPlanilha sem linha, ou linha sem NF no mes na planilha)
    ENTRA pelo app — senao some das duas fontes (Henry, 23/09/2026)."""
    q = f"""
      select id, board,
             dados->>'fornecedor' as fornecedor,
             dados->>'numero' as numero,
             dados->>'imovel' as imovel,
             coalesce(dados->'campos'->'nf-data-emissao'->>'valor', dados->'campos'->>'nf-data-emissao') as nf_emissao,
             coalesce((dados->>'totalItensCents')::bigint,
                      (dados->>'totalCents')::bigint - coalesce((dados->>'freteCents')::bigint,0)) as itens_cents,
             (dados->'origemPlanilha' is not null) as da_planilha,
             dados->'origemPlanilha'->>'linha' as linha_planilha
      from enxoval.pedidos_kanban
      where lower(coalesce(dados->>'fase','')) like 'enviado%'
        and coalesce(dados->'campos'->'nf-data-emissao'->>'valor', dados->'campos'->>'nf-data-emissao') >= '{mes}-01'
        and coalesce(dados->'campos'->'nf-data-emissao'->>'valor', dados->'campos'->>'nf-data-emissao') < (date '{mes}-01' + interval '1 month')::text
    """.replace("\n", " ")
    linhas = sql(q)
    por_forn = collections.defaultdict(lambda: {"comissao": 0.0, "pedidos": 0, "valor": 0.0})
    ignorados, agente = [], []
    for r in linhas:
        if r["da_planilha"]:
            p = plan.get(PLANILHA_DO_FORNECEDOR.get(r["fornecedor"] or ""), {})
            if r["linha_planilha"] and int(r["linha_planilha"]) in p.get("linhas", []):
                ignorados.append(f"{r['id']} ({r['imovel']}, linha {r['linha_planilha']})")
                continue
            agente.append(f"{r['id']} ({r['imovel']})")
        valor = (r["itens_cents"] or 0) / 100.0
        f = r["fornecedor"] or "(sem fornecedor)"
        por_forn[f]["comissao"] += valor * COMISSAO_APP_PCT
        por_forn[f]["valor"] += valor
        por_forn[f]["pedidos"] += 1
    return {"por_fornecedor": dict(por_forn), "ignorados_dedupe": ignorados,
            "agente_somados": agente, "total_linhas": len(linhas)}


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    mes, csv_mat, csv_rm = sys.argv[1], sys.argv[2], sys.argv[3]

    plan = {"Matinali": ler_planilha(csv_mat, *PLANILHAS["Matinali"], mes),
            "RM Enxoval": ler_planilha(csv_rm, *PLANILHAS["RM Enxoval"], mes)}
    nf = get_json(NF_URL.format(mes=mes))
    endpoint = {c["supplier_name"]: c for c in nf.get("commission_by_supplier", [])}
    somar = somar_malhas(nf, mes)
    app = pedidos_app(mes, plan)

    out = {"mes": mes, "planilhas": plan, "endpoint": endpoint, "somar_malhas": somar, "app": app}

    print(f"=== COMISSOES ENXOVAL/LOJINHA {mes} ===\n")
    print("[PLANILHAS] (fonte que vence no dedupe)")
    for k, v in plan.items():
        print(f"  {k}: {brl(v['total'])} ({v['nfs']} NFs) — {v['titulo']}")
    print("\n[LOJINHA / endpoint nf-commissions] 5% por fornecedor")
    for f in ["Harus", "IZY BRINDES", "Loja do Guarda pó", "Matinali", "Momento Amenities", "RM Enxoval"]:
        c = endpoint.get(f)
        print(f"  {f}: {brl(c['commission']) if c else brl(0)} ({c['nf_count'] if c else 0} NFs)")
    outros = [k for k in endpoint if k not in FORNECEDORES_5PCT and k != "Somar Malhas"]
    if outros:
        print(f"  (fornecedores no endpoint fora do mapeamento, NAO somados: {outros})")
    print(f"\n[SOMAR MALHAS] por item: {brl(somar['total'])} "
          f"({somar['pedidos']} pedidos, {somar['itens']} itens, "
          f"{somar['sem_comissao_itens']} itens sem comissao)")
    if somar["nao_mapeados"]:
        print(f"  ATENCAO precos nao mapeados: {somar['nao_mapeados']}")
    print(f"\n[APP JORNADA ENXOVAL] enviados com nf-data-emissao no mes = {app['total_linhas']} "
          f"card(s); {len(app['ignorados_dedupe'])} ignorado(s) por dedupe (linha ja somada na planilha)")
    if not app["por_fornecedor"]:
        print("  nenhum pedido nativo do app com NF no mes -> R$ 0,00")
    for f, v in sorted(app["por_fornecedor"].items()):
        print(f"  {f}: {brl(v['comissao'])} (5% de {brl(v['valor'])} sem frete, {v['pedidos']} pedidos)")
    if app["agente_somados"]:
        print(f"  {len(app['agente_somados'])} card(s) com origemPlanilha SOMADOS pelo app "
              f"(Agente de Adequacao / linha sem NF no mes na planilha): {', '.join(app['agente_somados'])}")
    if app["ignorados_dedupe"]:
        print(f"  dedupe (planilha venceu): {', '.join(app['ignorados_dedupe'])}")

    # consolidado
    forn = collections.defaultdict(float)
    for k, v in plan.items():
        forn[k] += v["total"]
    for f in ["Harus", "IZY BRINDES", "Loja do Guarda pó", "Matinali", "Momento Amenities", "RM Enxoval"]:
        if f in endpoint:
            forn[f] += endpoint[f]["commission"]
    forn["Somar Malhas"] += somar["total"]
    for f, v in app["por_fornecedor"].items():
        forn[f] += v["comissao"]

    print("\n[CONSOLIDADO POR FORNECEDOR]")
    for f in sorted(forn):
        print(f"  {f}: {brl(forn[f])}")
    enx = forn.get("Matinali", 0) + forn.get("RM Enxoval", 0)
    geral = sum(forn.values())
    print(f"\n  Enxoval (Matinali + RM Enxoval): {brl(enx)}")
    print(f"  Sem enxoval:                     {brl(geral - enx)}")
    print(f"  COMISSAO GERAL:                  {brl(geral)}")
    print("\nJSON=" + json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
