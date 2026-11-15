import pandas as pd
import streamlit as st

from core import db, importar as imp, ui

ui.exige_administrador()
st.title("Importar relatórios")
st.markdown(
    "**Rotina:**  \n"
    "**1.** Envie **Notas Sicovab** + **NBS** (e NBS Jack, se tiver) → vá em *Notas Sicovab* e faça os aceites.  \n"
    "**2.** Depois dos aceites, baixe e envie o **Estoque Sicovab** e o **Follow UP Vidros**.\n\n"
    "O sistema reconhece cada relatório pelas colunas, então pode mandar vários de uma vez. "
    "Cada importação **substitui** a versão anterior daquele relatório (um backup é feito antes)."
)

arquivos = st.file_uploader("Arquivos", type=["xlsx", "xlsm", "xls"], accept_multiple_files=True)
lidos = []
tem_fu = False
for arq in arquivos or []:
    try:
        tipo, df = imp.ler_arquivo(arq, tipos=["notas", "estoque", "nbs", "nbs_jack", "followup"])
        lidos.append((tipo, df, arq.name))
        st.success(f"**{arq.name}** → {imp.LAYOUTS[tipo]['nome']}: {len(df)} linhas")
        tem_fu = tem_fu or tipo == "followup"
        with st.expander("Ver primeiras linhas"):
            st.dataframe(df.head(20), hide_index=True)
    except imp.ErroImportacao as e:
        st.error(f"**{arq.name}**: {e}")

tipos = [t for t, _, _ in lidos]
if len(tipos) != len(set(tipos)):
    st.warning("Há dois arquivos do mesmo tipo. Só o último de cada tipo será importado.")

if tem_fu:
    st.warning("O Follow UP do arquivo vai **substituir** todo o Follow UP do sistema "
               "(inclusive lançamentos e edições feitos pela tela). Se quiser só acrescentar peças novas, "
               "use a aba *Importar em lote* na tela Follow UP Vidros.")

if lidos and st.button("Confirmar importação", type="primary"):
    for tipo, df, nome in {t: (t, d, n) for t, d, n in lidos}.values():
        if tipo == "followup":
            db.substituir_followup(df, nome, ui.usuario())
        else:
            db.substituir_relatorio(tipo, df, nome, ui.usuario())
    st.success("Relatórios importados. Veja o Painel.")
    st.balloons()

st.divider()
st.subheader("Últimas importações")
ult = db.ultimas_importacoes()
if ult.empty:
    st.caption("Nenhuma ainda.")
else:
    nomes = {"notas": "Notas Sicovab", "nbs": "NBS", "nbs_jack": "NBS Jack", "estoque": "Estoque Sicovab", "followup": "Follow UP Vidros"}
    ult["tipo"] = ult["tipo"].map(nomes).fillna(ult["tipo"])
    ult["quando"] = pd.to_datetime(ult["quando"])
    st.dataframe(ult, hide_index=True, column_config={
        "tipo": "Relatório", "arquivo": "Arquivo", "linhas": "Linhas",
        "quando": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm"), "usuario": "Por"})
