"""Banco de dados: estrutura, leitura, gravação, histórico e backup.

Funciona com dois bancos:
- PostgreSQL online (Neon, Supabase...) quando existe o endereço em .streamlit/secrets.toml ([database] url = "...")
  ou na variável de ambiente DATABASE_URL  -> é o que roda na nuvem;
- SQLite local (dados\\sicovab.db) quando não existe -> bom para testes no próprio computador.
"""
import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import ssl
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, event, make_url

from . import config

BASE = Path(__file__).resolve().parent.parent
PASTA_DADOS = BASE / "dados"

SCHEMA = """
CREATE TABLE IF NOT EXISTS notas_sicovab (
    chave TEXT, numero INTEGER, emissao TEXT, carga TEXT, cnpj TEXT, emitente TEXT,
    aceito TEXT, itens REAL, vab REAL, subst REAL, aee REAL, repas REAL,
    devolvido REAL, cancelado REAL, saldo REAL
);
CREATE TABLE IF NOT EXISTS nbs (
    cnpj TEXT, fornecedor TEXT, nf INTEGER, codigo TEXT, descricao TEXT, qtde REAL,
    preco_liq REAL, custo REAL, data_entrada TEXT, data_emissao TEXT
);
CREATE TABLE IF NOT EXISTS nbs_jack (
    nf INTEGER, codigo TEXT, descricao TEXT, qtde REAL, data_entrada TEXT, data_emissao TEXT
);
CREATE TABLE IF NOT EXISTS estoque (
    codigo TEXT, retex TEXT, tipo TEXT, descricao TEXT, sigla TEXT, serial TEXT,
    qtde REAL, vab REAL, aee REAL, subst REAL, repas REAL, saida REAL, saldo REAL,
    nf INTEGER, chave TEXT, emissao TEXT, nivel TEXT, descricao_nfe TEXT,
    utilizacao TEXT, data_utilizacao TEXT, motivo TEXT, repasse TEXT, fornecedor TEXT
);
CREATE TABLE IF NOT EXISTS follow_up (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    veiculo TEXT, peca TEXT, nf TEXT, fornecedor TEXT, data TEXT, serial TEXT,
    posicao TEXT, os TEXT, obs TEXT, validacao TEXT,
    criado_por TEXT, criado_em TEXT, atualizado_por TEXT, atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS decisoes (
    chave TEXT PRIMARY KEY, situacao TEXT NOT NULL, motivo TEXT, obs TEXT,
    data TEXT, usuario TEXT, numero INTEGER, emitente TEXT, carga TEXT, saldo REAL
);
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, usuario TEXT,
    acao TEXT, referencia TEXT, detalhe TEXT
);
CREATE TABLE IF NOT EXISTS importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, arquivo TEXT, linhas INTEGER,
    quando TEXT, usuario TEXT
);
CREATE TABLE IF NOT EXISTS senhas (
    usuario TEXT PRIMARY KEY, sal TEXT NOT NULL, hash TEXT NOT NULL, alterado_em TEXT
);
CREATE TABLE IF NOT EXISTS tentativas_login (
    usuario TEXT PRIMARY KEY, falhas INTEGER NOT NULL, bloqueado_ate TEXT
);
CREATE INDEX IF NOT EXISTS ix_nbs_nf ON nbs(nf);
CREATE INDEX IF NOT EXISTS ix_fu_serial ON follow_up(serial);
"""

TABELAS_RELATORIO = {"notas": "notas_sicovab", "nbs": "nbs", "nbs_jack": "nbs_jack", "estoque": "estoque"}


def caminho_db() -> Path:
    return Path(os.environ.get("SICOVAB_DB", PASTA_DADOS / "sicovab.db"))


def agora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def url_banco() -> str | None:
    """Endereço do PostgreSQL online, se configurado. Sem ele, usa o SQLite local."""
    url = os.environ.get("DATABASE_URL") or config.segredos().get("database", {}).get("url")
    return url.strip() if url else None


def online() -> bool:
    return url_banco() is not None


@lru_cache(maxsize=4)
def _motor(url: str | None, caminho: str):
    if url:
        # driver pg8000: 100% Python (não usa DLL, então o Windows não bloqueia)
        u = make_url(re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", url))
        sslmode = u.query.get("sslmode", "require" if u.host not in ("localhost", "127.0.0.1") else "disable")
        u = u.set(drivername="postgresql+pg8000", query={})
        args = {"ssl_context": ssl.create_default_context()} if sslmode != "disable" else {}
        return create_engine(u, connect_args=args, pool_pre_ping=True, pool_recycle=300,
                             pool_size=3, max_overflow=2)
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(f"sqlite:///{caminho}", connect_args={"timeout": 30})

    @event.listens_for(eng, "connect")
    def _wal(dbapi_con, _):
        dbapi_con.execute("PRAGMA journal_mode=WAL")
    return eng


def motor():
    return _motor(url_banco(), str(caminho_db()))


def _valor(v):
    """Converte valores do pandas/numpy para tipos simples que qualquer banco aceita."""
    if v is None or v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, np.generic):
        v = v.item()
        return None if isinstance(v, float) and np.isnan(v) else v
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d %H:%M:%S") if (v.hour or v.minute or v.second) else v.strftime("%Y-%m-%d")
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat(sep=" ") if isinstance(v, dt.datetime) else v.isoformat()
    return v


def _preparar(sql: str, params, pg: bool):
    """Os comandos são escritos no estilo SQLite (? e :nome); no PostgreSQL viram %s e %(nome)s."""
    if isinstance(params, dict):
        params = {k: _valor(v) for k, v in params.items()}
        if pg:  # :nome -> %s, na ordem em que aparecem
            nomes = re.findall(r"(?<![:\w]):(\w+)", sql)
            sql = re.sub(r"(?<![:\w]):(\w+)", "%s", sql)
            params = tuple(params[n] for n in nomes)
    else:
        params = tuple(_valor(v) for v in (params or ()))
        if pg:
            sql = sql.replace("?", "%s")
    return sql, params


class Conexao:
    """Fina camada sobre a conexão: con.execute(sql, params) e con.execute(...).fetchone() como no sqlite3."""

    def __init__(self, conn):
        self.conn = conn
        self.pg = conn.dialect.name == "postgresql"

    def execute(self, sql: str, params=()):
        sql, params = _preparar(sql, params, self.pg)
        return self.conn.exec_driver_sql(sql, params) if params else self.conn.exec_driver_sql(sql)


@contextmanager
def conectar():
    with motor().begin() as conn:  # grava tudo no fim; se der erro no meio, desfaz tudo
        yield Conexao(conn)


def _schema(pg: bool) -> list[str]:
    s = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY") if pg else SCHEMA
    return [c.strip() for c in s.split(";") if c.strip()]


TABELAS_SISTEMA = ["notas_sicovab", "nbs", "nbs_jack", "estoque", "follow_up", "decisoes",
                   "historico", "importacoes", "senhas", "tentativas_login"]


def iniciar():
    """Cria as tabelas que faltarem. No banco online o app usa um usuário sem permissão de criar tabelas,
    então só tenta criar se faltar alguma (nesse caso, rode uma vez com o usuário dono do banco)."""
    with conectar() as con:
        if con.pg:
            existentes = {r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()").fetchall()}
            if set(TABELAS_SISTEMA) <= existentes:
                return
        for comando in _schema(con.pg):
            con.execute(comando)


def ler(sql: str, params=()) -> pd.DataFrame:
    with conectar() as con:
        sql, params = _preparar(sql, params, con.pg)
        return pd.read_sql_query(sql, con.conn, params=params or None)


def registrar(con, usuario, acao, referencia, detalhe=""):
    con.execute(
        "INSERT INTO historico(quando, usuario, acao, referencia, detalhe) VALUES (?,?,?,?,?)",
        (agora(), usuario, acao, referencia, detalhe),
    )


# ---------------------------------------------------------------- senhas
# A senha do config.toml vale até o usuário trocar pela tela; depois vale a do banco (guardada criptografada).
def _hash(senha: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(sal), 200_000).hex()


def _iguais(a: str, b: str) -> bool:
    # compara em bytes: assim aceita acentos e não revela pelo tempo de resposta quantas letras acertou
    return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))


def conferir_senha(usuario: str, senha: str, senha_config: str) -> bool:
    with conectar() as con:
        linha = con.execute("SELECT sal, hash FROM senhas WHERE usuario=?", (usuario,)).fetchone()
    if linha:
        return _iguais(_hash(senha, linha[0]), linha[1])
    return bool(senha_config) and _iguais(senha_config, senha)


def usa_senha_inicial(usuario: str) -> bool:
    """True enquanto o usuário ainda não trocou a senha inicial (a que está nos segredos)."""
    with conectar() as con:
        return con.execute("SELECT 1 FROM senhas WHERE usuario=?", (usuario,)).fetchone() is None


# Contra quem tenta adivinhar senha: depois de MAX_FALHAS erros seguidos, o usuário fica bloqueado alguns minutos.
MAX_FALHAS = 5
MINUTOS_BLOQUEIO = 5


def minutos_bloqueado(usuario: str) -> int:
    """Quantos minutos faltam para o usuário poder tentar de novo (0 = liberado)."""
    with conectar() as con:
        r = con.execute("SELECT bloqueado_ate FROM tentativas_login WHERE usuario=?", (usuario,)).fetchone()
    if not r or not r[0]:
        return 0
    falta = (dt.datetime.fromisoformat(r[0]) - dt.datetime.now()).total_seconds()
    return max(0, int(falta // 60) + 1) if falta > 0 else 0


def registrar_falha_login(usuario: str):
    with conectar() as con:
        r = con.execute("SELECT falhas FROM tentativas_login WHERE usuario=?", (usuario,)).fetchone()
        falhas = (r[0] if r else 0) + 1
        bloqueio = None
        if falhas >= MAX_FALHAS:
            bloqueio = (dt.datetime.now() + dt.timedelta(minutes=MINUTOS_BLOQUEIO)).strftime("%Y-%m-%d %H:%M:%S")
            falhas = 0
            registrar(con, usuario, "Login bloqueado", usuario, f"{MAX_FALHAS} senhas erradas seguidas")
        con.execute("""INSERT INTO tentativas_login(usuario, falhas, bloqueado_ate) VALUES (?,?,?)
                       ON CONFLICT(usuario) DO UPDATE SET falhas=excluded.falhas,
                       bloqueado_ate=COALESCE(excluded.bloqueado_ate, tentativas_login.bloqueado_ate)""",
                    (usuario, falhas, bloqueio))


def limpar_falhas_login(usuario: str):
    with conectar() as con:
        con.execute("DELETE FROM tentativas_login WHERE usuario=?", (usuario,))


def trocar_senha(usuario: str, nova: str):
    sal = secrets.token_hex(16)
    with conectar() as con:
        con.execute("""INSERT INTO senhas(usuario, sal, hash, alterado_em) VALUES (?,?,?,?)
                       ON CONFLICT(usuario) DO UPDATE SET sal=excluded.sal, hash=excluded.hash,
                       alterado_em=excluded.alterado_em""",
                    (usuario, sal, _hash(nova, sal), agora()))
        registrar(con, usuario, "Senha alterada", usuario)


def gravar_df(con, tabela: str, df: pd.DataFrame):
    """Grava as linhas em blocos (um INSERT com várias linhas): no banco online, uma linha por vez é muito lento."""
    if len(df):
        bloco = max(1, 30000 // max(1, len(df.columns)))  # o PostgreSQL aceita até ~32 mil valores por comando
        df.to_sql(tabela, con.conn, if_exists="append", index=False, method="multi", chunksize=min(bloco, 1000))


def _linhas_followup(linhas: pd.DataFrame, usuario: str) -> pd.DataFrame:
    df = linhas.reindex(columns=CAMPOS_FU).astype(object).map(_valor).astype(object)
    df = df.where(df.notna(), None)  # o pandas transforma vazio em NaN de novo; o banco precisa de None
    df["criado_por"], df["criado_em"] = usuario, agora()
    return df


def substituir_relatorio(tipo: str, df: pd.DataFrame, arquivo: str, usuario: str):
    """Troca todo o conteúdo de um relatório (Notas, NBS, NBS Jack ou Estoque) pelo arquivo novo."""
    tabela = TABELAS_RELATORIO[tipo]
    backup()
    with conectar() as con:
        con.execute(f"DELETE FROM {tabela}")
        gravar_df(con, tabela, df)
        con.execute(
            "INSERT INTO importacoes(tipo, arquivo, linhas, quando, usuario) VALUES (?,?,?,?,?)",
            (tipo, arquivo, len(df), agora(), usuario),
        )
        registrar(con, usuario, "Importação", tipo, f"{len(df)} linhas - {arquivo}")


def ultimas_importacoes() -> pd.DataFrame:
    return ler(
        "SELECT tipo, arquivo, linhas, quando, usuario FROM importacoes "
        "WHERE id IN (SELECT MAX(id) FROM importacoes GROUP BY tipo)"
    )


TABELAS_BACKUP = ["notas_sicovab", "nbs", "nbs_jack", "estoque", "follow_up", "decisoes", "historico", "importacoes"]


def backup_excel() -> bytes:
    """Cópia de todas as tabelas num Excel (uma aba por tabela) para guardar ou restaurar."""
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for t in TABELAS_BACKUP:
            ler(f"SELECT * FROM {t}").to_excel(xw, sheet_name=t, index=False)
    return buf.getvalue()


def backup(manter: int = 30):
    """Cópia automática do arquivo antes de cada importação (só no SQLite local).
    No banco online, o próprio serviço guarda o histórico; use também o 'Baixar backup' da tela Histórico."""
    if online():
        return
    origem = caminho_db()
    if not origem.exists():
        return
    pasta = origem.parent / "backups"
    pasta.mkdir(exist_ok=True)
    destino = pasta / f"sicovab_{dt.datetime.now():%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(origem) as src, sqlite3.connect(destino) as dst:
        src.backup(dst)
    antigos = sorted(pasta.glob("sicovab_*.db"))[:-manter]
    for a in antigos:
        a.unlink(missing_ok=True)


# ---------------------------------------------------------------- decisões sobre notas
def marcar_notas(notas: pd.DataFrame, situacao: str, motivo: str, obs: str, usuario: str):
    """notas: linhas da conferência (precisam de chave, numero, emitente, carga, saldo)."""
    with conectar() as con:
        for _, n in notas.iterrows():
            con.execute(
                """INSERT INTO decisoes(chave, situacao, motivo, obs, data, usuario, numero, emitente, carga, saldo)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(chave) DO UPDATE SET situacao=excluded.situacao, motivo=excluded.motivo,
                   obs=excluded.obs, data=excluded.data, usuario=excluded.usuario""",
                (n["chave"], situacao, motivo, obs, dt.date.today().isoformat(), usuario,
                 _int(n.get("numero")), n.get("emitente"), _txt_data(n.get("carga")), _float(n.get("saldo"))),
            )
            registrar(con, usuario, f"Nota: {situacao}", f"NF {_int(n.get('numero'))} - {n.get('emitente')}",
                      " / ".join(x for x in (motivo, obs) if x))


def desfazer_decisao(chaves, usuario: str):
    with conectar() as con:
        for c in chaves:
            r = con.execute("SELECT numero, emitente, situacao FROM decisoes WHERE chave=?", (c,)).fetchone()
            con.execute("DELETE FROM decisoes WHERE chave=?", (c,))
            if r:
                registrar(con, usuario, "Nota: desfeito", f"NF {r[0]} - {r[1]}", f"era {r[2]}")


def atualizar_obs_decisao(chave: str, obs: str, usuario: str):
    with conectar() as con:
        r = con.execute("SELECT numero, emitente FROM decisoes WHERE chave=?", (chave,)).fetchone()
        con.execute("UPDATE decisoes SET obs=? WHERE chave=?", (obs, chave))
        if r:
            registrar(con, usuario, "Nota: obs", f"NF {r[0]} - {r[1]}", obs)


# ---------------------------------------------------------------- follow up
CAMPOS_FU = ["veiculo", "peca", "nf", "fornecedor", "data", "serial", "posicao", "os", "obs", "validacao"]


def inserir_followup(linhas: pd.DataFrame, usuario: str, origem: str = "Follow UP: lançamento"):
    with conectar() as con:
        gravar_df(con, "follow_up", _linhas_followup(linhas, usuario))
        registrar(con, usuario, origem, f"{len(linhas)} peça(s)",
                  ", ".join(str(s) for s in linhas["serial"].head(10)))


def substituir_followup(linhas: pd.DataFrame, arquivo: str, usuario: str):
    """O arquivo vira a fonte: apaga o Follow UP atual e grava o do arquivo (com backup antes)."""
    backup()
    with conectar() as con:
        con.execute("DELETE FROM follow_up")
        gravar_df(con, "follow_up", _linhas_followup(linhas, usuario))
        con.execute("INSERT INTO importacoes(tipo, arquivo, linhas, quando, usuario) VALUES (?,?,?,?,?)",
                    ("followup", arquivo, len(linhas), agora(), usuario))
        registrar(con, usuario, "Importação", "followup", f"{len(linhas)} linhas (substituiu tudo) - {arquivo}")


def atualizar_followup(id_: int, campos: dict, usuario: str):
    if not campos:
        return
    invalidos = set(campos) - set(CAMPOS_FU)  # o nome da coluna entra no SQL: só aceita as colunas conhecidas
    if invalidos:
        raise ValueError(f"Campo(s) não editável(is): {', '.join(map(str, invalidos))}")
    sets = ", ".join(f"{k}=?" for k in campos)
    with conectar() as con:
        con.execute(f"UPDATE follow_up SET {sets}, atualizado_por=?, atualizado_em=? WHERE id=?",
                    (*campos.values(), usuario, agora(), id_))
        serial = con.execute("SELECT serial FROM follow_up WHERE id=?", (id_,)).fetchone()
        registrar(con, usuario, "Follow UP: edição", f"Serial {serial[0] if serial else id_}",
                  "; ".join(f"{k}={v}" for k, v in campos.items()))


def excluir_followup(ids, usuario: str):
    with conectar() as con:
        for i in ids:
            r = con.execute("SELECT serial, nf FROM follow_up WHERE id=?", (int(i),)).fetchone()
            con.execute("DELETE FROM follow_up WHERE id=?", (int(i),))
            if r:
                registrar(con, usuario, "Follow UP: exclusão", f"Serial {r[0]}", f"NF {r[1]}")


# ---------------------------------------------------------------- utilitários
def _int(v):
    try:
        return None if v is None or pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return None if v is None or pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return None


def _txt_data(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v)
