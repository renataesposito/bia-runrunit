import io
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

_BLUE_FILL  = PatternFill("solid", fgColor="1F3864")
_GREEN_FILL = PatternFill("solid", fgColor="198754")
_BOLD_WHITE = Font(bold=True, color="FFFFFF")


def _style_header(ws, fill=None):
    fill = fill or _BLUE_FILL
    for cell in ws[1]:
        cell.fill = fill
        cell.font = _BOLD_WHITE
        cell.alignment = Alignment(horizontal="center")


def _auto_width(ws, min_w=10, max_w=60):
    for col in ws.columns:
        values = [str(cell.value) if cell.value is not None else '' for cell in col]
        width  = min(max_w, max(min_w, max((len(v) for v in values), default=min_w) + 2))
        ws.column_dimensions[col[0].column_letter].width = width


def gerar_excel(escopo_real: pd.DataFrame, entregas: pd.DataFrame, kpis: dict) -> bytes:
    wb = Workbook()

    # Aba 1: KPIs
    ws_kpi = wb.active
    ws_kpi.title = "Resumo KPIs"
    for row in [
        ["Indicador", "Valor"],
        ["Meses decorridos desde 01/03/2026", kpis["meses_decorridos"]],
        ["Entregas Previstas (acumulado)",     kpis["total_previsto"]],
        ["Entregas Realizadas",                kpis["total_realizado"]],
        ["% de Realização",                    str(kpis["pct_realizacao"]) + "%"],
    ]:
        ws_kpi.append(row)
    _style_header(ws_kpi)
    _auto_width(ws_kpi)

    # Aba 2: Escopo x Realizado
    ws_esc = wb.create_sheet("Escopo x Realizado")
    cols_esc = ["grupo", "entregavel", "qtd_mes", "qtd_ano", "previsto_acumulado", "realizado"]
    df_esc = escopo_real[[c for c in cols_esc if c in escopo_real.columns]].copy()
    df_esc.columns = ["Grupo", "Entregável", "Qtd/Mês", "Qtd/Ano",
                      "Previsto Acumulado", "Realizado"][:len(df_esc.columns)]
    for row in dataframe_to_rows(df_esc, index=False, header=True):
        ws_esc.append(row)
    _style_header(ws_esc)
    _auto_width(ws_esc)

    # Aba 3: Histórico de Entregas
    ws_hist = wb.create_sheet("Histórico Entregas")
    if not entregas.empty:
        slug_to_name = escopo_real.set_index("slug")["entregavel"].to_dict()
        df_hist = entregas.copy()
        df_hist.insert(4, "entregavel", df_hist["scope_slug"].map(slug_to_name).fillna(df_hist["hashtag"]))
        cols_hist = ["data", "mes_ano", "grupo", "projeto", "entregavel", "quantidade", "mapeado"]
        df_hist = df_hist[[c for c in cols_hist if c in df_hist.columns]]
        df_hist.columns = ["Data", "Mês/Ano", "Grupo", "Projeto",
                           "Entregável", "Quantidade", "Mapeado"][:len(df_hist.columns)]
        for row in dataframe_to_rows(df_hist, index=False, header=True):
            ws_hist.append(row)
        _style_header(ws_hist)
        _auto_width(ws_hist)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
