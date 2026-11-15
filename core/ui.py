"""Pedaços de tela reaproveitados pelas páginas."""
import datetime as dt

import streamlit as st

from . import config
from .exportar import para_excel

DATA = "DD/MM/YYYY"


def cfg() -> dict:
    return config.carregar()


def usuario() -> str | None:
    return st.session_state.get("usuario")


def exige_login():
    if not usuario():
        st.warning("Entre com seu usuário (barra lateral) para usar esta tela.")
        st.stop()
    if st.session_state.get("trocar_senha_obrigatorio"):
        st.warning("Troque a sua senha inicial antes de usar o sistema.")
        st.stop()


def e_administrador() -> bool:
    """Administradores podem substituir relatórios inteiros e baixar o backup completo.
    Se a lista [acesso] administradores estiver vazia nos segredos, todo usuário logado é administrador."""
    admins = config.carregar()["acesso"].get("administradores") or []
    return bool(usuario()) and (not admins or usuario() in admins)


def exige_administrador():
    exige_login()
    if not e_administrador():
        st.warning("Só administradores podem usar esta tela.")
        st.stop()


def botao_excel(df, nome: str, rotulo: str = "Exportar para Excel", key: str | None = None,
                vermelho: dict | None = None):
    st.download_button(
        rotulo, data=para_excel(df, nome, vermelho), key=key,
        file_name=f"{nome} {dt.date.today():%d-%m-%Y}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
    )


def col_data(rotulo: str):
    return st.column_config.DateColumn(rotulo, format=DATA)


def col_num(rotulo: str, fmt: str = "%d"):
    return st.column_config.NumberColumn(rotulo, format=fmt)
