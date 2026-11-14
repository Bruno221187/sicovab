"""Configurações.

- config.toml: prazos e listas (vai junto com o sistema, sem nada secreto);
- segredos (usuários, senhas iniciais e endereço do banco online):
  no computador ficam em .streamlit/secrets.toml (NÃO é publicado);
  na nuvem são colados na tela "Secrets" do Streamlit Community Cloud.
"""
import tomllib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARQUIVO = BASE / "config.toml"
ARQUIVO_SEGREDOS = BASE / ".streamlit" / "secrets.toml"

PADRAO = {
    "regras": {"prazo_aceite_dias": 14, "alerta_dias": 3, "estoque_parado_dias": 365},
    "usuarios": {},
    "acesso": {"exigir_login": False},
    "listas": {
        "motivos_rejeicao": ["Não localizado Recebimento", "Peça Devolvida"],
        "obs_nao_localizada": ["Aguardando recebimento", "Aguardando fornecedor", "Rejeitar"],
    },
}


def segredos() -> dict:
    try:
        import streamlit as st
        return st.secrets.to_dict()
    except Exception:  # fora do Streamlit (scripts) ou sem arquivo de segredos
        pass
    if ARQUIVO_SEGREDOS.exists():
        with open(ARQUIVO_SEGREDOS, "rb") as f:
            return tomllib.load(f)
    return {}


def carregar() -> dict:
    cfg = {k: dict(v) for k, v in PADRAO.items()}
    if ARQUIVO.exists():
        with open(ARQUIVO, "rb") as f:
            lido = tomllib.load(f)
        for secao, valores in lido.items():
            cfg.setdefault(secao, {}).update(valores)
    seg = segredos()
    for secao in ("usuarios", "acesso", "regras", "listas"):
        if isinstance(seg.get(secao), dict):
            cfg.setdefault(secao, {}).update(seg[secao])
    return cfg
