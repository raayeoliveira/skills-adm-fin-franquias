"""Roda: python3 tests/test_gerar.py  (sem dependências além do Python 3)."""
import csv, pathlib, subprocess, sys, tempfile

AQUI = pathlib.Path(__file__).parent
GERAR = AQUI.parent / "scripts" / "gerar.py"

def main():
    with tempfile.TemporaryDirectory() as d:
        html = pathlib.Path(d) / "saida.html"
        r = subprocess.run([sys.executable, str(GERAR), str(AQUI / "amostra.json"), str(html),
                            "--corte", "14/09/2026"], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        linhas = {l["imovel"]: l for l in csv.DictReader(open(html.with_suffix(".csv"), encoding="utf-8-sig"), delimiter=";")}
        texto = html.read_text(encoding="utf-8")

        assert len(linhas) == 8
        assert linhas["BIP70006"]["situacao"] == "subiu"
        assert linhas["RFM0044"]["situacao"] == "desceu"
        # troca sem nenhuma foto depois: só a janela aberta a partir da última foto
        assert "depois de 16/09" in linhas["RFM0044"]["mudancas_depois_do_corte"]
        # troca pega por foto posterior: janela entre as duas fotos, não data exata
        assert "entre 15/09 e 20/09" in linhas["FOTO0001"]["mudancas_depois_do_corte"]
        assert "sem registro próprio" in linhas["FOTO0001"]["mudancas_depois_do_corte"]
        # vai e volta: três trocas listadas, na ordem
        assert linhas["UNE1105"]["mudancas_depois_do_corte"].count("->") == 3
        assert linhas["PRY0002"]["situacao"] == "igual"
        assert linhas["BIP0002"]["situacao"] == "sem"
        assert linhas["ZER0001"]["situacao"] == "zerada"
        # foto zerada de passagem do sync não é troca sem registro
        assert linhas["ZTR0001"]["situacao"] == "igual"
        assert linhas["ZTR0001"]["mudancas_depois_do_corte"] == ""
        assert "Copiar taxa de antes" in texto
    print("ok")

if __name__ == "__main__":
    main()
