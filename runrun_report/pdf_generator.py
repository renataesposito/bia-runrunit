import os
import io
import requests
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch
from PIL import Image as PILImage
from config import CLIENT_NAME
import api_client

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
    all_task_attachments = api_client.get_task_attachments_batch(task_ids_list)

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
    story.append(Spacer(1, 1*inch))
    story.append(Paragraph(f"Relatório de Status", title_style))
    story.append(Paragraph(f"Cliente: {CLIENT_NAME}", subtitle_style))
    
    data_geracao = datetime.now().strftime("%d/%m/%Y às %H:%M")
    story.append(Paragraph(f"Referência: {mes_ano}", subtitle_style))
    story.append(Paragraph(f"Data de Geração: {data_geracao}", subtitle_style))
    
    story.append(PageBreak())

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
        
        # Coleta anexos da task e dos comentários
        anexos = []
        
        # Documentos/Anexos da raiz da task (usando o payload detalhado ou o da listagem como fallback)
        task_attachments = all_task_attachments.get(task["id"], [])
        if not task_attachments:
            task_attachments = task.get("attachments", [])
        anexos.extend(task_attachments)
        
        # Documentos/Anexos dos comentários
        comments = all_comments.get(task["id"], [])
        for c in comments:
            c_attachments = c.get("attachments", []) or c.get("documents", [])
            anexos.extend(c_attachments)
            
        # Remove duplicados baseados no ID do anexo
        anexos_unicos = {}
        for a in anexos:
            if "id" in a:
                anexos_unicos[a["id"]] = a
        anexos = list(anexos_unicos.values())
        
        story.append(Paragraph("<b>Arquivos Anexados:</b>", section_style))
        
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

    # Build the PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
