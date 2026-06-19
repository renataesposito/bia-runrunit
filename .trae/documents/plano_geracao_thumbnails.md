# Plano de Implementação: Geração Sólida de Thumbnails

## 1. Resumo

Criar um módulo dedicado para a gestão e geração de miniaturas (`thumbnail_manager.py`). O processo fará download e converterá anexos em um formato padronizado (JPEG, ajustado com faixas brancas - "Fit"), armazenando em um volume local como cache (`data/thumbnails/`). Serão suportados novos formatos (XLS/XLSX, DOC/DOCX, PPT/PPTX, PDF e MP4) utilizando ferramentas nativas instaladas no Docker (LibreOffice, FFmpeg, Poppler). Uma rotina de sincronização rodará diariamente às 2h da manhã, e a geração do PDF consumirá esse cache para garantir agilidade e consistência no layout.

## 2. Análise do Estado Atual

* **Formatos suportados:** Apenas imagens (`jpg`, `png`, `gif`, `webp`).

* **Geração:** É feita "on-the-fly" no momento da geração do relatório PDF (`pdf_generator.py`), baixando da API do RunRun.it e fazendo redimensionamento de pixels usando a biblioteca `Pillow`.

* **Problema de Layout/DPI:** A falta de padronização nas dimensões da imagem original cria dificuldades no encaixe preciso da imagem na célula de grade (grid) do relatório, muitas vezes distorcendo ou desalinhando por conta de DPIs variados.

* **Sincronismo:** Existe um agendamento (`APScheduler` em `app.py`) para os dados textuais, mas nenhum processo em background para gerenciar downloads pesados de anexos.

## 3. Mudanças Propostas

### A. Infraestrutura e Dependências (Docker & Requirements)

* **Arquivo:** `runrun_report/Dockerfile`

  * Adicionar a instalação de pacotes de sistema necessários: `libreoffice`, `poppler-utils` e `ffmpeg`.

* **Arquivo:** `runrun_report/requirements.txt`

  * Adicionar a biblioteca `pdf2image`.

### B. Novo Módulo: Gerenciador de Thumbnails

* **Arquivo:** `runrun_report/thumbnail_manager.py` (Novo)

  * Criar função `standardize_image(img, target_size=(800, 600))` que redimensiona mantendo a proporção (Fit) e preenche o fundo com branco, garantindo que toda miniatura tenha exatamente o mesmo tamanho e DPI.

  * Implementar conversores por extensão:

    * **Imagens:** Direto para `standardize_image`.

    * **PDF:** Usar `pdf2image.convert_from_path(file, first_page_only=True)`.

    * **Office (XLS, DOC, PPT):** Usar `subprocess.run` chamando `libreoffice --headless --convert-to pdf` para gerar um PDF temporário, e depois aplicar a conversão de PDF para imagem via `pdf2image`.

    * **Vídeo (MP4):** Usar `subprocess.run` chamando `ffmpeg -i video.mp4 -ss 00:00:01.000 -vframes 1` para extrair o frame do 1º segundo.

  * Criar função `get_or_create_thumbnail(anexo_id, anexo_url, extension)`:

    * Verifica se `data/thumbnails/{anexo_id}.jpg` existe. Se sim, retorna o caminho.

    * Se não, faz o download para um arquivo temporário, converte, padroniza a imagem, salva e retorna o caminho.

  * Criar função `sync_all_thumbnails()`:

    * Consulta o banco de dados para listar todos os anexos aprovados (`database.load_all_anexos()`).

    * Para cada anexo com extensão suportada, verifica se a miniatura existe.

    * Baixa e processa o que estiver faltando.

### C. Sincronização em Background

* **Arquivo:** `runrun_report/app.py`

  * Importar e adicionar um novo job no `APScheduler` para chamar `thumbnail_manager.sync_all_thumbnails()` todos os dias às 02:00 AM.

### D. Adaptação do Gerador de PDF

* **Arquivo:** `runrun_report/pdf_generator.py`

  * Substituir a lógica e função atual (`get_image_from_url`) por chamadas ao `thumbnail_manager.get_or_create_thumbnail`.

  * Simplificar o processo de renderização no grid: como todas as imagens agora terão dimensões exatas e fundo branco padronizado, basta embuti-las com a largura e altura predefinidas na célula do ReportLab, evitando cálculos matemáticos complexos para aspect ratio em tempo real.

### E. Estrutura de Diretórios

* O diretório `runrun_report/data/thumbnails/` será criado (se não existir) para armazenar os arquivos de cache.

## 4. Suposições e Decisões

* **Docker e Ferramentas:** Optamos por embutir as ferramentas no container (LibreOffice, FFmpeg, Poppler) em vez de usar API externa. Isso aumenta o tamanho da imagem, mas reduz a dependência de serviços pagos e tráfego de rede desnecessário.

* **Aspect Ratio no Grid:** Para evitar imagens esticadas ou distorcidas no grid, a decisão "Ajustar e Manter (Fit)" foi adotada. Todas as imagens recebem faixas/fundo branco quando necessário, assumindo um tamanho base rígido, garantindo consistência visual.

* **Tratamento de Arquivos Novos:** Se um relatório for gerado durante o dia contendo um anexo recém-adicionado (que ainda não foi cacheado pelo job da madrugada), o `pdf_generator` acionará a criação da miniatura "on-the-fly" antes de embutir no PDF. Isso causará um tempo extra apenas na primeira geração, deixando-o em cache para as próximas execuções.

## 5. Passos de Verificação 

1. **O processo ocorrerá remotamente, não sendo possível testes no momento.**

