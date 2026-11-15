"""Controle Sicovab - SBR.  Para abrir:  streamlit run app.py  (ou dê dois cliques em iniciar.bat)"""
import streamlit as st

from core import config, db, ui

st.set_page_config(page_title="Controle Sicovab", page_icon=":material/shield:", layout="wide")
db.iniciar()
cfg = config.carregar()
SENHA_MINIMA = 8


def problema_nova_senha(usuario: str, nova: str, repetir: str) -> str | None:
    """Devolve o motivo de recusar a nova senha, ou None se ela estiver boa."""
    if len(nova) < SENHA_MINIMA:
        return f"A nova senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    if nova != repetir:
        return "As duas senhas novas não são iguais."
    if nova == str(cfg["usuarios"].get(usuario, "")):
        return "A nova senha não pode ser igual à senha inicial."
    if nova.strip().lower() == usuario.strip().lower():
        return "A senha não pode ser o seu nome de usuário."
    return None


def form_trocar_senha(usuario: str, chave: str):
    with st.form(chave, clear_on_submit=True):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input(f"Nova senha (mínimo {SENHA_MINIMA} caracteres)", type="password")
        repetir = st.text_input("Repita a nova senha", type="password")
        if st.form_submit_button("Salvar nova senha"):
            if not db.conferir_senha(usuario, atual, cfg["usuarios"].get(usuario, "")):
                st.error("Senha atual incorreta.")
            elif erro := problema_nova_senha(usuario, nova, repetir):
                st.error(erro)
            else:
                db.trocar_senha(usuario, nova)
                st.session_state.pop("trocar_senha_obrigatorio", None)
                st.success("Senha alterada.")
                st.rerun()


def achar_usuario(digitado: str) -> str | None:
    """Aceita o nome com letras maiúsculas/minúsculas diferentes e espaços sobrando."""
    alvo = digitado.strip().casefold()
    return next((n for n in cfg["usuarios"] if n.strip().casefold() == alvo), None)


with st.sidebar:
    st.markdown("### Controle Sicovab")
    usuario = st.session_state.get("usuario")
    if usuario:
        st.write(f"Conectado como **{usuario}**")
        with st.expander("Trocar minha senha", icon=":material/key:"):
            form_trocar_senha(usuario, "trocar_senha")
        if st.button("Sair", icon=":material/logout:"):
            st.session_state.clear()
            st.rerun()
    elif not cfg["usuarios"]:
        st.info("Nenhum usuário cadastrado nos segredos (.streamlit/secrets.toml).")
    else:
        with st.form("login"):
            digitado = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                nome = achar_usuario(digitado)
                bloqueio = db.minutos_bloqueado(nome) if nome else 0
                if bloqueio:
                    st.error(f"Muitas tentativas erradas. Tente de novo em {bloqueio} minuto(s).")
                elif nome and db.conferir_senha(nome, senha, cfg["usuarios"].get(nome, "")):
                    db.limpar_falhas_login(nome)
                    st.session_state["usuario"] = nome
                    if db.usa_senha_inicial(nome):
                        st.session_state["trocar_senha_obrigatorio"] = True
                    st.rerun()
                else:
                    if nome:
                        db.registrar_falha_login(nome)
                    st.error("Usuário ou senha incorretos.")
        if not cfg["acesso"].get("exigir_login"):
            st.caption("Sem entrar você pode consultar o Painel e o Estoque e exportar para Excel.")

if cfg["acesso"].get("exigir_login") and not st.session_state.get("usuario"):
    st.title("Controle Sicovab")
    st.info("Entre com seu usuário e senha na barra à esquerda.", icon=":material/lock:")
    st.stop()

if st.session_state.get("trocar_senha_obrigatorio"):
    st.title("Crie a sua senha")
    st.info("Este é o seu primeiro acesso (ou você ainda usa a senha inicial). "
            "Para continuar, troque por uma senha só sua.", icon=":material/key:")
    form_trocar_senha(st.session_state["usuario"], "trocar_senha_inicial")
    st.stop()

paginas = [
    st.Page("paginas/painel.py", title="Painel Sicovab", icon=":material/dashboard:", default=True),
    st.Page("paginas/estoque.py", title="Estoque Sicovab", icon=":material/inventory_2:"),
]
if st.session_state.get("usuario"):
    paginas += [
        st.Page("paginas/notas.py", title="Notas Sicovab", icon=":material/receipt_long:"),
        st.Page("paginas/followup.py", title="Follow UP Vidros", icon=":material/fact_check:"),
    ]
    if ui.e_administrador():
        paginas.append(st.Page("paginas/importar.py", title="Importar relatórios", icon=":material/upload_file:"))
    paginas.append(st.Page("paginas/historico.py", title="Histórico", icon=":material/history:"))
st.navigation(paginas).run()
