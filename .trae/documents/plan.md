# Plano de Implementação: Seção "Correções" no PDF e Casos Órfãos no Debug

## Resumo
O objetivo é adicionar uma nova seção chamada "Correções" no final do relatório PDF, listando casos de mídia aprovados/entregues que normalmente ficariam de fora do relatório principal. Esses casos são identificados por anexos que possuem duas tags específicas: "aprovado" e a tag de competência (ex: "05/2026"). Casos órfãos (com tag "aprovado" mas sem competência) não vão para o PDF e serão exibidos em uma nova tabela na tela de Debug.

## Análise do Estado Atual
- O relatório PDF é gerado em `pdf_generator.py`, que atualmente filtra as tasks baseadas no mês selecionado (`mes_ano`) e busca seus anexos sob demanda.
- Os dados são sincronizados no banco de dados SQLite (`database.py`) pela função `load_entregas` em `data_processor.py`. No entanto, os anexos das tasks não são salvos no banco.
- A tela de Debug (`debug.html`) exibe status da sincronização e fila, usando JavaScript para buscar dados da API do Flask (`app.py`).

## Mudanças Propostas

### 1. Atualização do Banco de Dados (`database.py`)
- **O que**: Adicionar uma nova tabela `anexos` e funções de acesso.
- **Por que**: Precisamos ter todos os anexos sincronizados no banco para buscar eficientemente as tags "aprovado" e de competência em todas as tasks, sem esgotar o limite de requisições da API durante a geração do PDF.
- **Como**: 
  - Em `init_database()`, executar: `CREATE TABLE IF NOT EXISTS anexos (id INTEGER PRIMARY KEY, task_id INTEGER, data_json TEXT)`
  - Criar funções `save_anexos(anexos_list: list[dict])` e `load_all_anexos() -> list[dict]`.

### 2. Sincronização de Anexos (`data_processor.py`)
- **O que**: Buscar anexos e salvá-los no banco durante a sincronização (`load_entregas`).
- **Por que**: Para popular a tabela `anexos` criada acima.
- **Como**:
  - Chamar `api_client.get_task_attachments_batch(task_ids)` para buscar anexos das tasks.
  - Extrair os anexos que vêm dentro dos comentários (`all_comments`).
  - Remover duplicatas pelo ID do anexo.
  - Salvar todos usando `database.save_anexos()`.

### 3. Nova Seção "Correções" no PDF (`pdf_generator.py`)
- **O que**: Adicionar a seção ao final do documento.
- **Por que**: Requisito principal da nova funcionalidade.
- **Como**:
  - Após renderizar o corpo principal do PDF, carregar todos os anexos do banco de dados.
  - Identificar os anexos que contêm a tag "aprovado" e a tag igual a `mes_ano` (ex: "05/2026").
  - Ignorar anexos cujas tasks já estejam no relatório principal (lista `ordered_task_ids`).
  - Agrupar os anexos encontrados por `task_id` e renderizá-los com o mesmo formato de thumbnail usado na seção principal.

### 4. Tabela de Casos Órfãos no Debug (`app.py` e `debug.html`)
- **O que**: Criar um endpoint na API e exibir na interface de Debug os casos órfãos.
- **Por que**: Controle interno para anexos marcados como "aprovado" mas sem mês/ano.
- **Como**:
  - No `app.py`, criar a rota `/api/debug/orphan-cases` que carrega os anexos do banco, filtra os que têm "aprovado" mas nenhuma tag que faça match com a regex `\d{2}/\d{4}`, e retorna como JSON.
  - No `debug.html`, adicionar uma nova seção de tabela abaixo da API metrics, chamar o endpoint `/api/debug/orphan-cases` e preencher a tabela via JavaScript.

## Suposições e Decisões
- **Tags de Anexos**: Como não está 100% explícito como a API do Runrun.it expõe as tags do documento, buscaremos em propriedades comuns como `tags`, `document_tags`, e como fallback procuraremos no nome do arquivo caso seja uma convenção de nomenclatura.
- **Performance**: A busca de anexos será feita no momento da sincronização diária para evitar que a geração do PDF demore minutos.
- **Tasks no Relatório**: Se uma task já está no relatório principal por causa de uma entrega normal, seus arquivos de "correção" não criarão uma entrada duplicada na seção "Correções". O arquivo aparecerá junto aos anexos normais da task no corpo principal. A seção "Correções" lidará apenas com "tasks que normalmente ficariam de fora".

## Passos de Verificação
1. Iniciar o servidor e executar uma sincronização (via tela de Debug ou chamada na API) para popular a tabela de anexos.
2. Acessar a tela de Debug e verificar se a tabela de "Casos Órfãos" é renderizada corretamente, mostrando dados reais ou vazia sem erros.
3. Gerar o PDF de Status e verificar se a seção "Correções" é adicionada ao final, contendo os arquivos com "aprovado" e a competência correta.
4. Assegurar que nenhuma quebra ocorre no Dashboard principal nem na exportação em Excel.