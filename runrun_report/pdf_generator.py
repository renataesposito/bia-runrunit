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

# Caminho do template da primeira página (capa) do relatório.
# O template já contém o layout "Referência:" + branding; apenas adicionamos
# o texto YYYY-MM logo após "Referência:" via overlay.
_COVER_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "NucleaReport1stPage.pdf")

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
    sobrepondo o texto da referência (YYYY-MM) logo após o "Referência:" já presente no template.

    O template é mantido integralmente; a única alteração é a adição do YYYY-MM usando
    Helvetica-Bold (fonte padrão do documento), 33pt, na cor branca, posicionado logo após
    o ":" do "Referência:" com a baseline alinhada.
    """
    template_pdf = pypdf.PdfReader(_COVER_TEMPLATE_PATH)
    template_page = template_pdf.pages[0]
    page_w = float(template_page.mediabox.width)
    page_h = float(template_page.mediabox.height)

    # Cria um PDF overlay com apenas o texto YYYY-MM.
    overlay_buf = io.BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(page_w, page_h))
    c.setFont("Helvetica-Bold", 33)
    c.setFillColorRGB(1, 1, 1)  # branco, mesma cor do "Referência:" no template
    # No template (1440x810 pt), o texto "Referência:" ocupa
    # x≈111.53-285.11, y≈168-212 (coordenadas PDF, origem inferior-esquerda).
    # Posicionamos o YYYY-MM logo após o ":", com pequeno gap, alinhado pela baseline.
    c.drawString(296, 174, mes_ano)
    c.showPage()
    c.save()
    overlay_buf.seek(0)

    # Mescla o overlay sobre a página do template (mantém todo o template intacto).
    overlay_pdf = pypdf.PdfReader(overlay_buf)
    template_page.merge_page(overlay_pdf.pages[0])
    return template_page

def gerar_pdf_status(mes_ano, escopo_df, entregas_df):
    """
    Gera o PDF de Status iterando sobre as tasks que tiveram entregas no mês selecionado.
    """
    # 1. Filtra as entregas pelo mes_ano selecionado E apenas as mapeadas
    if entregas_df.empty:
        raise ValueError("Não há dados de entregas carregados.")
        
    # Filtra pelo mês e exclui as entregas que não foram mapeadas
    entregas_mes = entregas_df[(entregas_df["mes_ano"] == mes_ano) & (entregas_df["mapeado"] == True)]
    
    if entregas_mes.empty:
        raise ValueError(f"Nenhuma entrega MAPEADA encontrada para o mês {mes_ano}.")

    # Pega os IDs únicos das tasks que tiveram movimento nesse mês
    task_ids_validas = entregas_mes["task_id"].dropna().unique().tolist()
    task_ids_validas = [int(tid) for tid in task_ids_validas]

    # 2. Busca o cliente e as tarefas de gestão
    client_id = api_client.get_client_id(CLIENT_NAME)
    if not client_id:
        raise ValueError(f"Cliente '{CLIENT_NAME}' não encontrado.")

    gestao_tasks = api_client.get_gestao_tasks(client_id)
    
    # Filtra as tasks
    tasks_alvo = [t for t in gestao_tasks if t["id"] in task_ids_validas]
    if not tasks_alvo:
        raise ValueError(f"Nenhuma tarefa de gestão corresponde às entregas do mês {mes_ano}.")

    # 3. Busca os comentários e anexos detalhados em lote
    task_ids_list = [t["id"] for t in tasks_alvo]
    all_comments = api_client.get_comments_batch(task_ids_list)
    # all_task_attachments não é mais necessário aqui pois usaremos os anexos do banco
    # all_task_attachments = api_client.get_task_attachments_batch(task_ids_list)

    import database
    import re
    todos_anexos_aprovados = database.load_all_anexos()
    
    def get_file_mes_ano(anexo, selected_mes_ano):
        # Procura tag MM/YYYY em tags_data
        tags_data = anexo.get("tags_data")
        if isinstance(tags_data, list):
            for t in tags_data:
                tag_name = str(t.get("name", ""))
                match = re.search(r'(\d{2}/\d{4})', tag_name)
                if match: return match.group(1)

        # Fallbacks
        for key in ["tags", "document_tags"]:
            tags = anexo.get(key)
            if isinstance(tags, list):
                for t in tags:
                    match = re.search(r'(\d{2}/\d{4})', str(t))
                    if match: return match.group(1)
            elif isinstance(tags, str):
                match = re.search(r'(\d{2}/\d{4})', tags)
                if match: return match.group(1)
        
        # Fallback to name
        name = str(anexo.get("name") or anexo.get("file_name") or "")
        match = re.search(r'(\d{2}/\d{4})', name)
        if match: return match.group(1)
        
        # Se não tiver tag, assume o mês selecionado
        return selected_mes_ano

    # Filtra anexos que pertencem ao mês selecionado
    anexos_relatorio = [a for a in todos_anexos_aprovados if get_file_mes_ano(a, mes_ano) == mes_ano]
    
    # Agrupa por task_id
    anexos_por_task = {}
    for a in anexos_relatorio:
        tid = int(a.get("task_id") or 0)
        if tid not in anexos_por_task:
            anexos_por_task[tid] = []
        anexos_por_task[tid].append(a)

    # 4. Configuração do Documento PDF (Landscape)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=40, leftMargin=40,
        topMargin=40, bottomMargin=40
    )
    
    styles = getSampleStyleSheet()
    
    # Estilos customizados
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1A1A1A'),
        alignment=TA_CENTER,
        spaceAfter=30
    )
    
    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#555555'),
        alignment=TA_CENTER,
        spaceAfter=40
    )

    task_title_style = ParagraphStyle(
        'TaskTitleStyle',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=colors.HexColor('#1A1A1A'),
        spaceAfter=15,
        spaceBefore=10
    )
    
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=colors.HexColor('#333333'),
        spaceAfter=10,
        spaceBefore=15
    )
    
    normal_style = styles['Normal']
    
    attachment_name_style = ParagraphStyle(
        'AttachmentName',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER
    )

    story = []

    # ================= CAPA =================
    # A capa (primeira página) é montada separadamente a partir do template
    # NucleaReport1stPage.pdf + overlay com o YYYY-MM (ver _build_cover_page),
    # e mesclada ao final com o conteúdo gerado abaixo.

    # ================= HISTÓRICO DE ENTREGAS (Tabela) =================
    story.append(Paragraph("<b>Histórico de Entregas (Comentários)</b>", section_style))
    story.append(Spacer(1, 10))

    from reportlab.platypus import Table, TableStyle
    table_data = [["Data", "Grupo", "Projeto", "Entregável", "Qtd"]]
    
    # Prepara os dados do dataframe para a tabela (ordenados por data decrescente)
    entregas_sorted = entregas_mes.sort_values(by="data", ascending=False)
    
    # Precisamos do dicionário para resolver o nome do escopo mapeado, se aplicável
    slug_to_name = {}
    if not escopo_df.empty:
        slug_to_name = escopo_df.set_index("slug")["entregavel"].to_dict()

    # Criação do estilo de célula com quebra de texto automática
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#333333')
    )

    for _, row in entregas_sorted.iterrows():
        entregavel = row.get("hashtag", "")
        if row.get("scope_slug"):
            entregavel = slug_to_name.get(row["scope_slug"], row["hashtag"])
            
        # Usa Paragraph nas células que podem ter textos longos para garantir o word wrap
        table_data.append([
            str(row.get("data", "")),
            Paragraph(str(row.get("grupo", "")), table_cell_style),
            Paragraph(str(row.get("projeto", "")), table_cell_style),
            Paragraph(str(entregavel), table_cell_style),
            str(row.get("quantidade", 0))
        ])

    # Larguras ajustadas sem as colunas "Mês/Ano" e "Map." (A4 landscape ~10.5 inch de área útil)
    # Aumentando proporcionalmente as outras colunas para preencher o espaço
    col_widths = [1.0*inch, 2.0*inch, 4.2*inch, 2.8*inch, 0.5*inch]
    
    t_resumo = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    styles_list = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A1A1A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'), # Coluna Qtd no centro
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            styles_list.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F4F4F4')))
        else:
            styles_list.append(('BACKGROUND', (0, i), (-1, i), colors.white))
            
    t_resumo.setStyle(TableStyle(styles_list))
    story.append(t_resumo)

    story.append(PageBreak())

    # ================= CORPO (Iteração das Tasks) =================
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
        # Título da Task
        task_title = task.get("title", f"Task #{task['id']}")
        story.append(Paragraph(task_title, task_title_style))
        
        # Data de entrega
        entrega_date = task_dates.get(task["id"], "Data não disponível")
        story.append(Paragraph(f"<b>Entregue em:</b> {entrega_date}", normal_style))
        story.append(Spacer(1, 10))
        
        # Coleta anexos da task filtrados pelo banco (já filtrados por aprovado e mes_ano)
        anexos = anexos_por_task.get(task["id"], [])
        
        story.append(Paragraph("<b>Arquivos Anexados (Aprovados):</b>", section_style))
        
        if not anexos:
            story.append(Paragraph("Nenhum arquivo anexado nesta task.", normal_style))
        else:
            # Agrupa anexos em blocos de 6 (grid 3x2)
            GRID_COLS = 3
            GRID_ROWS = 2
            PAGE_SIZE = GRID_COLS * GRID_ROWS
            
            cell_width = (doc.pagesize[0] - 80) / GRID_COLS
            cell_height = 2.2 * inch
            
            for page_start in range(0, len(anexos), PAGE_SIZE):
                page_anexos = anexos[page_start:page_start + PAGE_SIZE]
                
                table_data = []
                row = []
                for idx, anexo in enumerate(page_anexos):
                    file_name = (anexo.get("name") or anexo.get("file_name") or anexo.get("data_file_name") or "Arquivo sem nome")
                    file_name_short = (file_name[:45] + "...") if len(file_name) > 48 else file_name
                    
                    thumb_url = None
                    
                    if "id" in anexo and "file_extension" in anexo:
                        ext = str(anexo.get("file_extension", "")).lower()
                        if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
                            thumb_url = f"https://runrun.it/api/v1.0/documents/{anexo['id']}/download"
                    else:
                        thumbnails = anexo.get("thumbnails", {})
                        if isinstance(thumbnails, dict) and thumbnails:
                            thumb_url = thumbnails.get("medium") or thumbnails.get("small") or list(thumbnails.values())[0]
                    
                    if thumb_url:
                        headers = api_client._HEADERS if "runrun.it" in thumb_url else None
                        img = get_image_from_url(thumb_url, width=cell_width - 0.2*inch, height=cell_height - 0.4*inch, headers=headers)
                    else:
                        img = None
                    
                    if img:
                        cell_content = Table([[img], [Paragraph(f"<b>{file_name_short}</b>", attachment_name_style)]], colWidths=[cell_width - 0.2*inch])
                        cell_content.setStyle(TableStyle([
                            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                            ('TOPPADDING', (0,0), (-1,-1), 5),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                        ]))
                    else:
                        cell_content = Paragraph(f"📄 {file_name_short}<br/><font size='8' color='gray'>Erro ao carregar</font>", attachment_name_style)
                    
                    row.append(cell_content)
                    if len(row) == GRID_COLS:
                        table_data.append(row)
                        row = []
                
                if row:
                    while len(row) < GRID_COLS:
                        row.append(Paragraph("", normal_style))
                    table_data.append(row)
                
                col_widths = [cell_width] * GRID_COLS
                grid_table = Table(table_data, colWidths=col_widths)
                grid_table.setStyle(TableStyle([
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
                    ('TOPPADDING', (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('LEFTPADDING', (0,0), (-1,-1), 8),
                    ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ]))
                story.append(grid_table)
                if page_start + PAGE_SIZE < len(anexos):
                    story.append(PageBreak())
        
        story.append(PageBreak())

    # ================= CORREÇÕES (Tasks de outros meses com anexos deste mês) =================
    correcoes = {tid: a_list for tid, a_list in anexos_por_task.items() if tid not in ordered_task_ids}

    if correcoes:
        story.append(PageBreak())
        story.append(Paragraph("<b>Correções (Casos de Mídia)</b>", title_style))
        story.append(Paragraph("Entregas aprovadas em momentos distintos que pertencem a este mês.", subtitle_style))
        story.append(Spacer(1, 20))
        
        for tid, a_list in correcoes.items():
            # Tenta achar a task para pegar o título
            task_title = f"Task #{tid}"
            # Na API, talvez a task não esteja no `tasks_alvo`. Podemos usar apenas o ID.
            story.append(Paragraph(task_title, task_title_style))
            story.append(Spacer(1, 10))
            
            # Remove duplicados
            anexos_unicos = {a["id"]: a for a in a_list}
            anexos_cor = list(anexos_unicos.values())
            
            GRID_COLS = 3
            GRID_ROWS = 2
            PAGE_SIZE = GRID_COLS * GRID_ROWS
            cell_width = (doc.pagesize[0] - 80) / GRID_COLS
            cell_height = 2.2 * inch
            
            for page_start in range(0, len(anexos_cor), PAGE_SIZE):
                page_anexos = anexos_cor[page_start:page_start + PAGE_SIZE]
                table_data = []
                row = []
                for idx, anexo in enumerate(page_anexos):
                    file_name = (anexo.get("name") or anexo.get("file_name") or anexo.get("data_file_name") or "Arquivo sem nome")
                    file_name_short = (file_name[:45] + "...") if len(file_name) > 48 else file_name
                    
                    thumb_url = None
                    if "id" in anexo and "file_extension" in anexo:
                        ext = str(anexo.get("file_extension", "")).lower()
                        if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
                            thumb_url = f"https://runrun.it/api/v1.0/documents/{anexo['id']}/download"
                    else:
                        thumbnails = anexo.get("thumbnails", {})
                        if isinstance(thumbnails, dict) and thumbnails:
                            thumb_url = thumbnails.get("medium") or thumbnails.get("small") or list(thumbnails.values())[0]
                    
                    if thumb_url:
                        headers = api_client._HEADERS if "runrun.it" in thumb_url else None
                        img = get_image_from_url(thumb_url, width=cell_width - 0.2*inch, height=cell_height - 0.4*inch, headers=headers)
                    else:
                        img = None
                    
                    if img:
                        cell_content = [img, Spacer(1, 5), Paragraph(file_name_short, attachment_name_style)]
                    else:
                        cell_content = [Spacer(1, cell_height/2 - 0.5*inch), Paragraph(f"📄 {file_name_short}", attachment_name_style)]
                        
                    row.append(cell_content)
                    
                    if len(row) == GRID_COLS or idx == len(page_anexos) - 1:
                        while len(row) < GRID_COLS:
                            row.append([])
                        table_data.append(row)
                        row = []
                        
                grid_table = Table(table_data, colWidths=[cell_width]*GRID_COLS)
                grid_table.setStyle(TableStyle([
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('LEFTPADDING', (0,0), (-1,-1), 8),
                    ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ]))
                story.append(grid_table)
                if page_start + PAGE_SIZE < len(anexos_cor):
                    story.append(PageBreak())
            story.append(Spacer(1, 20))

    # Constrói o PDF com o conteúdo (sem a capa) e mescla com a capa (template + overlay).
    doc.build(story)
    buffer.seek(0)

    writer = pypdf.PdfWriter()
    writer.add_page(_build_cover_page(mes_ano))
    for page in pypdf.PdfReader(buffer).pages:
        writer.add_page(page)

    final_buffer = io.BytesIO()
    writer.write(final_buffer)
    return final_buffer.getvalue()
