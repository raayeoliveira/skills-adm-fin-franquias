# -*- coding: utf-8 -*-
"""Taxa de limpeza antes × hoje: lê o resultado do historico.sql e escreve HTML + CSV.

uso: python3 gerar.py RESULTADO.json SAIDA.html --corte "14/09/2026" [--titulo "..."] [--recorte "..."]
RESULTADO.json é a saída do mcp__sapron__consultar_banco (lista de linhas, ou o arquivo salvo
pela ferramenta quando o resultado é grande).
"""
import argparse, csv, html, io, json, os, pathlib, re

ORIGEM = {
    "dispatch_stays_sync_cleaning_fee": "Stays (sync)",
    "vistoria-client@seazone.com.br": "automação da vistoria",
    "cloud@seazone.com.br": "automação do Pipefy",
    "automacao.hospedagem@seazone.com.br": "ativação do imóvel",
    "stays_handle_reservation_task": "Stays (reserva)",
}
def origem(o):
    if o in ORIGEM: return ORIGEM[o]
    if "@" in o: return o.split("@")[0]
    return o

def ler(p):
    t = pathlib.Path(p).read_text(encoding="utf-8").strip()
    d = json.loads(t)
    if isinstance(d, dict):
        d = next(v for v in d.values() if isinstance(v, list))
    return d

def num(v):
    return None if v in (None, "") else int(float(v))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada"); ap.add_argument("saida")
    ap.add_argument("--corte", required=True, help="data do corte, como aparece no texto")
    ap.add_argument("--titulo", default="Taxa de limpeza antes da nova calculadora")
    ap.add_argument("--recorte", default="", help="o que foi consultado, em uma frase")
    ap.add_argument("--lotes", help="JSON {código: rótulo do lote}; acrescenta a coluna Lote")
    a = ap.parse_args()

    LOTE = json.loads(pathlib.Path(a.lotes).read_text(encoding="utf-8")) if a.lotes else None
    linhas = []
    for r in ler(a.entrada):
        antes, hoje = num(r.get("taxa_antes")), num(r.get("taxa_hoje"))
        hist = []
        for item in (r.get("historico") or "").split("|"):
            if not item: continue
            partes = item.split(";")
            quando, de, para, quem = partes[:4]
            registrada = len(partes) < 5 or partes[4] == "r"
            desde = partes[5] if len(partes) > 5 else ""
            # troca registrada: data exata. Pega por foto posterior: só a janela em que aconteceu
            rot = quando[:5] + quando[10:16] if registrada else f"entre {desde[:5]} e {quando[:5]}"
            hist.append((rot, int(de), int(para), origem(quem) if registrada else "sem registro próprio"))
        ult, dult = num(r.get("taxa_ult_foto")), r.get("data_ult_foto") or ""
        if ult and ult > 0 and hoje and hoje > 0 and ult != hoje:
            # nenhuma foto depois da troca: só se sabe que foi depois da última
            hist.append((f"depois de {dult[:5]}", ult, hoje, "sem registro no histórico"))
        if antes is None: cat = "sem"
        elif hoje is None or hoje == 0: cat = "zerada"
        elif hoje < antes: cat = "desceu"
        elif hoje > antes: cat = "subiu"
        else: cat = "igual"
        linhas.append(dict(code=r["code"], franqueado=r.get("franqueado") or "—",
                           status=r.get("status") or "", antes=antes, hoje=hoje, cat=cat, hist=hist))

    CATS = [("desceu", "Desceram", "A taxa de hoje é menor que a de antes do corte."),
            ("subiu", "Subiram", "A taxa de hoje é maior que a de antes do corte."),
            ("igual", "Iguais", "Mesma taxa de antes. Onde há histórico, mudou e voltou."),
            ("zerada", "Sem taxa hoje", "Tinham taxa antes do corte e hoje estão sem valor no Sapron."),
            ("sem", "Sem taxa antes do corte", "Cadastrados ou precificados depois do corte: não há valor anterior.")]
    por = {k: [l for l in linhas if l["cat"] == k] for k, _, _ in CATS}
    assert sum(len(v) for v in por.values()) == len(linhas)

    def pct(l):
        return (l["hoje"] - l["antes"]) / l["antes"] if l["antes"] and l["hoje"] else 0
    def fmt_hist(h):
        if not h: return "—"
        return "<br>".join(f"{html.escape(q)} · {de} → {pa} · {html.escape(o)}" for q, de, pa, o in h)

    secoes = []
    for i, (k, nome, explica) in enumerate(CATS):
        g = sorted(por[k], key=lambda l: (-abs(pct(l)), l["code"]))
        if not g: continue
        copia = "\n".join(f'{l["code"]}, {l["antes"]}' for l in g if l["antes"])
        rows = "\n".join(f"""            <tr>
              <th scope="row">{html.escape(l["code"])}<span class="uf">{html.escape(l["status"])}</span></th>
              <td class="nome">{html.escape(l["franqueado"])}</td>{f'<td class="nome">{html.escape(LOTE.get(l["code"], "—"))}</td>' if LOTE else ""}
              <td class="num">{l["antes"] if l["antes"] is not None else "—"}</td>
              <td class="num alvo">{l["hoje"] if l["hoje"] is not None else "—"}</td>
              <td class="num dif">{f'{l["hoje"] - l["antes"]:+d}' if l["antes"] and l["hoje"] else "—"}</td>
              <td class="num pct">{f'{pct(l)*100:+.0f}%' if l["antes"] and l["hoje"] else "—"}</td>
              <td class="motivo">{fmt_hist(l["hist"])}</td>
            </tr>""" for l in g)
        botao = (f'''      <div class="barra">
        <button class="copiar" type="button" data-alvo="c{i}">Copiar taxa de antes <span class="qtd">{copia.count(chr(10)) + 1}</span></button>
        <textarea id="c{i}" hidden>{html.escape(copia)}</textarea>
      </div>''' if copia else "")
        secoes.append(f"""    <section>
      <h2>{nome}
        <span class="conta-bloco">{len(g)} imóve{'is' if len(g) != 1 else 'l'}. {explica}</span>
      </h2>
{botao}
      <div class="rolagem largura">
        <table>
          <thead><tr>
            <th scope="col">Imóvel</th><th scope="col">Franquia</th>{'<th scope="col">Lote</th>' if LOTE else ""}
            <th scope="col" class="num">Antes</th><th scope="col" class="num">Hoje</th>
            <th scope="col" class="num">Dif.</th><th scope="col" class="num">%</th>
            <th scope="col">Mudanças depois do corte</th>
          </tr></thead>
          <tbody>
{rows}
          </tbody>
        </table>
      </div>
    </section>""")

    resumo = "\n".join(f"""      <li><b>{len(por[k])}</b><span>{nome.lower()}
        <small>{explica}</small></span></li>""" for k, nome, explica in CATS if por[k])
    css = pathlib.Path(__file__).with_name("estilo.css").read_text(encoding="utf-8")
    recorte = f"<p>{html.escape(a.recorte)}</p>" if a.recorte else ""
    doc = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Taxa de limpeza antes</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body>
<div class="folha">
  <p class="chapeu">Backoffice de Franquias · taxa de limpeza</p>
  <h1>{html.escape(a.titulo)}</h1>
  <p class="linha-fina">
    Taxa vigente no Sapron antes de <strong>{html.escape(a.corte)}</strong> comparada com a taxa de
    hoje, para <strong>{len(linhas)}</strong> imóve{'is' if len(linhas) != 1 else 'l'}.
  </p>
  {recorte}
  <ul class="resumo">
{resumo}
  </ul>
{chr(10).join(secoes)}
  <footer>
    <p>
      Fonte: Sapron, histórico de cadastro (<code>property_audit</code>). A taxa de antes é a última
      gravada antes do corte; valores zerados ou vazios, que o sync da Stays grava de passagem, são
      ignorados. A coluna de mudanças lista cada troca de valor depois do corte, com data, hora e
      origem. O botão copia <code>CÓDIGO, TAXA DE ANTES</code>, uma linha por imóvel.
    </p>
  </footer>
</div>
<script>
  document.addEventListener('click', function (ev) {{
    var b = ev.target.closest('.copiar'); if (!b) return;
    var fonte = document.getElementById(b.dataset.alvo); if (!fonte) return;
    var rotulo = b.childNodes[0].nodeValue;
    function ok() {{ b.classList.add('feito'); b.childNodes[0].nodeValue = 'Copiado ';
      setTimeout(function () {{ b.classList.remove('feito'); b.childNodes[0].nodeValue = rotulo; }}, 2000); }}
    function manual() {{ b.childNodes[0].nodeValue = 'Selecione e copie ';
      fonte.hidden = false; fonte.style.width = '100%'; fonte.style.minHeight = '8rem'; fonte.select(); }}
    if (navigator.clipboard && window.isSecureContext) {{ navigator.clipboard.writeText(fonte.value).then(ok, manual); return; }}
    var ta = document.createElement('textarea'); ta.value = fonte.value; ta.style.position = 'fixed'; ta.style.top = '-1000px';
    document.body.appendChild(ta); ta.select();
    try {{ document.execCommand('copy') ? ok() : manual(); }} catch (e) {{ manual(); }} finally {{ document.body.removeChild(ta); }}
  }});
</script>
</body>
</html>
"""
    pathlib.Path(a.saida).write_text(doc, encoding="utf-8")
    csv_p = re.sub(r"\.html?$", "", a.saida) + ".csv"
    with io.open(csv_p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["imovel", "franqueado", "lote", "status", "taxa_antes", "taxa_hoje", "diferenca", "situacao", "mudancas_depois_do_corte"])
        for l in sorted(linhas, key=lambda l: l["code"]):
            w.writerow([l["code"], l["franqueado"], (LOTE or {}).get(l["code"], ""), l["status"], l["antes"] or "", l["hoje"] or "",
                        (l["hoje"] - l["antes"]) if l["antes"] and l["hoje"] else "", l["cat"],
                        " | ".join(f"{q} {de}->{pa} ({o})" for q, de, pa, o in l["hist"])])
    print(f"{len(linhas)} imóveis ·", " · ".join(f"{nome.lower()}: {len(por[k])}" for k, nome, _ in CATS))
    print("HTML:", a.saida); print("CSV:", csv_p)

if __name__ == "__main__":
    main()
