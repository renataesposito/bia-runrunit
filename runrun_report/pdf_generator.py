import io
import os
import requests
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch
from config import CLIENT_NAME
import api_client

def get_image_from_url(url, width=2*inch, height=2*inch, headers=None):
    """Faz download de uma imagem a partir da URL de forma síncrona para não deixar buracos."""
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        img_data = io.BytesIO(response.content)
        # Tenta carregar a imagem com ReportLab
        return RLImage(img_data, width=width, height=height)
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
    # Ordenar as tasks alvo pela data da última entrega (mesma ordem visual da tabela)
    # 1. Pega os IDs únicos de tasks na ordem que aparecem na tabela de entregas
    ordered_task_ids = entregas_sorted["task_id"].dropna().unique().tolist()
    ordered_task_ids = [int(tid) for tid in ordered_task_ids]
    
    # 2. Cria um mapa para buscar as tasks rapidamente
    task_map = {t["id"]: t for t in tasks_alvo}
    
    # 3. Recria a lista de tasks na ordem correta
    tasks_alvo_sorted = [task_map[tid] for tid in ordered_task_ids if tid in task_map]

    for task in tasks_alvo_sorted:
        # Título da Task
        task_title = task.get("title", f"Task #{task['id']}")
        story.append(Paragraph(task_title, task_title_style))
        
        # Responsáveis
        assignments = task.get("assignments", [])
        responsaveis = []
        for a in assignments:
            assignee = a.get("assignee", {})
            name = assignee.get("name")
            if name:
                responsaveis.append(name)
        
        resp_text = ", ".join(responsaveis) if responsaveis else "Nenhum responsável designado"
        story.append(Paragraph(f"<b>Responsáveis:</b> {resp_text}", normal_style))
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
            # Para cada anexo, verifica se tem thumbnail ou imagem válida
            for anexo in anexos:
                file_name = anexo.get("name") or anexo.get("file_name") or anexo.get("data_file_name") or "Arquivo sem nome"
                
                thumb_url = None
                
                # Se for um documento do tipo UploadedDocument e tiver ID, podemos tentar baixar
                if "id" in anexo and "file_extension" in anexo:
                    ext = str(anexo.get("file_extension", "")).lower()
                    if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
                        # Endpoint direto para download do documento
                        thumb_url = f"https://runrun.it/api/v1.0/documents/{anexo['id']}/download"
                else:
                    # Legado (caso venha no formato antigo de attachments)
                    thumbnails = anexo.get("thumbnails", {})
                    if isinstance(thumbnails, dict) and thumbnails:
                        thumb_url = thumbnails.get("medium") or thumbnails.get("small") or list(thumbnails.values())[0]
                
                if thumb_url:
                    # Passa os headers de autenticação, pois o endpoint de download exige
                    headers = api_client._HEADERS if "runrun.it" in thumb_url else None
                    img = get_image_from_url(thumb_url, width=2.5*inch, height=2.5*inch, headers=headers)
                    if img:
                        # Para alinhar melhor, colocamos numa mini-tabela ou simplesmente empilhados
                        # Aqui vamos adicionar a imagem e depois o nome centralizado abaixo
                        from reportlab.platypus import Table, TableStyle
                        t = Table([[img], [Paragraph(file_name, attachment_name_style)]], colWidths=[3*inch])
                        t.setStyle(TableStyle([
                            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 15))
                    else:
                        story.append(Paragraph(f"• {file_name} (Erro ao carregar thumbnail)", normal_style))
                else:
                    story.append(Paragraph(f"• {file_name}", normal_style))
        
        story.append(PageBreak())

    # Build the PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
