# Plano de Implementação: Geração de Relatório de Status em PDF

## 1. Resumo

O objetivo é implementar uma nova funcionalidade no sistema que gere um relatório formal em PDF com base nas tarefas (tasks) do cliente "Núclea" do Runrun.it. O PDF será filtrado por um mês específico (baseado na data dos comentários/entregas) e cada página detalhará uma única task, contendo seu título, responsáveis e a lista de arquivos anexados (tanto da task quanto de seus comentários) com seus respectivos thumbnails. A interface ficará na página de Debug já existente.

## 2. Análise do Estado Atual

* O projeto é uma aplicação Flask com frontend em HTML/JS (Bootstrap).

* A integração com a API do Runrun.it é gerenciada por `api_client.py` e os dados são processados por `data_processor.py`.

* O dashboard principal e a tela de debug (`debug.html`) já existem e funcionam de forma estável.

* Atualmente, não há nenhuma biblioteca de geração de PDF instalada no backend.

* A filtragem de entregas por data já ocorre para gerar os relatórios em Excel, e os dados são mantidos em memória no `app.py`.

## 3. Mudanças Propostas

### 3.1. Dependências (requirements.txt)

* Adicionar `reportlab` e `Pillow` ao `requirements.txt`. O ReportLab será utilizado para a construção do PDF no backend de forma robusta e programática.

### 3.2. Novo Serviço: `pdf_generator.py`

* Criar um novo arquivo para concentrar a lógica de montagem do PDF.

* **Função principal**: `gerar_pdf_status(mes_ano, escopo_df, entregas_df)`

  * Identificar quais `task_id`s possuem entregas (comentários) no mês selecionado (`mes_ano`).

  * Buscar os dados completos dessas tasks e de seus comentários via `api_client.py` (ou usar os dados já armazenados em cache).

  * Extrair de cada task:

    * **Título**.

    * **Responsáveis** (lista de usuários designados - `assignments`).

    * **Anexos** (`attachments` na raiz da task e `attachments` dentro dos comentários da task).

  * **Tratamento de Imagens**: Fazer o download síncrono dos thumbnails das imagens (via `requests`) utilizando buffers em memória (`io.BytesIO`). Isso garante que o gerador "aguarde" o carregamento total de todas as imagens antes de desenhá-las no PDF, evitando espaços em branco.

  * **Montagem (Layout)**:

    * **Capa**: Nome do Cliente ("Núclea") e Data de Geração atual, com layout elegante e centralizado.

    * **Páginas das Tasks**: Para cada task identificada, adicionar uma quebra de página (`PageBreak`). Desenhar o Título (em destaque), os Responsáveis e, em seguida, uma grade/lista iterando sobre os anexos, exibindo a imagem do thumbnail ao lado do nome do arquivo.

### 3.3. Rotas no Backend (`app.py`)

* Criar a rota `GET /api/pdf-report`.

* Parâmetro esperado: `mes_ano` (ex: "2024-05" ou "05/2024", conforme formato do backend).

* A rota invocará o `pdf_generator.gerar_pdf_status`, gerará o arquivo em memória (`io.BytesIO`) e o retornará usando `send_file` com mimetype `application/pdf`.

### 3.4. Frontend (`debug.html`)

* Adicionar um novo painel/card intitulado **"Relatório de Status em PDF"**.

* Incluir um `<select>` de Mês, preenchido automaticamente pela rota existente `/api/meses-com-dados`.

* Adicionar o botão **"Gerar Relatório PDF"**.

* Ao clicar no botão, exibir um indicador de carregamento (spinner) no botão, fazer o fetch do PDF, e iniciar o download programaticamente via Blob.

## 4. Premissas e Decisões

* **Origem dos Anexos**: Como definido, os arquivos extraídos para o PDF englobarão anexos presentes tanto na Task em si quanto em todos os seus Comentários.

* **Filtro de Data**: O critério para a task entrar no relatório do mês será se ela possui comentários/entregas válidas registradas naquele mês.

* **Geração Backend**: Foi escolhido gerar o PDF no backend com Python (ReportLab) ao invés do frontend. Isso permite lidar melhor com a autenticação das imagens (se necessário) e evita lentidão/travamentos na interface de debug do cliente, gerando o arquivo remotamente de forma confiável.

* **Ambiente Remoto**: O projeto roda em um servidor Linux. O `reportlab` é compatível e não exige binários externos pesados, sendo ideal para essa arquitetura.

## 5. Passos de Validação

* Verificar se a rota `/api/pdf-report` responde corretamente com um arquivo PDF sem corrompimentos.

* Conferir visualmente se a capa apresenta o nome "Núclea" e a data correta.

* Conferir se cada página detalha estritamente 1 Task.

* Garantir que as imagens dos thumbnails foram baixadas e renderizadas sem deixar áreas em branco ou quebrar a formatação.

