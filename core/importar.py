"""Leitura dos Excel exportados do Sicovab e do NBS.

O tipo de relatório é reconhecido pelos nomes das colunas do cabeçalho, em qualquer linha
das 20 primeiras e em qualquer aba do arquivo. A ordem das colunas não importa.
Todos os valores passam por limpeza: espaços (inclusive o invisível), zeros à esquerda
do CNPJ, números e datas gravados como texto.
"""
import datetime as dt
import math
import re
import unicodedata

import pandas as pd


class ErroImportacao(Exception):
    pass


# ---------------------------------------------------------------- conversores
def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def vazio(v) -> bool:
    if v is None or v is pd.NaT:
        return True
    try:
        return isinstance(v, float) and math.isnan(v)
    except TypeError:
        return False


def txt(v) -> str:
    if vazio(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).replace("\xa0", " ").strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    return re.sub(r"\s+", " ", s)


def num(v):
    if vazio(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = txt(v).replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def inteiro(v):
    if vazio(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    s = txt(v)
    if re.fullmatch(r"\d+([.,]0+)?", s):
        return int(re.split(r"[.,]", s)[0])
    d = re.sub(r"\D", "", s)
    return int(d) if d else None


FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                 "%d/%m/%Y %H:%M", "%d/%m/%y", "%d-%m-%Y")


def data(v):
    """Devolve a data como texto ISO (AAAA-MM-DD) ou None."""
    if vazio(v):
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < v < 80000:  # número de série do Excel
            return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v))).isoformat()
        return None
    s = txt(v)
    for f in FORMATOS_DATA:
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    return None


def cnpj(v) -> str:
    if isinstance(v, (int, float)) and not vazio(v) and not isinstance(v, bool):
        d = str(int(v))
    else:
        d = re.sub(r"\D", "", txt(v))
    return d.zfill(14) if d else ""


RE_EMITENTE = re.compile(r"^\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\s*-?\s*(.*)$")


def separar_emitente(v):
    s = txt(v)
    m = RE_EMITENTE.match(s)
    return (cnpj(m.group(1)), m.group(2).strip()) if m else ("", s)


def chave_nf_serial(nf, serial) -> pd.Series:
    """Chave usada para cruzar Estoque Sicovab x Follow UP: 'NF|SERIAL'."""
    nf_txt = pd.Series(nf).map(lambda x: "" if inteiro(x) is None else str(inteiro(x)))
    se_txt = pd.Series(serial).map(lambda x: txt(x).upper())
    return (nf_txt.values + "|" + se_txt.values)


# ---------------------------------------------------------------- layouts
LAYOUTS = {
    "notas": {
        "nome": "Notas Sicovab (NF-e recebidas)",
        "assinatura": {"NFECHAVE", "CARGA", "SALDO"},
        "obrigatorias": ["chave", "numero", "carga", "emitente", "saldo"],
        "colunas": {"chave": "NFECHAVE", "numero": "NUMERO", "emissao": "EMISSAO", "carga": "CARGA",
                    "emitente": "EMITENTE", "aceito": "ACEITO", "itens": "TITENS", "vab": "VAB",
                    "subst": "SUBST", "aee": "AEE", "repas": "REPAS", "devolvido": "DEVOLVIDO",
                    "cancelado": "CANCELADO", "saldo": "SALDO"},
    },
    "estoque": {
        "nome": "Estoque Sicovab",
        "assinatura": {"RETEX", "NUMERO", "SALDO", "CHAVE"},
        "obrigatorias": ["codigo", "serial", "nf", "saldo"],
        "colunas": {"codigo": "CODIGO", "retex": "RETEX", "tipo": "TIPO", "descricao": "DESCRICAO",
                    "sigla": "SIGLA", "serial": "NUMERO", "qtde": "QTDE", "vab": "VAB", "aee": "AEE",
                    "subst": "SUBST", "repas": "REPAS", "saida": "SAIDA", "saldo": "SALDO",
                    "nf": "NUMERONFE", "chave": "CHAVE", "emissao": "DEMISSAO", "nivel": "NIVEL",
                    "descricao_nfe": "DESCRICAONFE", "utilizacao": "UTILIZACAO",
                    "data_utilizacao": "DUTILIZACAO", "motivo": "MOTIVO", "repasse": "REPASSE",
                    "fornecedor": "FORNECEDOR"},
    },
    "nbs": {
        "nome": "NBS - Itens de entrada de estoque",
        "assinatura": {"NNOTA", "CODCLIENTE"},
        "obrigatorias": ["cnpj", "nf", "qtde"],
        "colunas": {"cnpj": "CODCLIENTE", "fornecedor": "NOME", "nf": "NNOTA", "codigo": "CODIGO",
                    "descricao": "DESCRICAO", "qtde": "QTDE", "preco_liq": "PRECOCOMPRALIQ",
                    "custo": "CUSTOCONTABIL", "data_entrada": "DATAENTRADACOMPRA",
                    "data_emissao": "DATAEMISSAOCOMPRA"},
    },
    "nbs_jack": {
        "nome": "NBS Jack",
        "assinatura": {"NNOTA", "DATAENTRADA", "QTDE"},
        "obrigatorias": ["nf", "qtde"],
        "colunas": {"nf": "NNOTA", "codigo": "CODIGO", "descricao": "DESCRICAO", "qtde": "QTDE",
                    "data_entrada": "DATAENTRADACOMPRA", "data_emissao": "DATAEMISSAOCOMPRA"},
    },
    "followup": {
        "nome": "Follow UP Vidros",
        "assinatura": {"VEICULO", "PECA", "SERIAL"},
        "obrigatorias": ["nf", "serial"],
        "colunas": {"veiculo": "VEICULO", "peca": "PECA", "nf": "NF", "fornecedor": "FORNECEDOR",
                    "data": "DATA", "serial": "SERIAL", "posicao": "POSICAO", "os": "OS",
                    "obs": "OBS", "validacao": "VALIDACAO"},
    },
}
ORDEM_DETECCAO = ["notas", "estoque", "nbs", "nbs_jack", "followup"]


def detectar(bruto: pd.DataFrame, tipos=None, max_linhas: int = 20):
    tipos = tipos or ORDEM_DETECCAO
    for i in range(min(max_linhas, len(bruto))):
        nomes = {norm(v) for v in bruto.iloc[i].tolist() if not vazio(v)}
        for t in tipos:
            if LAYOUTS[t]["assinatura"] <= nomes:
                return t, i
    return None, None


def _montar(bruto: pd.DataFrame, tipo: str, linha_cab: int) -> pd.DataFrame:
    lay = LAYOUTS[tipo]
    cab = [norm(v) if not vazio(v) else "" for v in bruto.iloc[linha_cab].tolist()]
    pos = {}
    for j, n in enumerate(cab):
        pos.setdefault(n, j)
    faltando = [c for c in lay["obrigatorias"] if lay["colunas"][c] not in pos]
    if faltando:
        raise ErroImportacao(f"{lay['nome']}: faltam as colunas {', '.join(lay['colunas'][c] for c in faltando)}")
    dados = bruto.iloc[linha_cab + 1:]
    df = pd.DataFrame({campo: (dados.iloc[:, pos[h]].tolist() if h in pos else [None] * len(dados))
                       for campo, h in lay["colunas"].items()})
    return CONVERSORES[tipo](df).reset_index(drop=True)


def _aplicar(df, textos=(), numeros=(), inteiros=(), datas=()):
    for c in textos:
        df[c] = df[c].map(txt)
    for c in numeros:
        df[c] = df[c].map(num)
    for c in inteiros:
        df[c] = df[c].map(inteiro).astype("Int64")
    for c in datas:
        df[c] = df[c].map(data)
    return df


def _conv_notas(df):
    df = _aplicar(df, textos=["chave", "aceito"], inteiros=["numero"], datas=["emissao", "carga"],
                  numeros=["itens", "vab", "subst", "aee", "repas", "devolvido", "cancelado", "saldo"])
    df = df[df["chave"].str.upper().str.startswith("NFE") | df["chave"].str.fullmatch(r"\d{44}")].copy()
    partes = df["emitente"].map(separar_emitente)
    df["cnpj"] = partes.map(lambda p: p[0])
    df["emitente"] = partes.map(lambda p: p[1])
    return df[["chave", "numero", "emissao", "carga", "cnpj", "emitente", "aceito", "itens", "vab",
               "subst", "aee", "repas", "devolvido", "cancelado", "saldo"]]


def _conv_nbs(df):
    df["cnpj"] = df["cnpj"].map(cnpj)
    df = _aplicar(df, textos=["fornecedor", "codigo", "descricao"], inteiros=["nf"],
                  numeros=["qtde", "preco_liq", "custo"], datas=["data_entrada", "data_emissao"])
    return df[df["nf"].notna()]


def _conv_jack(df):
    df = _aplicar(df, textos=["codigo", "descricao"], inteiros=["nf"], numeros=["qtde"],
                  datas=["data_entrada", "data_emissao"])
    return df[df["nf"].notna()]


def _conv_estoque(df):
    textos = ["codigo", "retex", "tipo", "descricao", "sigla", "serial", "chave", "nivel", "descricao_nfe",
              "utilizacao", "motivo", "repasse", "fornecedor"]
    df = _aplicar(df, textos=textos, inteiros=["nf"], datas=["emissao", "data_utilizacao"],
                  numeros=["qtde", "vab", "aee", "subst", "repas", "saida", "saldo"])
    return df[(df["codigo"] != "") & ~df["codigo"].str.upper().str.startswith("TOTAL")]


def _conv_followup(df):
    df = _aplicar(df, textos=["veiculo", "peca", "fornecedor", "serial", "posicao", "os", "obs"],
                  datas=["data", "validacao"])
    df["nf"] = df["nf"].map(lambda v: "" if inteiro(v) is None else str(inteiro(v)))
    df["os"] = df["os"].map(lambda v: str(inteiro(v)) if re.fullmatch(r"\d+([.,]0+)?", v or "") else v)
    return df[(df["serial"] != "") | (df["veiculo"] != "")]


CONVERSORES = {"notas": _conv_notas, "nbs": _conv_nbs, "nbs_jack": _conv_jack,
               "estoque": _conv_estoque, "followup": _conv_followup}


# ---------------------------------------------------------------- entrada principal
def ler_arquivo(arquivo, tipos=None, aba=None):
    """Lê um Excel e devolve (tipo, DataFrame limpo). Procura em todas as abas."""
    try:
        xls = arquivo if isinstance(arquivo, pd.ExcelFile) else pd.ExcelFile(arquivo)
    except Exception as e:  # arquivo corrompido, protegido, formato errado...
        raise ErroImportacao(f"Não consegui abrir o arquivo: {e}") from e
    abas = [aba] if aba else xls.sheet_names
    for nome in abas:
        bruto = pd.read_excel(xls, sheet_name=nome, header=None, dtype=object)
        if bruto.empty:
            continue
        tipo, linha = detectar(bruto, tipos)
        if tipo:
            return tipo, _montar(bruto, tipo, linha)
    esperados = ", ".join(LAYOUTS[t]["nome"] for t in (tipos or ORDEM_DETECCAO))
    raise ErroImportacao(f"Não reconheci o relatório. Esperava um destes: {esperados}.")
