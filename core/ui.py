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
