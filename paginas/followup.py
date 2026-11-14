import datetime as dt

import pandas as pd
import streamlit as st

from core import db, importar as imp, regras, ui

ui.exige_login()
st.title("Follow UP Vidros")

aba_lanc, aba_cons, aba_lote = st.tabs(["Lançar peça", "Consultar / editar", "Importar em lote"])

# ---------------------------------------------------------------- lançar
with aba_lanc:
    with st.form("novo_fu", clear_on_submit=True):
        a, b, c = st.columns(3)
        veiculo = a.text_input("Veículo *")
        peca = b.text_input("Peça (posição do vidro, ex.: PDD) *")
        fornecedor = c.text_input("Fornecedor")
        a, b, c = st.columns(3)
        nf = a.text_input("NF *")
        serial = b.text_input("Serial *")
        data = c.date_input("Data", value=dt.date.today(), format="DD/MM/YYYY")
        a, b, c = st.columns(3)
        os_ = a.text_input("O.S")
        posicao = b.text_input("Posição")
        validacao = c.date_input("Validação", value=None, format="DD/MM/YYYY")
        obs = st.text_input("Obs")
        forcar = st.checkbox("Lançar mesmo se o serial já existir no Follow UP")
        enviar = st.form_submit_button("Lançar", type="primary")

    if enviar:
        nf_l, serial_l = imp.txt(nf), imp.txt(serial)
        if not (imp.txt(veiculo) and imp.txt(peca) and nf_l and serial_l):
            st.error("Preencha os campos com *.")
        else:
            existentes = db.ler("SELECT id, nf, veiculo, os FROM follow_up WHERE UPPER(TRIM(serial)) = ?",
                                (serial_l.upper(),))
            if len(existentes) and not forcar:
                st.error(f"O serial {serial_l} já está lançado (NF {existentes.iloc[0]['nf']}, "
                         f"{existentes.iloc[0]['veiculo']}, O.S {existentes.iloc[0]['os']}). "
                         "Marque a opção para lançar mesmo assim.")
            else:
                nova = pd.DataFrame([{
                    "veiculo": imp.txt(veiculo), "peca": imp.txt(peca), "fornecedor": imp.txt(fornecedor),
                    "nf": str(imp.inteiro(nf_l) or nf_l), "serial": serial_l, "data": imp.data(data),
                    "os": imp.txt(os_), "posicao": imp.txt(posicao), "validacao": imp.data(validacao),
                    "obs": imp.txt(obs)}])
                db.inserir_followup(nova, ui.usuario())
                if regras.serial_no_estoque(nova.iloc[0]["nf"], serial_l):
                    st.success(f"Lançado. Serial {serial_l} encontrado no Estoque Sicovab (NF {nova.iloc[0]['nf']}).")
                else:
                    st.warning(f"Lançado, mas o serial {serial_l} com NF {nova.iloc[0]['nf']} "
                               "NÃO foi encontrado no Estoque Sicovab. Confira a NF e o serial.")

# ---------------------------------------------------------------- consultar / editar
with aba_cons:
    fu = regras.followup()
    if fu.empty:
        st.info("Nenhuma peça lançada ainda.")
    else:
        f1, f2, f3 = st.columns([2, 2, 4])
        sel_status = f1.multiselect("Situação no Sicovab", ["Disponível", "Baixado"], default=["Disponível", "Baixado"])
        so_dup = f2.checkbox("Só seriais repetidos")
        busca = f3.text_input("Buscar (veículo, serial, NF, O.S)")
        v = fu[fu["status"].isin(sel_status)]
        if so_dup:
            v = v[v["duplicado"]]
        if busca.strip():
            b = busca.strip().upper()
            alvo = (v["veiculo"].fillna("") + " " + v["serial"].fillna("") + " " + v["nf"].fillna("") + " "
                    + v["os"].fillna("")).str.upper()
            v = v[alvo.str.contains(b, regex=False)]

        EDITAVEIS = ["veiculo", "peca", "nf", "fornecedor", "data", "serial", "posicao", "os", "obs", "validacao"]
        tabela = v[["id", "icone", "status"] + EDITAVEIS].copy().reset_index(drop=True)
        tabela.insert(0, "excluir", False)
        st.caption(f"{len(tabela)} peças. Edite direto na tabela e clique em Salvar alterações.")
        ed = st.data_editor(
            tabela, hide_index=True, key="ed_fu", height=520,
            disabled=["id", "icone", "status"],
            column_config={
                "excluir": st.column_config.CheckboxColumn("Excluir"), "id": None,
                "icone": st.column_config.TextColumn("", width="small"), "status": "Situação",
                "veiculo": "Veículo", "peca": "Peça", "nf": "NF", "fornecedor": "Fornecedor",
                "data": ui.col_data("Data"), "serial": "Serial", "posicao": "Posição", "os": "O.S",
                "obs": "Obs", "validacao": ui.col_data("Validação"),
            })
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("Salvar alterações", type="primary"):
            u = ui.usuario()
            alterados = 0
            for (_, antes), (_, depois) in zip(tabela.iterrows(), ed.iterrows()):
                mud = {}
                for col in EDITAVEIS:
                    va, vd = antes[col], depois[col]
                    if col in ("data", "validacao"):
                        va, vd = imp.data(va), imp.data(vd)
                    else:
                        va, vd = imp.txt(va), imp.txt(vd)
                    if va != vd:
                        mud[col] = vd
                if mud:
                    db.atualizar_followup(int(antes["id"]), mud, u)
                    alterados += 1
            excluir = ed.loc[ed["excluir"], "id"].tolist()
            if excluir:
                db.excluir_followup(excluir, u)
            st.toast(f"{alterados} alterada(s), {len(excluir)} excluída(s).", icon=":material/check:")
            st.rerun()
        with c2:
            ui.botao_excel(v.drop(columns=["icone", "chave", "duplicado"], errors="ignore"), "Follow UP Vidros")

# ---------------------------------------------------------------- lote
with aba_lote:
    st.markdown("Envie um Excel com as mesmas colunas do Follow UP: **VEÍCULO, PEÇA, NF, FORNECEDOR, DATA, "
                "SERIAL, POSIÇÃO, OS, OBS, VALIDAÇÃO**. As linhas são acrescentadas ao que já existe.")
    arq = st.file_uploader("Arquivo Excel", type=["xlsx", "xlsm", "xls"], key="up_fu")
    if arq:
        try:
            _, lote = imp.ler_arquivo(arq, tipos=["followup"])
        except imp.ErroImportacao as e:
            st.error(str(e))
            st.stop()
        existentes = set(db.ler("SELECT UPPER(TRIM(serial)) s FROM follow_up")["s"])
        lote["ja_existe"] = lote["serial"].str.upper().isin(existentes)
        st.write(f"{len(lote)} linhas lidas, {int(lote['ja_existe'].sum())} com serial já lançado.")
        st.dataframe(lote.head(50), hide_index=True)
        pular = st.checkbox("Não lançar os seriais que já existem", value=True)
        if st.button("Confirmar lançamento", type="primary"):
            novos = lote[~lote["ja_existe"]] if pular else lote
            db.inserir_followup(novos.drop(columns=["ja_existe"]), ui.usuario(), "Follow UP: importação em lote")
            st.success(f"{len(novos)} peças lançadas.")
