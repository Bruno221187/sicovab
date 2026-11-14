import streamlit as st

from core import db, regras, ui

ui.exige_login()
cfg = ui.cfg()
prazo, alerta = cfg["regras"]["prazo_aceite_dias"], cfg["regras"]["alerta_dias"]
motivos = cfg["listas"]["motivos_rejeicao"]
obs_lista = cfg["listas"]["obs_nao_localizada"]

st.title("Notas Sicovab")
notas = regras.conferir_notas(prazo, alerta)

COLS = {
    "icone": st.column_config.TextColumn("", width="small"),
    "status": "Status", "numero": ui.col_num("NF", "%d"), "chave": "NF-e Chave", "fornecedor": "Fornecedor",
    "carga": ui.col_data("Carga"), "expira": ui.col_data("Expira em"),
    "dias": ui.col_num("Dias p/ vencer"), "alerta": "Alerta",
    "saldo": ui.col_num("Saldo Sicovab"), "qtd_nbs": ui.col_num("Qtd NBS"),
    "qtd_jack": ui.col_num("Qtd Jack"), "falta": ui.col_num("Falta"),
    "fornecedor_nbs": "Fornecedor no NBS", "decisao_obs": "Obs",
}

aba_conf, aba_ac, aba_nl, aba_rej = st.tabs(["Conferência", "Aceitar no Sicovab", "Não localizadas", "Rejeitadas"])

# ---------------------------------------------------------------- conferência
with aba_conf:
    if notas.empty:
        st.info("Importe o relatório de notas do Sicovab em **Importar relatórios**.")
    else:
        f1, f2, f3, f4 = st.columns([3, 3, 2, 2])
        padrao = [s for s in regras.ORDEM_STATUS if s not in regras.FINALIZADAS]
        sel_status = f1.multiselect("Status", regras.ORDEM_STATUS, default=padrao)
        sel_forn = f2.multiselect("Fornecedor", sorted(notas["fornecedor"].dropna().unique()))
        busca = f3.text_input("Buscar NF")
        so_alerta = f4.checkbox(f"Só vencendo em até {alerta} dias ou vencidas")

        v = notas[notas["status"].isin(sel_status)]
        if sel_forn:
            v = v[v["fornecedor"].isin(sel_forn)]
        if busca.strip():
            v = v[v["numero"].astype(str).str.contains(busca.strip())]
        if so_alerta:
            v = v[v["alerta"] != ""]
        v = v.reset_index(drop=True)

        st.caption(f"{len(v)} notas. Marque as linhas na primeira coluna para rejeitar ou marcar como não localizada.")
        ev = st.dataframe(v[list(COLS)], hide_index=True, column_config=COLS,
                          on_select="rerun", selection_mode="multi-row", key="tab_conf")
        selecionadas = v.iloc[ev.selection.rows] if ev and ev.selection.rows else v.iloc[0:0]

        c1, c2 = st.columns([1, 4])
        with c1:
            ui.botao_excel(v.drop(columns=["icone"]), "Notas Sicovab", key="xl_conf")
        if len(selecionadas):
            with st.form("acao_notas", clear_on_submit=True):
                st.markdown(f"**{len(selecionadas)} nota(s) selecionada(s):** "
                            + ", ".join(str(x) for x in selecionadas["numero"].head(15))
                            + (" ..." if len(selecionadas) > 15 else ""))
                acao = st.radio("Ação", ["Rejeitar", "Marcar como não localizada", "Marcar como aceita no Sicovab",
                                        "Desfazer marcação"], horizontal=True)
                a, b = st.columns(2)
                motivo = a.selectbox("Motivo da rejeição", motivos)
                obs = b.text_input("Observação (opcional)")
                if st.form_submit_button("Confirmar", type="primary"):
                    u = ui.usuario()
                    if acao == "Rejeitar":
                        db.marcar_notas(selecionadas, "Rejeitada", motivo, obs, u)
                    elif acao == "Marcar como aceita no Sicovab":
                        db.marcar_notas(selecionadas, "Aceita", "", obs, u)
                    elif acao == "Marcar como não localizada":
                        db.marcar_notas(selecionadas, "Não localizada", "", obs or obs_lista[0], u)
                    else:
                        db.desfazer_decisao(selecionadas["chave"].tolist(), u)
                    st.toast("Feito!", icon=":material/check:")
                    st.rerun()

# ---------------------------------------------------------------- aceitar no Sicovab
with aba_ac:
    pa = notas[notas["status"] == "Aceitar"].sort_values(["fornecedor", "numero"]).reset_index(drop=True)
    feitas = notas[notas["status"] == "Aceita"]
    if pa.empty:
        st.info("Nenhuma nota pronta para aceite agora."
                + (f" {len(feitas)} já marcada(s) como aceita(s) aguardando o próximo relatório." if len(feitas) else ""))
    else:
        st.markdown(f"**{len(pa)} nota(s) prontas para aceite** — o saldo do Sicovab bate com o que entrou no NBS.")
        formato = st.radio("Formato da chave para copiar", ["Como no relatório (NFe + 44 dígitos)", "Só os 44 dígitos"],
                           horizontal=True, key="fmt_chave")
        col = "chave" if formato.startswith("Como") else "chave_acesso"
        st.caption("Clique no ícone de copiar ao lado da chave, cole no Sicovab e dê o aceite. "
                   "Depois marque a nota aqui e clique em **Confirmar aceites** para tirá-la da lista.")
        with st.expander("Copiar todas de uma vez (uma chave por linha)"):
            st.code("\n".join(pa[col]), language=None)

        marcadas = []
        for i, n in pa.iterrows():
            c1, c2, c3 = st.columns([5, 4, 1], vertical_alignment="center")
            c1.code(n[col], language=None)
            c2.markdown(f"**NF {n['numero']}** · {n['fornecedor']} · {int(n['saldo'])} peça(s)")
            if c3.checkbox("Feito", key=f"ac_{n['chave']}"):
                marcadas.append(i)
        if st.button(f"Confirmar aceites ({len(marcadas)})", type="primary", disabled=not marcadas):
            db.marcar_notas(pa.loc[marcadas], "Aceita", "", "", ui.usuario())
            st.toast(f"{len(marcadas)} nota(s) marcada(s) como aceitas.", icon=":material/check:")
            st.rerun()
    if len(feitas):
        with st.expander(f"Já marcadas como aceitas ({len(feitas)}) — somem quando o próximo relatório do Sicovab for importado"):
            st.dataframe(feitas[["numero", "chave", "fornecedor", "saldo"]], hide_index=True,
                         column_config={"numero": ui.col_num("NF"), "chave": "NF-e Chave",
                                        "fornecedor": "Fornecedor", "saldo": ui.col_num("Saldo")})
            st.caption("Marcou errado? Use 'Desfazer marcação' na aba Conferência (filtre o status Aceita).")

# ---------------------------------------------------------------- não localizadas
with aba_nl:
    nl = regras.notas_nao_localizadas(notas, prazo)
    if nl.empty:
        st.info("Nenhuma nota marcada como não localizada. Marque na aba Conferência.")
    else:
        st.caption("Edite a coluna Obs e clique em Salvar. 'Recebida no NBS' = a nota já entrou e pode ser desmarcada.")
        nl = nl[["chave", "numero", "emitente", "carga", "expira", "dias", "status_hoje", "obs", "data", "usuario"]]
        nl.insert(0, "desmarcar", False)
        ed = st.data_editor(
            nl, hide_index=True, key="ed_nl",
            disabled=[c for c in nl.columns if c not in ("obs", "desmarcar")],
            column_config={
                "desmarcar": st.column_config.CheckboxColumn("Desmarcar"),
                "chave": None, "numero": ui.col_num("NF"), "emitente": "Fornecedor",
                "carga": ui.col_data("Carga"), "expira": ui.col_data("Expira em"), "dias": ui.col_num("Dias p/ vencer"),
                "status_hoje": "Situação hoje",
                "obs": st.column_config.SelectboxColumn("Obs", options=obs_lista),
                "data": ui.col_data("Marcada em"), "usuario": "Por",
            })
        c1, c2, c3 = st.columns([1, 1, 3])
        if c1.button("Salvar", type="primary", key="salvar_nl"):
            u = ui.usuario()
            for (_, antes), (_, depois) in zip(nl.iterrows(), ed.iterrows()):
                if (depois["obs"] or "") != (antes["obs"] or ""):
                    db.atualizar_obs_decisao(depois["chave"], depois["obs"] or "", u)
            desm = ed.loc[ed["desmarcar"], "chave"].tolist()
            if desm:
                db.desfazer_decisao(desm, u)
            st.toast("Salvo!", icon=":material/check:")
            st.rerun()
        with c2:
            ui.botao_excel(nl.drop(columns=["desmarcar", "chave"]), "Notas não localizadas", key="xl_nl")

# ---------------------------------------------------------------- rejeitadas
with aba_rej:
    rej = regras.notas_rejeitadas()
    if rej.empty:
        st.info("Nenhuma nota rejeitada.")
    else:
        rej = rej[["chave", "numero", "emitente", "carga", "saldo", "data", "motivo", "obs", "usuario"]]
        cfg_rej = {"chave": "Chave", "numero": ui.col_num("NF"), "emitente": "Fornecedor", "carga": ui.col_data("Carga"),
                   "saldo": ui.col_num("Saldo"), "data": ui.col_data("Rejeitada em"), "motivo": "Motivo",
                   "obs": "Obs", "usuario": "Por"}
        ev = st.dataframe(rej, hide_index=True, column_config=cfg_rej,
                          on_select="rerun", selection_mode="multi-row", key="tab_rej")
        c1, c2 = st.columns([1, 4])
        with c1:
            ui.botao_excel(rej, "Notas rejeitadas", key="xl_rej")
        if ev and ev.selection.rows:
            with c2:
                if st.button(f"Desfazer rejeição de {len(ev.selection.rows)} nota(s)"):
                    db.desfazer_decisao(rej.iloc[ev.selection.rows]["chave"].tolist(), ui.usuario())
                    st.rerun()
