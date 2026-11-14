import pandas as pd
import streamlit as st

from core import db, ui

ui.exige_login()
st.title("Histórico")

with st.expander("Backup completo dos dados", icon=":material/backup:"):
    st.caption("Baixa todas as tabelas do sistema num Excel (uma aba por tabela). Bom guardar um por semana.")
    if st.button("Gerar backup"):
        st.download_button("Baixar backup", data=db.backup_excel(), icon=":material/download:",
                           file_name=f"Backup Controle Sicovab {pd.Timestamp.now():%d-%m-%Y %Hh%M}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

h = db.ler("SELECT quando, usuario, acao, referencia, detalhe FROM historico ORDER BY id DESC")
if h.empty:
    st.info("Nada registrado ainda.")
    st.stop()

h["quando"] = pd.to_datetime(h["quando"])
f1, f2, f3 = st.columns([2, 3, 3])
sel_u = f1.multiselect("Usuário", sorted(h["usuario"].dropna().unique()))
sel_a = f2.multiselect("Ação", sorted(h["acao"].dropna().unique()))
busca = f3.text_input("Buscar (NF, serial, fornecedor...)")
if sel_u:
    h = h[h["usuario"].isin(sel_u)]
if sel_a:
    h = h[h["acao"].isin(sel_a)]
if busca.strip():
    alvo = (h["referencia"].fillna("") + " " + h["detalhe"].fillna("")).str.upper()
    h = h[alvo.str.contains(busca.strip().upper(), regex=False)]

st.dataframe(h, hide_index=True, height=560, column_config={
    "quando": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm"),
    "usuario": "Usuário", "acao": "Ação", "referencia": "Referência", "detalhe": "Detalhe"})
ui.botao_excel(h, "Histórico")
