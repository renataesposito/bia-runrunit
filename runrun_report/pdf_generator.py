import os
import io
import pypdf
import requests
from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from PIL import Image as PILImage
from config import CLIENT_NAME
import api_client
import thumbnail_manager


# Template paths
_TEMPLATES_DIR = os.path.dirname(__file__)
_COVER_TEMPLATE_PATH = os.path.join(_TEMPLATES_DIR, "NucleaReport1stPage.pdf")
_PAGE2_TEMPLATE_PATH = os.path.join(_TEMPLATES_DIR, "NucleaReport2ndPage.pdf")
_PAGE3_TEMPLATE_PATH = os.path.join(_TEMPLATES_DIR, "NucleaReport3rdPage.pdf")

# Page size: same as templates
PAGE_W = 1440.0
PAGE_H = 810.0

# Margins
L_MARGIN = 40.0
R_MARGIN = 40.0
T_MARGIN = 60.0  # Adjusted for title space
B_MARGIN = 40.0


def get_image_from_path(file_path, width=2*inch, height=2*inch):
    """Lê a imagem padronizada local e retorna como RLImage para o PDF."""
    try:
        pil_img = PILImage.open(file_path)
        orig_w, orig_h = pil_img.size
        
        display_w = int(width)
        display_h = int(height)
        
        img_aspect = orig_w / orig_h
        cell_aspect = display_w / display_h

        if img_aspect > cell_aspect:
            final_display_w = display_w
            final_display_h = int(display_w / img_aspect)
        else:
            final_display_h = display_h
            final_display_w = int(display_h * img_aspect)

        return RLImage(file_path, width=final_display_w, height=final_display_h)
    except Exception as e:
        print(f"Erro ao carregar imagem local {file_path}: {e}")
        return None


def _build_cover_page(mes_ano: str):
    """
    Constrói a página de capa do relatório a partir do template NucleaReport1stPage.pdf,
    sobrepondo o texto da referência (YYYY-MM em maiúsculas) logo após o "Referência:" já presente no template.
    """
    template_pdf = pypdf.PdfReader(_COVER_TEMPLATE_PATH)
    template_page = template_pdf.pages[0]

    # Overlay PDF
    overlay_buf = io.BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(PAGE_W, PAGE_H))
    c.setFont("Helvetica-Bold", 33)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(291, 190, mes_ano.upper())
    c.showPage()
    c.save()
    overlay_buf.seek(0)

    overlay_pdf = pypdf.PdfReader(overlay_buf)
    template_page.merge_page(overlay_pdf.pages[0])
    return template_page


def _draw_entregas_table_on_template(entregas_sorted, escopo_df, styles):
    """
    Draws the entregas table onto NucleaReport2ndPage.pdf template,
    filling as much lateral space as possible with nice borders.
    """
    # Load template
    template_pdf = pypdf.PdfReader(_PAGE2_TEMPLATE_PATH)
    template_page = template_pdf.pages[0]

    # Create overlay PDF with the table
    overlay_buf = io.BytesIO()
    doc = SimpleDocTemplate(overlay_buf,
                           pagesize=(PAGE_W, PAGE_H),
                           rightMargin=R_MARGIN,
                           leftMargin=L_MARGIN,
                           topMargin=90,  # Space for title on template
                           bottomMargin=B_MARGIN)

    story = []

    # Prepare data
    table_data = [["Data", "Grupo", "Projeto", "Entregável", "Qtd"]]

    slug_to_name = {}
    if not escopo_df.empty:
        slug_to_name = escopo_df.set_index("slug")["entregavel"].to_dict()

    # Table cell style
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#333333')
    )

    for _, row in entregas_sorted.iterrows():
        entregavel = row.get("hashtag", "")
        if row.get("scope_slug"):
            entregavel = slug_to_name.get(row["scope_slug"], row["hashtag"])
        table_data.append([
            str(row.get("data", "")),
            Paragraph(str(row.get("grupo", "")), table_cell_style),
            Paragraph(str(row.get("projeto", "")), table_cell_style),
            Paragraph(str(entregavel), table_cell_style),
            str(row.get("quantidade", 0))
        ])

    # Calculate column widths: Projeto larger, Entregável much smaller
    available_width = PAGE_W - L_MARGIN - R_MARGIN
    col_widths = [
        available_width * 0.08,   # Data
        available_width * 0.15,   # Grupo
        available_width * 0.55,   # Projeto (bigger)
        available_width * 0.17,   # Entregável (much smaller, ~35% of previous)
        available_width * 0.05    # Qtd
    ]

    t_resumo = Table(table_data, colWidths=col_widths, repeatRows=1)
    styles_list = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A1A1A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            styles_list.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F4F4F4')))
        else:
            styles_list.append(('BACKGROUND', (0, i), (-1, i), colors.white))

    t_resumo.setStyle(TableStyle(styles_list))
    story.append(t_resumo)

    doc.build(story)
    overlay_buf.seek(0)

    overlay_pdf = pypdf.PdfReader(overlay_buf)
    template_page.merge_page(overlay_pdf.pages[0])

    return [template_page]


def _draw_task_pages_on_template(task, entrega_date, anexos, styles):
    """
    Creates task media pages using NucleaReport3rdPage.pdf as base:
    - Adds task title higher up, in light gray
    - Adds entrega date below/next to "Entregue em:", also light gray
    - Adds "Arquivos Anexados (Aprovados):" section and media grid
    """
    pages = []

    # Load styles
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=colors.HexColor('#555555'),  # Light gray
        spaceAfter=15
    )
    attachment_name_style = ParagraphStyle(
        'AttachmentName',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER
    )

    # Split media into chunks (3 cols x 3 rows per page = 9 items per page)
    GRID_COLS = 3
    GRID_ROWS = 3
    PAGE_SIZE = GRID_COLS * GRID_ROWS

    cell_width = (PAGE_W - L_MARGIN - R_MARGIN) / GRID_COLS
    cell_height = 1.9 * inch # Adjusted to fit 3 rows nicely

    # Style for wrapped title
    title_style = ParagraphStyle(
        'TaskTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        textColor=colors.HexColor('#666666'),
        leading=28,
        alignment=TA_LEFT,
    )

    anexos_chunks = []
    for i in range(0, max(1, len(anexos)), PAGE_SIZE):
        anexos_chunks.append(anexos[i:i+PAGE_SIZE])

    for chunk_idx, page_anexos in enumerate(anexos_chunks):
        # Get template page
        template_page = pypdf.PdfReader(_PAGE3_TEMPLATE_PATH).pages[0]

        # Create overlay
        overlay_buf = io.BytesIO()
        c = canvas.Canvas(overlay_buf, pagesize=(PAGE_W, PAGE_H))

        # Title and Headers on EVERY page for alignment
        # Task title: with wrapping and safety margin
        title_text = task.get("title", f"Task #{task['id']}")
        p_title = Paragraph(title_text, title_style)
        
        # 10% safety margin on the right
        avail_width = PAGE_W - L_MARGIN - (PAGE_W * 0.10)
        tw, th = p_title.wrap(avail_width, 100)
        
        # If wrapped (th > 30), raise the first line. 
        # Base y for title is 740 (baseline of a single line).
        title_y_base = 740
        if th > 30:
            p_title.drawOn(c, L_MARGIN, title_y_base - 10) # Draw wrapped (2 lines)
        else:
            # For 1 line, th is ~28. Using title_y_base - 10 puts it at y=730 (was y=712)
            p_title.drawOn(c, L_MARGIN, title_y_base - 10)

        # Date: RIGHT AFTER "Entregue em:"
        c.setFont("Helvetica", 24)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(L_MARGIN + 146, 697, entrega_date)

        # "Arquivos Anexados (Aprovados):"
        c.setFont("Helvetica-Bold", 14)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.drawString(L_MARGIN, 600, "Arquivos Anexados (Aprovados):")

        # Draw grid - Always starts at the same Y for alignment
        current_y = 580 
        current_x = L_MARGIN

        for idx, anexo in enumerate(page_anexos):
            # Draw cell border (light gray)
            c.setStrokeColor(colors.HexColor('#DDDDDD'))
            c.setLineWidth(0.5)
            c.rect(current_x, current_y - cell_height, cell_width, cell_height, stroke=1, fill=0)

            # File name
            file_name = (anexo.get("name") or anexo.get("file_name") or anexo.get("data_file_name") or "Arquivo sem nome")
            file_name_short = (file_name[:67] + "..." + file_name[-3:]) if len(file_name) > 73 else file_name

            # Image
            thumb_path = None
            if "id" in anexo and "file_extension" in anexo:
                ext = str(anexo.get("file_extension", "")).lower()
                anexo_id = anexo["id"]
                url = f"https://runrun.it/api/v1.0/documents/{anexo_id}/download"
                thumb_path = thumbnail_manager.get_or_create_thumbnail(anexo_id, url, ext)

            img = None
            if thumb_path:
                img = get_image_from_path(thumb_path,
                                         width=cell_width - 0.3 * inch,
                                         height=cell_height - 0.8 * inch)

            # Draw image centered
            if img:
                # Calculate position to center image
                img_w = img.drawWidth
                img_h = img.drawHeight
                img_x = current_x + (cell_width - img_w) / 2
                img_y = current_y - cell_height + (cell_height - img_h - 30) / 2 + 25
                img.drawOn(c, img_x, img_y)

                # Draw file name below image
                c.setFont("Helvetica", 10)
                c.setFillColorRGB(0.2, 0.2, 0.2)
                c.drawCentredString(current_x + cell_width / 2, img_y - 10, file_name_short)
            else:
                # Draw placeholder if no image
                c.setFont("Helvetica", 10)
                c.setFillColorRGB(0.6, 0.6, 0.6)
                c.drawCentredString(current_x + cell_width / 2, current_y - cell_height / 2, f"📄 {file_name_short}")

            # Move to next cell
            if (idx + 1) % GRID_COLS == 0:
                current_x = L_MARGIN
                current_y -= cell_height
            else:
                current_x += cell_width

        c.showPage()
        c.save()
        overlay_buf.seek(0)

        overlay_pdf = pypdf.PdfReader(overlay_buf)
        template_page.merge_page(overlay_pdf.pages[0])
        pages.append(template_page)

    return pages


def gerar_pdf_status(mes_ano, escopo_df, entregas_df):
    """
    Gera o PDF de Status iterando sobre as tasks que tiveram entregas no mês selecionado.
    """
    # 1. Filter entregas
    if entregas_df.empty:
        raise ValueError("Não há dados de entregas carregados.")

    entregas_mes = entregas_df[(entregas_df["mes_ano"] == mes_ano) & (entregas_df["mapeado"] == True)]
    if entregas_mes.empty:
        raise ValueError(f"Nenhuma entrega MAPEADA encontrada para o mês {mes_ano}.")

    task_ids_validas = entregas_mes["task_id"].dropna().unique().tolist()
    task_ids_validas = [int(tid) for tid in task_ids_validas]

    # 2. Fetch tasks
    client_id = api_client.get_client_id(CLIENT_NAME)
    if not client_id:
        raise ValueError(f"Cliente '{CLIENT_NAME}' não encontrado.")
    gestao_tasks = api_client.get_gestao_tasks(client_id)
    tasks_alvo = [t for t in gestao_tasks if t["id"] in task_ids_validas]
    if not tasks_alvo:
        raise ValueError(f"Nenhuma tarefa de gestão corresponde às entregas do mês {mes_ano}.")

    # 3. Fetch attachments from DB
    import database
    import re
    todos_anexos_aprovados = database.load_all_anexos()

    # Create task_mes_ano_dict with the latest mes_ano for each mapped task
    latest_entregas = entregas_df[entregas_df["mapeado"] == True].sort_values(by="data", ascending=False).drop_duplicates(subset=["task_id"])
    task_mes_ano_dict = dict(zip(latest_entregas["task_id"], latest_entregas["mes_ano"]))
    
    # Precompute task dates to be used both in normal flow and correcoes
    task_dates_dict = {}
    for _, row in latest_entregas.iterrows():
        task_dates_dict[row["task_id"]] = str(row["data"])

    def get_file_competence_yyyy_mm(anexo, task_month):
        def extract_tag(tags_list):
            for t in tags_list:
                match = re.search(r'(\d{2})/(\d{4})', str(t))
                if match:
                    return f"{match.group(2)}-{match.group(1)}"
            return None

        # Procura tag MM/YYYY em tags_data
        tags_data = anexo.get("tags_data")
        if isinstance(tags_data, list):
            res = extract_tag([t.get("name", "") for t in tags_data])
            if res:
                return res

        # Fallbacks (outras chaves e nome)
        for key in ["tags", "document_tags"]:
            tags = anexo.get(key)
            if isinstance(tags, list):
                res = extract_tag(tags)
                if res:
                    return res
            elif isinstance(tags, str):
                match = re.search(r'(\d{2})/(\d{4})', tags)
                if match:
                    return f"{match.group(2)}-{match.group(1)}"
                    
        name = str(anexo.get("name") or anexo.get("file_name") or "")
        match = re.search(r'(\d{2})/(\d{4})', name)
        if match:
            return f"{match.group(2)}-{match.group(1)}"

        # Se não tiver tag, assume o mês da tarefa
        return task_month

    # Filtra e classifica os anexos que pertencem ao mês selecionado
    anexos_por_task = {}
    correcoes_por_task = {}
    
    for a in todos_anexos_aprovados:
        tid = int(a.get("task_id") or 0)
        task_month = task_mes_ano_dict.get(tid)
        
        # Ignora se a tarefa não possui entregas mapeadas
        if not task_month:
            continue
            
        file_month = get_file_competence_yyyy_mm(a, task_month)
        
        # Só incluímos no relatório se a competência do arquivo bater com o mês selecionado
        if file_month == mes_ano:
            is_correcao = (task_month != mes_ano)
            
            if is_correcao:
                if tid not in correcoes_por_task:
                    correcoes_por_task[tid] = []
                correcoes_por_task[tid].append(a)
            else:
                if tid not in anexos_por_task:
                    anexos_por_task[tid] = []
                anexos_por_task[tid].append(a)

    # 4. Prepare styles
    styles = getSampleStyleSheet()

    # 5. Build the PDF
    writer = pypdf.PdfWriter()

    # Add cover page
    writer.add_page(_build_cover_page(mes_ano))

    # Add page 2 (entregas table)
    entregas_sorted = entregas_mes.sort_values(by="data", ascending=False)
    page2_pages = _draw_entregas_table_on_template(entregas_sorted, escopo_df, styles)
    for page in page2_pages:
        writer.add_page(page)

    # Add task media pages
    ordered_task_ids = entregas_sorted["task_id"].dropna().unique().tolist()
    ordered_task_ids = [int(tid) for tid in ordered_task_ids]
    task_map = {t["id"]: t for t in gestao_tasks}
    tasks_alvo_sorted = [task_map[tid] for tid in ordered_task_ids if tid in task_map]

    for task in tasks_alvo_sorted:
        entrega_date = task_dates_dict.get(task["id"], "Data não disponível")
        anexos = anexos_por_task.get(task["id"], [])

        # Se a task não tiver anexos aprovados para este mês, criamos um placeholder
        # para manter a padronização visual das páginas (página numerada do template).
        # Caso contrário, gera as páginas com grade de mídias.
        if not anexos:
            # Gera uma página do template apenas com o cabeçalho (sem grade de anexos)
            task_pages = _draw_task_pages_on_template(task, entrega_date, [], styles)
        else:
            task_pages = _draw_task_pages_on_template(task, entrega_date, anexos, styles)

        for page in task_pages:
            writer.add_page(page)

    # Add corrections (tasks from other months, but with attachments this month)
    if correcoes_por_task:
        # Use a simple page for Correções title (no template needed here)
        title_overlay_buf = io.BytesIO()
        c = canvas.Canvas(title_overlay_buf, pagesize=(PAGE_W, PAGE_H))
        c.setFont("Helvetica-Bold", 28)
        c.setFillColorRGB(0.102, 0.102, 0.102)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 200, "Correções (Casos de Mídia)")
        c.setFont("Helvetica", 14)
        c.setFillColorRGB(0.33, 0.33, 0.33)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 240, "Entregas aprovadas em momentos distintos que pertencem a este mês.")
        c.showPage()
        c.save()
        title_overlay_buf.seek(0)
        writer.add_page(pypdf.PdfReader(title_overlay_buf).pages[0])

        for tid, a_list in correcoes_por_task.items():
            task = task_map.get(tid, {"id": tid, "title": f"Task #{tid}"})
            entrega_date = task_dates_dict.get(tid, "Data não disponível")
            
            task_pages = _draw_task_pages_on_template(task, entrega_date, a_list, styles)
            for page in task_pages:
                writer.add_page(page)

    final_buffer = io.BytesIO()
    writer.write(final_buffer)
    return final_buffer.getvalue()
