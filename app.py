"""Controle Sicovab - SBR.  Para abrir:  streamlit run app.py  (ou dê dois cliques em iniciar.bat)"""
import streamlit as st

from core import config, db

st.set_page_config(page_title="Controle Sicovab", page_icon=":material/shield:", layout="wide")
db.iniciar()
cfg = config.carregar()

with st.sidebar:
    st.markdown("### Controle Sicovab")
    usuario = st.session_state.get("usuario")
    if usuario:
        st.write(f"Conectado como **{usuario}**")
        with st.expander("Trocar minha senha", icon=":material/key:"):
            with st.form("trocar_senha", clear_on_submit=True):
                atual = st.text_input("Senha atual", type="password")
                nova = st.text_input("Nova senha", type="password")
                repetir = st.text_input("Repita a nova senha", type="password")
                if st.form_submit_button("Salvar nova senha"):
                    if not db.conferir_senha(usuario, atual, cfg["usuarios"].get(usuario, "")):
                        st.error("Senha atual incorreta.")
                    elif len(nova) < 4:
                        st.error("A nova senha precisa ter pelo menos 4 caracteres.")
                    elif nova != repetir:
                        st.error("As duas senhas novas não são iguais.")
                    else:
                        db.trocar_senha(usuario, nova)
                        st.success("Senha alterada.")
        if st.button("Sair", icon=":material/logout:"):
            st.session_state.pop("usuario", None)
            st.rerun()
    else:
        nomes = list(cfg["usuarios"])
        if not nomes:
            st.info("Nenhum usuário cadastrado no config.toml.")
        else:
            with st.form("login"):
                nome = st.selectbox("Usuário", nomes)
                senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar"):
                    if db.conferir_senha(nome, senha, cfg["usuarios"].get(nome, "")):
                        st.session_state["usuario"] = nome
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")
        if not cfg["acesso"].get("exigir_login"):
            st.caption("Sem entrar você pode consultar o Painel e o Estoque e exportar para Excel.")

if cfg["acesso"].get("exigir_login") and not st.session_state.get("usuario"):
    st.title("Controle Sicovab")
    st.info("Entre com seu usuário e senha na barra à esquerda.", icon=":material/lock:")
    st.stop()

paginas = [
    st.Page("paginas/painel.py", title="Painel Sicovab", icon=":material/dashboard:", default=True),
    st.Page("paginas/estoque.py", title="Estoque Sicovab", icon=":material/inventory_2:"),
]
if st.session_state.get("usuario"):
    paginas += [
        st.Page("paginas/notas.py", title="Notas Sicovab", icon=":material/receipt_long:"),
        st.Page("paginas/followup.py", title="Follow UP Vidros", icon=":material/fact_check:"),
        st.Page("paginas/importar.py", title="Importar relatórios", icon=":material/upload_file:"),
        st.Page("paginas/historico.py", title="Histórico", icon=":material/history:"),
    ]
st.navigation(paginas).run()
