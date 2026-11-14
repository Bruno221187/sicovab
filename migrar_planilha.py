"""Migração única: traz os dados da planilha atual (Validação Sicovab SBR.xlsm) para o sistema.

Uso (com o ambiente ativado):
    python migrar_planilha.py "C:\\caminho\\Validação Sicovab SBR.xlsm"

Traz: Notas Sicovab, NBS, NBS Jack, Estoque Sicovab, Follow UP Vidros,
Notas não localizadas (com a Obs) e Notas rejeitadas (com data e motivo).
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from core import db
from core import importar as imp

RELATORIOS = [("Notas Sicovab", "notas"), ("NBS", "nbs"), ("NBS Jack", "nbs_jack"), ("Estoque sicovab", "estoque")]


def _decisoes(xls, aba, situacao, col_data=None, col_motivo=None, col_obs=None):
    if aba not in xls.sheet_names:
        return []
    df = pd.read_excel(xls, sheet_name=aba, dtype=object)
    cols = {imp.norm(c): c for c in df.columns}
    linhas = []
    for _, r in df.iterrows():
        chave = imp.txt(r.get(cols.get("NFECHAVE")))
        if not chave:
            continue
        cnpj, nome = imp.separar_emitente(r.get(cols.get("EMITENTE")))
        linhas.append({
            "chave": chave, "situacao": situacao,
            "motivo": imp.txt(r.get(cols.get(col_motivo))) if col_motivo else "",
            "obs": imp.txt(r.get(cols.get(col_obs))) if col_obs else "",
            "data": imp.data(r.get(cols.get(col_data))) if col_data else None,
            "numero": imp.inteiro(r.get(cols.get("NUMERO"))), "emitente": nome,
            "carga": imp.data(r.get(cols.get("CARGA"))), "saldo": imp.num(r.get(cols.get("SALDO"))),
        })
    return linhas


def main():
    ap = argparse.ArgumentParser(description="Migra a planilha atual para o sistema.")
    ap.add_argument("planilha", help="caminho do arquivo .xlsm")
    ap.add_argument("--usuario", default="Migração")
    ap.add_argument("--forcar", action="store_true", help="apaga Follow UP e decisões já existentes no sistema")
    a = ap.parse_args()

    db.iniciar()
    ja_tem = not db.ler("SELECT 1 FROM follow_up LIMIT 1").empty or not db.ler("SELECT 1 FROM decisoes LIMIT 1").empty
    if ja_tem and not a.forcar:
        print("O sistema já tem Follow UP ou decisões gravadas. Use --forcar para substituir.")
        sys.exit(1)

    print(f"Abrindo {a.planilha} ...")
    xls = pd.ExcelFile(a.planilha)
    nome = Path(a.planilha).name

    for aba, tipo in RELATORIOS:
        if aba in xls.sheet_names:
            _, df = imp.ler_arquivo(xls, tipos=[tipo], aba=aba)
            db.substituir_relatorio(tipo, df, f"{nome} [{aba}]", a.usuario)
            print(f"  {aba}: {len(df)} linhas")

    if a.forcar:
        with db.conectar() as con:
            con.execute("DELETE FROM follow_up")
            con.execute("DELETE FROM decisoes")

    if "Follow UP Vidros" in xls.sheet_names:
        _, fu = imp.ler_arquivo(xls, tipos=["followup"], aba="Follow UP Vidros")
        db.inserir_followup(fu, a.usuario, "Migração da planilha")
        print(f"  Follow UP Vidros: {len(fu)} peças")

    decisoes = (_decisoes(xls, "Notas não localizadas", "Não localizada", col_obs="OBS")
                + _decisoes(xls, "Notas rejeitadas", "Rejeitada", col_data="DATA", col_motivo="MOTIVO"))
    with db.conectar() as con:
        for d in decisoes:  # rejeitada vem depois e prevalece sobre "não localizada"
            con.execute(
                """INSERT INTO decisoes(chave, situacao, motivo, obs, data, usuario, numero, emitente, carga, saldo)
                   VALUES (:chave,:situacao,:motivo,:obs,:data,'Migração',:numero,:emitente,:carga,:saldo)
                   ON CONFLICT(chave) DO UPDATE SET situacao=excluded.situacao, motivo=excluded.motivo,
                   data=excluded.data""", d)
        db.registrar(con, a.usuario, "Migração da planilha", "Decisões", f"{len(decisoes)} notas")
    print(f"  Notas não localizadas/rejeitadas: {len(decisoes)}")
    print("Pronto.")


if __name__ == "__main__":
    main()
