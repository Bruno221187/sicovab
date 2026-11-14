import streamlit as st

from core import regras, ui

cfg = ui.cfg()
parado = cfg["regras"]["estoque_parado_dias"]

st.title("Estoque Sicovab")
es = regras.estoque(parado)
if es.empty:
    st.info("Importe o relatório de estoque do Sicovab em **Importar relatórios**.")
    st.stop()

f1, f2, f3, f4 = st.columns([2, 2, 3, 3])
sel_status = f1.multiselect("Status", ["Disponível", "Produção"], default=["Disponível", "Produção"])
sel_tipo = f2.multiselect("Tipo", sorted(es["tipo"].dropna().unique()))
sel_forn = f3.multiselect("Fornecedor", sorted(es["fornecedor"].dropna().unique()))
busca = f4.text_input("Buscar (serial, descrição, código, NF ou O.S)")
g1, g2 = st.columns(2)
so_parado = g1.checkbox(f"Só itens disponíveis parados há mais de {parado} dias")
so_repetida = g2.checkbox("Só Chave NF|Serial repetida 🔴")

v = es[es["status"].isin(sel_status)]
if sel_tipo:
    v = v[v["tipo"].isin(sel_tipo)]
if sel_forn:
    v = v[v["fornecedor"].isin(sel_forn)]
if busca.strip():
    b = busca.strip().upper()
    alvo = (v["serial"].fillna("") + " " + v["descricao"].fillna("") + " " + v["codigo"].fillna("") + " "
            + v["nf"].astype(str) + " " + v["os"].fillna("")).str.upper()
    v = v[alvo.str.contains(b, regex=False)]
if so_parado:
    v = v[v["parado"]]
if so_repetida:
    v = v[v["chave_repetida"]].sort_values(["chave_nf_serial"])

v = v.assign(rep=v["chave_repetida"].map({True: "🔴"}).fillna(""))
COLS = {
    "icone": st.column_config.TextColumn("", width="small"), "status": "Status", "os": "O.S",
    "rep": st.column_config.TextColumn("Rep.", width="small", help="🔴 = esta NF + Serial aparece mais de uma vez no estoque"),
    "chave_nf_serial": "Chave NF|Serial",
    "codigo": "Código", "retex": "Retex", "tipo": "Tipo", "descricao": "Descrição", "sigla": "Sigla",
    "serial": "Serial (Número)", "saldo": ui.col_num("Saldo", "%.3f"), "nf": ui.col_num("NF-e"),
    "emissao": ui.col_data("Emissão"), "dias_estoque": ui.col_num("Dias em estoque"), "nivel": "Nível",
    "fornecedor": "Fornecedor", "chave": "Chave NF-e",
}
a, b, c, d = st.columns(4)
a.metric("Itens no filtro", f"{len(v):,}".replace(",", "."))
b.metric("Disponíveis", f"{(v['status'] == 'Disponível').sum():,}".replace(",", "."))
c.metric("Em produção", int((v["status"] == "Produção").sum()))
d.metric("Chave NF|Serial repetida 🔴", int(v["chave_repetida"].sum()))

st.dataframe(v[list(COLS)], hide_index=True, column_config=COLS, height=560)
ROTULOS = {"status": "Status", "os": "O.S", "codigo": "Código", "retex": "Retex", "tipo": "Tipo",
           "descricao": "Descrição", "sigla": "Sigla", "serial": "Serial", "saldo": "Saldo", "nf": "NF-e",
           "emissao": "Emissão", "dias_estoque": "Dias em estoque", "nivel": "Nível",
           "fornecedor": "Fornecedor", "chave": "Chave NF-e", "chave_nf_serial": "Chave NF|Serial"}
COMPLETO = {"status": "Status", "os": "O.S", "codigo": "Código", "retex": "Retex", "tipo": "Tipo",
            "descricao": "Descrição", "sigla": "Sigla", "serial": "Serial", "qtde": "Qtde", "vab": "VAB",
            "aee": "AEE", "subst": "Subst", "repas": "Repas", "saida": "Saída", "saldo": "Saldo", "nf": "NF-e",
            "chave": "Chave NF-e", "emissao": "Emissão", "dias_estoque": "Dias em estoque", "nivel": "Nível",
            "descricao_nfe": "Descrição NF-e", "utilizacao": "Utilização", "data_utilizacao": "Data utilização",
            "motivo": "Motivo", "repasse": "Repasse", "fornecedor": "Fornecedor",
            "chave_nf_serial": "Chave NF|Serial"}

st.markdown("**Exportar relatório** (respeita os filtros acima)")
completo = st.toggle("Incluir todas as colunas do Sicovab (VAB, AEE, Subst, Repas, Saída, Utilização...)")
mapa = COMPLETO if completo else ROTULOS
exp = v[[c for c in mapa if c in v.columns]].rename(columns=mapa)
ui.botao_excel(exp, "Estoque Sicovab", vermelho={"Chave NF|Serial": v["chave_repetida"].to_numpy()})
