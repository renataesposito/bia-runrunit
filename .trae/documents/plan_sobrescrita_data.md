# Plano de Implementação: Sobrescrita de Data e Log de Comentários Ignorados

## Resumo
A atualização adiciona a capacidade de sobrescrever a data de uma entrega extraída de um comentário. Caso o usuário que fez o comentário tenha o seu e-mail cadastrado em uma "whitelist" (lista de permitidos) e o comentário contenha uma data no formato brasileiro (DD/MM/YYYY) no final do texto, essa data substituirá a data da criação do comentário para fins de relatório. Além disso, a página de debug será aprimorada para exibir o texto original do comentário ignorado em uma nova coluna.

## Análise do Estado Atual
- Atualmente, as hashtags e quantidades são parseadas da mensagem e a data (`data_str`) é extraída do campo `created_at` em `to_brasilia_time`.
- Os logs de debug gravam itens ignorados sem o texto completo da mensagem. A página `debug.html` exibe esses logs sem uma coluna para exibir o texto, e os parâmetros são salvos como string usando `str(params)` no SQLite.

## Mudanças Propostas

### 1. Configuração de Usuários Permitidos (`.env.example` e `config.py`)
- **O que:** Adicionar uma nova variável de ambiente `ALLOWED_DATE_OVERRIDE_EMAILS`.
- **Como:**
  - No `.env.example`, adicionar algo como `ALLOWED_DATE_OVERRIDE_EMAILS=user1@email.com,user2@email.com`.
  - No `config.py`, carregar a variável usando `os.getenv("ALLOWED_DATE_OVERRIDE_EMAILS", "")` e transformá-la numa lista de e-mails em letras minúsculas.

### 2. Lógica de Sobrescrita de Data (`runrun_report/data_processor.py`)
- **O que:** Modificar a função `load_entregas` para identificar datas ao final do texto, caso o e-mail do autor esteja na lista permitida.
- **Como:**
  - Obter o e-mail do usuário logado no comentário (`user_email = comment.get("user_email")` ou navegando no objeto `user`). *Nota: será feito um pequeno log de verificação para garantir o campo correto retornado pela API do Runrun.it.*
  - Caso `user_email` (convertido para minúsculas) esteja em `ALLOWED_DATE_OVERRIDE_EMAILS`:
    - Executar a regex `r'\s+(\d{2}/\d{2}/\d{4})\s*$'` sobre o texto.
    - Se der match, extrair `DD/MM/YYYY`, converter para o formato ISO `YYYY-MM-DD` e atribuir à variável `data_str` (substituindo a data original `created_at`).

### 3. Melhoria no Registro de Ignorados (`runrun_report/data_processor.py` e `runrun_report/database.py`)
- **O que:** Gravar o texto do comentário nos logs de debug de forma estruturada.
- **Como:**
  - Em `database.py`, na função `log_debug_request`, alterar a inserção do campo `params` para usar `json.dumps(params, ensure_ascii=False)` (importando a biblioteca `json`). Isso garantirá que o campo seja um JSON válido.
  - Em `data_processor.py`, na função `add_ignored_item`, adicionar o parâmetro opcional `comment_text: str = None`.
  - Quando `comment_text` for fornecido, adicioná-lo ao dicionário guardado na memória e enviá-lo como parte dos parâmetros para `log_debug_request`.
  - Atualizar os locais de invocação do `add_ignored_item` dentro do loop de `comments` (ex: "Comentário sem hashtag") para passar o `text` do comentário.

### 4. Nova Coluna na Tela de Debug (`runrun_report/templates/debug.html`)
- **O que:** Mostrar o texto do comentário ignorado diretamente na interface.
- **Como:**
  - No HTML da tabela de Itens Ignorados (`<tbody id="t-ignored-body">`), adicionar uma nova tag `<th>Comentário Original</th>`.
  - No JavaScript (`loadIgnored`), tentar fazer o `JSON.parse` de `item.params` de forma segura (tratando compatibilidade com logs antigos onde usava-se `str()`).
  - Renderizar o valor de `comment_text` na nova coluna criada (`<td>`), ou `-` caso não haja.

## Premissas e Decisões
- O formato do e-mail é utilizado como mecanismo de filtro, conforme selecionado pelo usuário.
- O comentário ignorado aparecerá como uma nova coluna na tabela de log detalhado, tornando-o facilmente legível.
- A conversão de `str(params)` para `json.dumps(params)` não quebra o sistema atual, e a função em Javascript irá contemplar erros de conversão para lidar com os logs legados.

## Verificação
1. Validar se a data em um comentário simulado substitui corretamente a data do relatório (se o usuário estiver listado).
2. Validar se o log ignorado reflete a nova coluna e se o parse JSON funciona corretamente para os itens novos e antigos no modo debug.
