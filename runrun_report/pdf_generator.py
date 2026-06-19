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


def get_image_from_url(url, width=2*inch, height=2*inch, headers=None):
    """Faz download de uma imagem, calcula pixels para preencher a celula e salva em alta qualidade."""
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        img_bytes = response.content

        pil_img = PILImage.open(BytesIO(img_bytes))

        if pil_img.mode in ("RGBA", "P"):
            pil_img = pil_img.convert("RGB")

        orig_w, orig_h = pil_img.size
        display_w = int(width)
        display_h = int(height)

        target_dpi = 150

        render_by_w = int(display_w * target_dpi / 72)
        render_by_h = int(display_h * target_dpi / 72)

        ratio_w = render_by_w / orig_w
        ratio_h = render_by_h / orig_h
        ratio = max(ratio_w, ratio_h)

        new_w = int(orig_w * ratio)
        new_h = int(orig_h * ratio)

        if (new_w, new_h) != (orig_w, orig_h):
            pil_img = pil_img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)

        output = BytesIO()
        pil_img.save(output, format="JPEG", quality=92, optimize=True)
        output.seek(0)

        img_aspect = orig_w / orig_h
        cell_aspect = display_w / display_h

        if img_aspect > cell_aspect:
            final_display_w = display_w
            final_display_h = int(display_w / img_aspect)
        else:
            final_display_h = display_h
            final_display_w = int(display_h * img_aspect)

        return RLImage(output, width=final_display_w, height=final_display_h)
    except Exception as e:
        print(f"Erro ao carregar imagem {url}: {e}")
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

    # Split media into chunks (3 cols x 2 rows per page = 6 items per page)
    GRID_COLS = 3
    GRID_ROWS = 2
    PAGE_SIZE = GRID_COLS * GRID_ROWS

    cell_width = (PAGE_W - L_MARGIN - R_MARGIN) / GRID_COLS
    cell_height = 2.2 * inch

    # We'll handle the first page specially to show all the text (title, date, Arquivos Anexados)
    # Then subsequent pages just have the grid
    anexos_chunks = []
    for i in range(0, max(1, len(anexos)), PAGE_SIZE):
        anexos_chunks.append(anexos[i:i+PAGE_SIZE])

    for chunk_idx, page_anexos in enumerate(anexos_chunks):
        # Get template page
        template_page = pypdf.PdfReader(_PAGE3_TEMPLATE_PATH).pages[0]

        # Create overlay
        overlay_buf = io.BytesIO()
        c = canvas.Canvas(overlay_buf, pagesize=(PAGE_W, PAGE_H))

        # First page gets the extra text elements
        if chunk_idx == 0:
            # Task title: higher up, light gray (#666666)
            c.setFont("Helvetica-Bold", 24)
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawString(L_MARGIN, 740, task.get("title", f"Task #{task['id']}"))

            # Date: RIGHT AFTER "Entregue em:"!
            # Template "Entregue em:" ends at x≈185 (top-down), light gray, matching baseline
            # PDF y-coordinate for baseline: PAGE_H - 129 (top-down y1) ≈ 681
            c.setFont("Helvetica", 20)  # Slightly smaller to match template better
            c.drawString(L_MARGIN + 146, 683, entrega_date)

            # "Arquivos Anexados (Aprovados):"
            c.setFont("Helvetica-Bold", 14)
            c.setFillColorRGB(0.2, 0.2, 0.2)
            c.drawString(L_MARGIN, 600, "Arquivos Anexados (Aprovados):")

        # Draw grid
        if chunk_idx == 0:
            current_y = 580  # Below the section title
        else:
            current_y = PAGE_H - B_MARGIN - 50  # Start near the top for subsequent pages
        current_x = L_MARGIN

        for idx, anexo in enumerate(page_anexos):
            # Draw cell border (light gray)
            c.setStrokeColor(colors.HexColor('#DDDDDD'))
            c.setLineWidth(0.5)
            c.rect(current_x, current_y - cell_height, cell_width, cell_height, stroke=1, fill=0)

            # File name
            file_name = (anexo.get("name") or anexo.get("file_name") or anexo.get("data_file_name") or "Arquivo sem nome")
            file_name_short = (file_name[:40] + "...") if len(file_name) > 43 else file_name

            # Image
            thumb_url = None
            if "id" in anexo and "file_extension" in anexo:
                ext = str(anexo.get("file_extension", "")).lower()
                if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
                    thumb_url = f"https://runrun.it/api/v1.0/documents/{anexo['id']}/download"
            else:
                thumbnails = anexo.get("thumbnails", {})
                if isinstance(thumbnails, dict) and thumbnails:
                    thumb_url = thumbnails.get("medium") or thumbnails.get("small") or list(thumbnails.values())[0]

            img = None
            if thumb_url:
                headers = api_client._HEADERS if "runrun.it" in thumb_url else None
                img = get_image_from_url(thumb_url,
                                         width=cell_width - 0.3 * inch,
                                         height=cell_height - 0.8 * inch,
                                         headers=headers)

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

    def get_file_mes_ano(anexo, selected_mes_ano):
        tags_data = anexo.get("tags_data")
        if isinstance(tags_data, list):
            for t in tags_data:
                tag_name = str(t.get("name", ""))
                match = re.search(r'(\d{2}/\d{4})', tag_name)
                if match:
                    return match.group(1)
        for key in ["tags", "document_tags"]:
            tags = anexo.get(key)
            if isinstance(tags, list):
                for t in tags:
                    match = re.search(r'(\d{2}/\d{4})', str(t))
                    if match:
                        return match.group(1)
            elif isinstance(tags, str):
                match = re.search(r'(\d{2}/\d{4})', tags)
                if match:
                    return match.group(1)
        name = str(anexo.get("name") or anexo.get("file_name") or "")
        match = re.search(r'(\d{2}/\d{4})', name)
        if match:
            return match.group(1)
        return selected_mes_ano

    anexos_relatorio = [a for a in todos_anexos_aprovados if get_file_mes_ano(a, mes_ano) == mes_ano]
    anexos_por_task = {}
    for a in anexos_relatorio:
        tid = int(a.get("task_id") or 0)
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
    task_map = {t["id"]: t for t in tasks_alvo}
    task_dates = {}
    for tid in ordered_task_ids:
        task_rows = entregas_sorted[entregas_sorted["task_id"] == tid]
        if not task_rows.empty:
            dates = task_rows["data"].sort_values(ascending=False)
            if not dates.empty:
                task_dates[tid] = str(dates.iloc[0])
    tasks_alvo_sorted = [task_map[tid] for tid in ordered_task_ids if tid in task_map]

    for task in tasks_alvo_sorted:
        entrega_date = task_dates.get(task["id"], "Data não disponível")
        anexos = anexos_por_task.get(task["id"], [])
        task_pages = _draw_task_pages_on_template(task, entrega_date, anexos, styles)
        for page in task_pages:
            writer.add_page(page)

    # Add corrections (tasks from other months, but with attachments this month)
    correcoes = {tid: a_list for tid, a_list in anexos_por_task.items() if tid not in ordered_task_ids}

    if correcoes:
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

        for tid, a_list in correcoes.items():
            dummy_task = {"id": tid, "title": f"Task #{tid}"}
            task_pages = _draw_task_pages_on_template(dummy_task, "", a_list, styles)
            for page in task_pages:
                writer.add_page(page)

    final_buffer = io.BytesIO()
    writer.write(final_buffer)
    return final_buffer.getvalue()
