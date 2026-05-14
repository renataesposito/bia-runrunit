import io
import os
import copy
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yesh_nuclea_template.xlsx")

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

def _copy_cell_style(source_cell, target_cell):
    """Copia a formatação de uma célula para outra."""
    if source_cell.has_style:
        target_cell.font = copy.copy(source_cell.font)
        target_cell.border = copy.copy(source_cell.border)
        target_cell.fill = copy.copy(source_cell.fill)
        target_cell.number_format = copy.copy(source_cell.number_format)
        target_cell.protection = copy.copy(source_cell.protection)
        target_cell.alignment = copy.copy(source_cell.alignment)

def _find_kpi_cell(ws, label):
    """Encontra a célula que contém um texto específico na aba de KPIs."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and isinstance(cell.value, str) and label.lower() in cell.value.lower():
                return cell
    return None

def _find_table_header_row(ws, expected_headers):
    """
    Procura a linha que contém os cabeçalhos esperados.
    Retorna (row_idx, col_mapping) onde col_mapping é um dict: {nome_coluna_lower: col_idx}
    """
    expected_lower = [h.lower() for h in expected_headers]
    
    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=50), start=1):
        found_headers = {}
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                val_lower = cell.value.strip().lower()
                for exp in expected_lower:
                    if exp in val_lower or val_lower in exp:
                        found_headers[exp] = cell.column
        
        # Se encontrou pelo menos metade dos cabeçalhos esperados, consideramos que é a tabela
        if len(found_headers) >= len(expected_headers) / 2:
            return row_idx, found_headers
            
    return None, {}

def _clear_and_fill_table(ws, df, start_row, col_mapping):
    """
    Limpa as linhas de dados da tabela (preservando o template) e insere os novos dados.
    """
    # 1. Armazena o estilo da primeira linha de dados do template (logo abaixo do cabeçalho)
    reference_styles = {}
    for col_name_lower, col_idx in col_mapping.items():
        ref_cell = ws.cell(row=start_row + 1, column=col_idx)
        reference_styles[col_idx] = ref_cell
        
    # 2. Limpa os dados existentes a partir do start_row + 1
    # Deleta as linhas para não deixar lixo se a nova tabela for menor
    max_row = ws.max_row
    if max_row > start_row:
        # Remover a partir do start_row + 1. openpyxl idx base 1.
        ws.delete_rows(start_row + 1, max_row - start_row)
        
    # 3. Insere os novos dados
    for i, (_, row_data) in enumerate(df.iterrows()):
        current_row_idx = start_row + 1 + i
        # Se precisarmos inserir as linhas de fato para empurrar o resto (caso haja algo abaixo da tabela)
        # O ideal seria insert_rows se houver dados abaixo, mas vamos apenas preencher.
        # No caso de listagens geralmente elas são as últimas coisas da aba.
        for col_name_lower, col_idx in col_mapping.items():
            cell = ws.cell(row=current_row_idx, column=col_idx)
            
            val = None
            for df_col in df.columns:
                if df_col.lower() == col_name_lower or col_name_lower in df_col.lower():
                    val = row_data[df_col]
                    break
                    
            cell.value = val
            
            # Aplica estilo de referência
            if col_idx in reference_styles:
                _copy_cell_style(reference_styles[col_idx], cell)

def gerar_excel(escopo_real: pd.DataFrame, entregas: pd.DataFrame, kpis: dict) -> bytes:
    # Verifica se o arquivo de template existe. Se não existir, usa o fallback que gera do zero.
    if not os.path.exists(TEMPLATE_PATH):
        return _gerar_excel_fallback(escopo_real, entregas, kpis)
        
    wb = load_workbook(TEMPLATE_PATH)

    # --- Aba 1: Resumo KPIs ---
    ws_kpi = wb["Resumo KPIs"] if "Resumo KPIs" in wb.sheetnames else wb.active
    if ws_kpi:
        kpi_mapping = {
            "Meses decorridos": kpis.get("meses_decorridos", 0),
            "Entregas Previstas": kpis.get("total_previsto", 0),
            "Entregas Realizadas": kpis.get("total_realizado", 0),
            "% de Realização": f"{kpis.get('pct_realizacao', 0)}%"
        }
        
        for label, value in kpi_mapping.items():
            cell = _find_kpi_cell(ws_kpi, label)
            if cell:
                target_cell = ws_kpi.cell(row=cell.row, column=cell.column + 1)
                target_cell.value = value

    # --- Aba 2: Escopo x Realizado ---
    if "Escopo x Realizado" in wb.sheetnames:
        ws_esc = wb["Escopo x Realizado"]
        cols_esc = ["grupo", "entregavel", "qtd_mes", "qtd_ano", "previsto_acumulado", "realizado"]
        df_esc = escopo_real[[c for c in cols_esc if c in escopo_real.columns]].copy()
        df_esc.columns = ["Grupo", "Entregável", "Qtd/Mês", "Qtd/Ano", "Previsto Acumulado", "Realizado"][:len(df_esc.columns)]
        
        header_row_idx, col_mapping = _find_table_header_row(ws_esc, df_esc.columns.tolist())
        
        if header_row_idx:
            _clear_and_fill_table(ws_esc, df_esc, header_row_idx, col_mapping)
            _auto_width(ws_esc)

    # --- Aba 3: Histórico Entregas ---
    if "Histórico Entregas" in wb.sheetnames and not entregas.empty:
        ws_hist = wb["Histórico Entregas"]
        slug_to_name = escopo_real.set_index("slug")["entregavel"].to_dict()
        df_hist = entregas.copy()
        
        if "entregavel" not in df_hist.columns:
            df_hist.insert(4, "entregavel", df_hist["scope_slug"].map(slug_to_name).fillna(df_hist["hashtag"]))
            
        cols_hist = ["data", "mes_ano", "grupo", "projeto", "entregavel", "quantidade", "mapeado"]
        df_hist = df_hist[[c for c in cols_hist if c in df_hist.columns]]
        df_hist.columns = ["Data", "Mês/Ano", "Grupo", "Projeto", "Entregável", "Quantidade", "Mapeado"][:len(df_hist.columns)]
        
        header_row_idx, col_mapping = _find_table_header_row(ws_hist, df_hist.columns.tolist())
        
        if header_row_idx:
            _clear_and_fill_table(ws_hist, df_hist, header_row_idx, col_mapping)
            _auto_width(ws_hist)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _gerar_excel_fallback(escopo_real: pd.DataFrame, entregas: pd.DataFrame, kpis: dict) -> bytes:
    """Geração de excel do zero caso o template não exista."""
    wb = Workbook()

    # Aba 1: KPIs
    ws_kpi = wb.active
    ws_kpi.title = "Resumo KPIs"
    for row in [
        ["Indicador", "Valor"],
        ["Meses decorridos desde 01/03/2026", kpis.get("meses_decorridos", 0)],
        ["Entregas Previstas (acumulado)",     kpis.get("total_previsto", 0)],
        ["Entregas Realizadas",                kpis.get("total_realizado", 0)],
        ["% de Realização",                    str(kpis.get("pct_realizacao", 0)) + "%"],
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
        if "entregavel" not in df_hist.columns:
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
