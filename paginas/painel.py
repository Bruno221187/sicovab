import altair as alt
import pandas as pd
import streamlit as st

from core import db, regras, ui

# cores dos gráficos (paleta validada para daltonismo: azul e laranja)
COR_DISP, COR_PROD, COR_NOTAS = "#2a78d6", "#eb6834", "#2a78d6"
TINTA_2, GRADE = "#52514e", "#e1e0d9"


def br(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def cartao(col, rotulo, valor, ajuda=None):
    col.metric(rotulo, valor, help=ajuda, border=True)


cfg = ui.cfg()
r = regras.resumo(cfg)
alerta = cfg["regras"]["alerta_dias"]
parado = cfg["regras"]["estoque_parado_dias"]
imp = db.ultimas_importacoes()

st.title("Painel Sicovab")
quando = ""
if not imp.empty:
    quando = f"  •  Última importação: {pd.to_datetime(imp['quando']).max():%d/%m/%Y %H:%M}"
st.caption(f"Hoje: {pd.Timestamp.today():%d/%m/%Y}  •  Prazo de aceite: {cfg['regras']['prazo_aceite_dias']} dias "
           f"após a carga{quando}")

if r["notas"].empty and r["estoque_total"] == 0:
    st.info("Ainda não há relatórios no sistema. Entre com seu usuário e use **Importar relatórios**.")
    st.stop()

# ================================================================ NOTAS
st.subheader(":material/receipt_long: Notas Sicovab", divider="blue")
ps = r["por_status"]
c = st.columns(5)
cartao(c[0], "🟢 Aceitar", br(ps["Aceitar"]), "Entraram no NBS com a quantidade certa: é só dar o aceite.")
cartao(c[1], "🟡 Parciais", br(ps["Parcial"]), "Entraram no NBS com quantidade menor que o saldo do Sicovab.")
cartao(c[2], "🔴 Não recebidas", br(ps["Não recebido"]), "Ainda não entraram no NBS.")
cartao(c[3], f"⚠️ Vencem em até {alerta} dias", br(r["vence_logo"]))
cartao(c[4], "⛔ Vencidas", br(r["vencidas"]))

if r["notas"].empty:
    st.info("Importe o relatório de Notas do Sicovab para ver esta parte.")
else:
    esq, dir_ = st.columns([3, 2], gap="medium")
    with esq.container(border=True):
        st.markdown("**Notas por fornecedor**")
        st.dataframe(r["por_fornecedor"], hide_index=True, use_container_width=True, column_config={
            "Notas": ui.col_num("Notas"),
            "Vence logo": st.column_config.NumberColumn(f"Vence ≤ {alerta}d")})
    with dir_.container(border=True):
        st.markdown("**Situação das notas**")
        sit = pd.DataFrame({"Status": [f"{regras.ICONE[s]} {s}" for s in ps.index], "Notas": ps.values})
        sit["rotulo"] = sit["Notas"].map(br)
        base = alt.Chart(sit).encode(
            y=alt.Y("Status:N", sort=list(sit["Status"]), title=None,
                    axis=alt.Axis(labelLimit=200, ticks=False, labelOverlap=False, labelFontSize=12)),
            x=alt.X("Notas:Q", title=None, axis=None),
            tooltip=[alt.Tooltip("Status:N"), alt.Tooltip("rotulo:N", title="Notas")])
        barras = base.mark_bar(color=COR_NOTAS, cornerRadiusEnd=4, height=16)
        rotulos = base.mark_text(align="left", dx=4, color=TINTA_2, fontSize=12).encode(text="rotulo:N")
        st.altair_chart((barras + rotulos).properties(height=alt.Step(28)), use_container_width=True)

# ================================================================ ESTOQUE
st.subheader(":material/inventory_2: Estoque Sicovab", divider="blue")
c = st.columns(4)
cartao(c[0], "Itens com saldo", br(r["estoque_total"]))
cartao(c[1], "🟢 Disponíveis", br(r["estoque_disp"]))
cartao(c[2], "🔵 Em produção (com O.S)", br(r["estoque_prod"]), "Peças que têm O.S lançada no Follow UP Vidros.")
cartao(c[3], f"Parados > {parado} dias", br(r["estoque_parado"]), "Disponíveis há mais tempo que o configurado.")

ef = r["estoque_fornecedor"]
if ef.empty:
    st.info("Importe o relatório de Estoque do Sicovab para ver esta parte.")
else:
    with st.container(border=True):
        st.markdown("**Peças em estoque por fornecedor**")
        longo = ef[["Fornecedor", "Disponíveis", "Em produção"]].melt(
            id_vars="Fornecedor", var_name="Situação", value_name="Peças")
        ordem = list(ef["Fornecedor"])
        y = alt.Y("Fornecedor:N", sort=ordem, title=None,
                  axis=alt.Axis(labelLimit=340, ticks=False, labelOverlap=False, labelFontSize=12))
        barras = alt.Chart(longo).mark_bar(height=16, stroke="#ffffff", strokeWidth=2).encode(
            y=y,
            x=alt.X("sum(Peças):Q", title=None, axis=alt.Axis(grid=True, gridColor=GRADE, format="d")),
            color=alt.Color("Situação:N", scale=alt.Scale(domain=["Disponíveis", "Em produção"],
                                                          range=[COR_DISP, COR_PROD]),
                            legend=alt.Legend(orient="top", title=None)),
            order=alt.Order("Situação:N", sort="ascending"),
            tooltip=[alt.Tooltip("Fornecedor:N"), alt.Tooltip("Situação:N"), alt.Tooltip("Peças:Q", format=",d")])
        totais = alt.Chart(ef.assign(rotulo=ef["Itens"].map(br))).mark_text(
            align="left", dx=4, color=TINTA_2, fontSize=12).encode(
            y=y, x="Itens:Q", text="rotulo:N",
            tooltip=[alt.Tooltip("Fornecedor:N"), alt.Tooltip("rotulo:N", title="Total")])
        st.altair_chart((barras + totais).properties(height=alt.Step(26)), use_container_width=True)

        st.dataframe(ef, hide_index=True, use_container_width=True, height=(len(ef) + 1) * 35 + 3, column_config={
            "Fornecedor": st.column_config.TextColumn("Fornecedor", width="large"),
            "Itens": st.column_config.NumberColumn("Itens", format="%d", width="small"),
            "Disponíveis": st.column_config.NumberColumn("🟢 Disponíveis", format="%d", width="small"),
            "Em produção": st.column_config.NumberColumn("🔵 Em produção", format="%d", width="small"),
            "Parados": st.column_config.NumberColumn(f"Parados > {parado}d", format="%d", width="small"),
            "Participação": st.column_config.ProgressColumn("% do estoque", format="percent", min_value=0,
                                                            max_value=1, width="small"),
            "Mais antigo (dias)": st.column_config.NumberColumn("Mais antigo (dias)", format="%d", width="small"),
        })
        ui.botao_excel(ef.assign(Participação=(ef["Participação"] * 100).round(1)).rename(
            columns={"Participação": "% do estoque"}), "Estoque por fornecedor", key="exp_estoque_forn")

# ================================================================ FOLLOW UP E IMPORTAÇÕES
st.subheader(":material/fact_check: Follow UP Vidros e importações", divider="blue")
esq, dir_ = st.columns([2, 3], gap="medium")
with esq.container(border=True):
    st.markdown("**Follow UP Vidros**")
    a, b = st.columns(2)
    a.metric("Ainda no Sicovab", br(r["fu_disp"]))
    b.metric("Já baixadas", br(r["fu_baixado"]))
    if r["fu_duplicado"]:
        st.warning(f"{r['fu_duplicado']} lançamentos com serial repetido no Follow UP.", icon=":material/warning:")
with dir_.container(border=True):
    st.markdown("**Últimas importações**")
    if imp.empty:
        st.caption("Nenhuma importação ainda.")
    else:
        nomes = {"notas": "Notas Sicovab", "nbs": "NBS", "nbs_jack": "NBS Jack", "estoque": "Estoque Sicovab",
                 "followup": "Follow UP Vidros"}
        imp["tipo"] = imp["tipo"].map(nomes).fillna(imp["tipo"])
        imp["quando"] = pd.to_datetime(imp["quando"])
        st.dataframe(imp[["tipo", "quando", "linhas", "usuario"]], hide_index=True, use_container_width=True,
                     column_config={"tipo": "Relatório",
                                    "quando": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm"),
                                    "linhas": ui.col_num("Linhas"), "usuario": "Por"})
