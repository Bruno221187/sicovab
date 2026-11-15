"""Copia os dados do banco local (dados\\sicovab.db) para o banco online configurado em .streamlit\\secrets.toml.

Uso:  .venv\\Scripts\\python.exe enviar_para_nuvem.py            (só envia se o banco online estiver vazio)
      .venv\\Scripts\\python.exe enviar_para_nuvem.py --forcar   (apaga o que houver no online e envia de novo)

Precisa do endereço do DONO do banco (neondb_owner, pego no site do Neon) na variável DATABASE_URL:
o usuário do app (sicovab_app) não pode apagar o Histórico, de propósito.
"""
import argparse
import sqlite3
import sys

import pandas as pd

from core import db

TABELAS = db.TABELAS_BACKUP + ["senhas"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forcar", action="store_true")
    a = ap.parse_args()

    if not db.online():
        sys.exit("Não achei o endereço do banco online em .streamlit\\secrets.toml ([database] url = ...).")
    local = db.caminho_db()
    if not local.exists():
        sys.exit(f"Não achei o banco local em {local}.")

    db.iniciar()
    total_online = sum(len(db.ler(f"SELECT 1 FROM {t} LIMIT 1")) for t in TABELAS)
    if total_online and not a.forcar:
        sys.exit("O banco online já tem dados. Use --forcar para apagar e enviar de novo.")

    with sqlite3.connect(local) as src:
        dados = {t: pd.read_sql_query(f"SELECT * FROM {t}", src) for t in TABELAS}

    with db.conectar() as con:  # tudo ou nada
        for t in TABELAS:
            con.execute(f"DELETE FROM {t}")
            if len(dados[t]):
                dados[t].to_sql(t, con.conn, if_exists="append", index=False, chunksize=1000)
            print(f"  {t}: {len(dados[t])} linhas")
        for t in ("follow_up", "historico", "importacoes"):  # o contador de id continua do maior id copiado
            con.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)")
    print("Pronto: dados enviados para o banco online.")


if __name__ == "__main__":
    main()
