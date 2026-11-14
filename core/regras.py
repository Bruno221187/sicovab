"""Regras de negócio: as mesmas da planilha v2, agora num lugar só."""
import re

import numpy as np
import pandas as pd

from . import db
from .importar import chave_nf_serial, separar_emitente

ORDEM_STATUS = ["Aceitar", "Parcial", "Divergente", "Verificar fornecedor", "Verificar NBS Jack",
                "Não localizada", "Não recebido", "Aceita", "Rejeitada"]
FINALIZADAS = ["Aceita", "Rejeitada"]  # já tratadas: não contam como pendência
ICONE = {"Aceitar": "🟢", "Parcial": "🟡", "Divergente": "🟠", "Verificar fornecedor": "🟠",
         "Verificar NBS Jack": "🟠", "Não localizada": "🟣", "Não recebido": "🔴", "Aceita": "✅", "Rejeitada": "⚫",
         "Disponível": "🟢", "Produção": "🔵", "Baixado": "⚫"}


def hoje() -> pd.Timestamp:
    return pd.Timestamp.today().normalize()


def _chave44(chave: str) -> str:
    d = re.sub(r"\D", "", chave or "")
    return d[-44:] if len(d) >= 44 else d


# ---------------------------------------------------------------- notas
COLUNAS_NOTAS = ["icone", "status", "numero", "fornecedor", "carga", "expira", "dias", "alerta", "saldo",
                 "qtd_nbs", "qtd_jack", "falta", "fornecedor_nbs", "decisao_motivo", "decisao_obs",
                 "emissao", "cnpj", "chave", "chave_acesso"]


def conferir_notas(prazo: int, alerta: int) -> pd.DataFrame:
    n = db.ler("SELECT * FROM notas_sicovab")
    if n.empty:
        return pd.DataFrame(columns=COLUNAS_NOTAS)
    nbs = db.ler("SELECT cnpj, nf, fornecedor, qtde FROM nbs")
    jack = db.ler("SELECT nf, qtde FROM nbs_jack")
    dec = db.ler("SELECT chave, situacao, motivo, obs FROM decisoes").set_index("chave")

    n["numero"] = n["numero"].astype("Int64")
    n["chave_acesso"] = n["chave"].map(_chave44)
    n["cnpj_chave"] = n["chave_acesso"].str[6:20]

    # recebido no NBS: mesmo CNPJ + mesmo número de nota, somando as quantidades
    agg = (nbs.groupby(["cnpj", "nf"], as_index=False)
              .agg(qtd_nbs=("qtde", "sum"), fornecedor_nbs=("fornecedor", "first"))
              .rename(columns={"cnpj": "cnpj_chave", "nf": "numero"}))
    agg["numero"] = agg["numero"].astype("Int64")
    n = n.merge(agg, how="left", on=["cnpj_chave", "numero"])
    outro = nbs.groupby("nf")["fornecedor"].first()
    n["forn_outro"] = n["numero"].map(outro)
    n["qtd_jack"] = n["numero"].map(jack.groupby("nf")["qtde"].sum()).fillna(0)
    n["qtd_nbs"] = n["qtd_nbs"].fillna(0)
    n["saldo"] = n["saldo"].fillna(0)
    n["falta"] = n["saldo"] - n["qtd_nbs"]

    n["decisao"] = n["chave"].map(dec["situacao"])
    n["decisao_motivo"] = n["chave"].map(dec["motivo"]).fillna("")
    n["decisao_obs"] = n["chave"].map(dec["obs"]).fillna("")

    recebido = n["qtd_nbs"] > 0
    n["status"] = np.select(
        [n["decisao"].eq("Rejeitada"), n["decisao"].eq("Aceita"),
         recebido & (n["falta"] == 0), recebido & (n["falta"] > 0), recebido,
         n["decisao"].eq("Não localizada"),
         n["forn_outro"].notna(),
         n["qtd_jack"] > 0],
        ["Rejeitada", "Aceita", "Aceitar", "Parcial", "Divergente", "Não localizada",
         "Verificar fornecedor", "Verificar NBS Jack"],
        default="Não recebido")
    n["icone"] = n["status"].map(ICONE)
    n["fornecedor_nbs"] = np.where(n["fornecedor_nbs"].notna(), n["fornecedor_nbs"],
                                   np.where(n["forn_outro"].notna(), "Outro forn.: " + n["forn_outro"].fillna(""), ""))

    n["carga"] = pd.to_datetime(n["carga"], errors="coerce")
    n["emissao"] = pd.to_datetime(n["emissao"], errors="coerce")
    n["expira"] = n["carga"] + pd.Timedelta(days=prazo)
    n["dias"] = (n["expira"] - hoje()).dt.days.astype("Float64")
    n.loc[n["status"].isin(["Aceitar"] + FINALIZADAS), "dias"] = pd.NA
    n["alerta"] = np.select([n["dias"].fillna(9999) < 0, n["dias"].fillna(9999) <= alerta],
                            ["Vencida", "Vence logo"], default="")
    n = n.rename(columns={"emitente": "fornecedor"})
    return n[COLUNAS_NOTAS].sort_values(["dias", "numero"], na_position="last").reset_index(drop=True)


def notas_rejeitadas() -> pd.DataFrame:
    d = db.ler("SELECT * FROM decisoes WHERE situacao='Rejeitada' ORDER BY data DESC")
    for c in ("data", "carga"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    return d


def notas_nao_localizadas(conferencia: pd.DataFrame, prazo: int) -> pd.DataFrame:
    d = db.ler("SELECT * FROM decisoes WHERE situacao='Não localizada' ORDER BY data DESC")
    d["carga"] = pd.to_datetime(d["carga"], errors="coerce")
    d["data"] = pd.to_datetime(d["data"], errors="coerce")
    d["expira"] = d["carga"] + pd.Timedelta(days=prazo)
    d["dias"] = (d["expira"] - hoje()).dt.days
    # se a nota já entrou no NBS, a conferência mostra (ex.: "Aceitar") e ela pode sair desta lista
    atual = conferencia.set_index("chave")["status"] if not conferencia.empty else pd.Series(dtype=str)
    recebida = conferencia.set_index("chave")["qtd_nbs"] if not conferencia.empty else pd.Series(dtype=float)
    d["status_hoje"] = np.where(d["chave"].map(recebida).fillna(0) > 0, "Recebida no NBS",
                                np.where(d["chave"].isin(atual.index), "Pendente", "Fora do relatório"))
    return d


# ---------------------------------------------------------------- estoque e follow up
def _followup_base() -> pd.DataFrame:
    fu = db.ler("SELECT * FROM follow_up ORDER BY id")
    fu["chave"] = chave_nf_serial(fu["nf"], fu["serial"]) if not fu.empty else []
    return fu


def estoque(parado_dias: int) -> pd.DataFrame:
    es = db.ler("SELECT * FROM estoque")
    if es.empty:
        return es.assign(icone=None, status=None, os=None, dias_estoque=None, chave_nf_serial=None,
                         chave_repetida=None)
    fu = _followup_base()
    es["chave_nf_serial"] = chave_nf_serial(es["nf"], es["serial"])
    # igual à planilha: a mesma NF + Serial aparecendo mais de uma vez no estoque fica em vermelho
    es["chave_repetida"] = es["chave_nf_serial"].ne("") & es["chave_nf_serial"].duplicated(keep=False)
    com_os = fu[fu["os"].fillna("") != ""].groupby("chave")["os"].first() if not fu.empty else pd.Series(dtype=str)
    es["os"] = es["chave_nf_serial"].map(com_os).fillna("")
    es["status"] = np.where(es["os"] != "", "Produção", "Disponível")
    es["icone"] = es["status"].map(ICONE)
    es["emissao"] = pd.to_datetime(es["emissao"], errors="coerce")
    es["dias_estoque"] = (hoje() - es["emissao"]).dt.days
    es["parado"] = (es["status"] == "Disponível") & (es["dias_estoque"] > parado_dias)
    es["nf"] = es["nf"].astype("Int64")
    return es


def estoque_por_fornecedor(es: pd.DataFrame) -> pd.DataFrame:
    """Peças do Estoque Sicovab por fornecedor: disponíveis, em produção, paradas e a mais antiga."""
    cols = ["Fornecedor", "Itens", "Disponíveis", "Em produção", "Parados", "Participação", "Mais antigo (dias)"]
    if es.empty:
        return pd.DataFrame(columns=cols)
    nome = es["fornecedor"].map(lambda v: separar_emitente(v)[1] or "Sem fornecedor")
    g = es.assign(nome=nome).groupby("nome")
    t = pd.DataFrame({
        "Itens": g.size(),
        "Disponíveis": g["status"].apply(lambda s: int((s == "Disponível").sum())),
        "Em produção": g["status"].apply(lambda s: int((s == "Produção").sum())),
        "Parados": g["parado"].sum().astype(int),
        "Mais antigo (dias)": g["dias_estoque"].max(),
    })
    t["Participação"] = t["Itens"] / t["Itens"].sum()
    return t.sort_values("Itens", ascending=False).reset_index(names="Fornecedor")[cols]


def followup() -> pd.DataFrame:
    fu = _followup_base()
    if fu.empty:
        return fu.assign(icone=None, status=None, duplicado=None)
    es = db.ler("SELECT nf, serial FROM estoque")
    chaves_estoque = set(chave_nf_serial(es["nf"], es["serial"])) if not es.empty else set()
    fu["status"] = np.where(fu["chave"].isin(chaves_estoque), "Disponível", "Baixado")
    fu["icone"] = fu["status"].map(ICONE)
    s = fu["serial"].fillna("").str.upper().str.strip()
    fu["duplicado"] = s.ne("") & s.duplicated(keep=False)
    for c in ("data", "validacao"):
        fu[c] = pd.to_datetime(fu[c], errors="coerce")
    return fu


def serial_no_estoque(nf: str, serial: str) -> bool:
    es = db.ler("SELECT nf, serial FROM estoque")
    if es.empty:
        return False
    alvo = chave_nf_serial([nf], [serial])[0]
    return alvo in set(chave_nf_serial(es["nf"], es["serial"]))


# ---------------------------------------------------------------- painel
def resumo(cfg: dict) -> dict:
    r = cfg["regras"]
    notas = conferir_notas(r["prazo_aceite_dias"], r["alerta_dias"])
    pend = notas[~notas["status"].isin(["Aceitar"] + FINALIZADAS)]
    por_status = notas["status"].value_counts().reindex(ORDEM_STATUS, fill_value=0)

    if notas.empty:
        por_forn = pd.DataFrame(columns=["Fornecedor", "Notas", "Aceitar", "Parcial", "Não recebido", "Vence logo"])
    else:
        g = notas.groupby("fornecedor")
        por_forn = pd.DataFrame({
            "Notas": g.size(),
            "Aceitar": g["status"].apply(lambda s: (s == "Aceitar").sum()),
            "Parcial": g["status"].apply(lambda s: (s == "Parcial").sum()),
            "Não recebido": g["status"].apply(lambda s: (s == "Não recebido").sum()),
            "Vence logo": g["alerta"].apply(lambda s: (s == "Vence logo").sum()),
        }).sort_values("Notas", ascending=False).reset_index().rename(columns={"fornecedor": "Fornecedor"})

    es = estoque(r["estoque_parado_dias"])
    fu = followup()
    return {
        "estoque_fornecedor": estoque_por_fornecedor(es),
        "notas": notas,
        "por_status": por_status,
        "por_fornecedor": por_forn,
        "vence_logo": int((pend["alerta"] == "Vence logo").sum()),
        "vencidas": int((pend["alerta"] == "Vencida").sum()),
        "estoque_total": len(es),
        "estoque_disp": int((es.get("status") == "Disponível").sum()) if len(es) else 0,
        "estoque_prod": int((es.get("status") == "Produção").sum()) if len(es) else 0,
        "estoque_parado": int(es["parado"].sum()) if len(es) else 0,
        "fu_total": len(fu),
        "fu_disp": int((fu.get("status") == "Disponível").sum()) if len(fu) else 0,
        "fu_baixado": int((fu.get("status") == "Baixado").sum()) if len(fu) else 0,
        "fu_duplicado": int(fu["duplicado"].sum()) if len(fu) else 0,
    }
