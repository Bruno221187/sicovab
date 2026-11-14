"""Gera arquivos Excel formatados para download."""
import io

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def para_excel(df: pd.DataFrame, aba: str = "Dados", vermelho: dict | None = None) -> bytes:
    """vermelho = {nome da coluna: lista de True/False por linha} -> pinta essas células de vermelho."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.date
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name=aba[:31], index=False)
        ws = xw.sheets[aba[:31]]
        cab = PatternFill("solid", start_color="1F3864", end_color="1F3864")
        for cell in ws[1]:
            cell.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
            cell.fill = cab
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for i, col in enumerate(df.columns, start=1):
            amostra = [len(str(col))] + [len(str(v)) for v in df[col].head(300).tolist()]
            ws.column_dimensions[get_column_letter(i)].width = min(max(amostra) + 2, 50)
            if pd.api.types.is_object_dtype(df[col]) and df[col].map(lambda v: hasattr(v, "isoformat")).any():
                for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                    row[0].number_format = "dd/mm/yyyy"
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.font = Font(name="Arial", size=10)
        fundo = PatternFill("solid", start_color="FFC7CE", end_color="FFC7CE")
        for coluna, marcas in (vermelho or {}).items():
            if coluna not in df.columns:
                continue
            letra = get_column_letter(list(df.columns).index(coluna) + 1)
            for i, marcar in enumerate(marcas, start=2):
                if marcar:
                    ws[f"{letra}{i}"].fill = fundo
                    ws[f"{letra}{i}"].font = Font(name="Arial", size=10, color="9C0006")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    return buf.getvalue()
