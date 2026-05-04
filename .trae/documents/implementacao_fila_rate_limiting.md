# Plano de Implementação: Sistema de Rate Limiting e Fila de Processamento

## Resumo
Implementação de uma arquitetura baseada em fila persistente para todas as chamadas à API do runrun.it, garantindo o limite estrito de 30 requisições por minuto com janela deslizante. A solução substituirá o atual modelo síncrono por um modelo assíncrono, resiliente (com retries progressivos) e monitorado, incluindo feedback visual para os usuários.

## Análise do Estado Atual
- As requisições (clientes, tasks, comentários) em `data_processor.py` e `api_client.py` são síncronas e lineares.
- O controle de limite atual é apenas um `time.sleep(0.7)`.
- O banco SQLite (`database.py`) lida bem com dados finais e logs, mas não gerencia os estados transicionais de requisições.
- Não existe um painel específico de monitoramento de saúde da API, apenas os logs brutos no modo debug.

## Mudanças Propostas

### 1. Persistência de Estado e Concorrência (`database.py`)
- **Tabela `api_queue`**: Criar tabela para persistir os jobs (campos: `id`, `endpoint`, `params`, `priority`, `status` [pending, processing, completed, error], `attempts`, `next_attempt_at`, `created_at`, `updated_at`, `error_log`).
- **Tabela `system_locks`**: Criar tabela para gerenciar o lock distribuído. Registrará um timestamp sempre que um usuário acionar a sincronização, impedindo sobreposições (ex: trava ativa por X minutos ou até a fila esvaziar).
- **Tabela `api_metrics`**: Armazenar métricas agregadas (tempo de resposta, status HTTP) para análise de throttling.

### 2. Sistema de Fila Centralizada e Rate Limiting (`queue_manager.py` - Novo)
- **FIFO com Prioridade**: Desenvolver o motor de enfileiramento e consumo. Tipos de dados críticos (ex: metadados do cliente) terão prioridade 1; tasks prioridade 2; comentários prioridade 3.
- **Rate Limiting Robusto**: Implementar contador em janela deslizante de 60 segundos. O worker verificará quantas requisições ocorreram nos últimos 60s (via query rápida) antes de despachar o próximo job.
- **Sistema de Retry Inteligente**: Se o job falhar (timeout ou erro de rede), incrementar `attempts`. `next_attempt_at` receberá `now() + 1s`, depois `+ 3s`, e depois `+ 9s`. Falhando 3 vezes, status vira `error`.
- **Throttling Adaptativo**: Monitorar a taxa de sucesso. Se identificar erros consecutivos ou proximidade com o limite da API (status HTTP 429), reduzir dinamicamente o *throughput* inserindo atrasos extras no loop do worker.

### 3. Integração do Worker (`app.py`, `data_processor.py`, `api_client.py`)
- **Enfileiramento**: Alterar `data_processor.py` para que, ao sincronizar, ele insira todos os jobs de descoberta (tasks) na fila ao invés de bloquearem o processo.
- **Worker em Background**: Iniciar uma *thread* ou um novo job no `APScheduler` (`app.py`) rodando continuamente (ex: a cada 1s) para despachar os itens `pending` da tabela `api_queue`.

### 4. Interface de Status para Usuários (`app.py` e `templates/index.html`)
- **Endpoints**: Adicionar `/api/queue/status` que retornará o tamanho da fila e status atual da sincronização.
- **Frontend**: Criar badges/componentes no header indicando os estados: "Sincronizando...", "Fila pendente: [X] itens" e "Última atualização: [timestamp]". Atualizar via *polling* suave (AJAX a cada 5-10s enquanto estiver sincronizando).

### 5. Monitoramento e Alertas (`templates/debug.html`)
- Transformar/expandir a página de debug em um *Dashboard Administrativo*.
- Mostrar métricas em tempo real: Requisições/minuto, Tempo Médio de Processamento, Taxa de Sucesso e Tamanho da Fila.
- Alerta em destaque no painel caso o tamanho da fila seja `> 100` itens pendentes.

### 6. Documentação Técnica (`docs/sync_architecture.md` - Novo)
- Documentar os parâmetros de configuração (limites, retries, delays).
- Criar diagramas de sequência descrevendo o fluxo de enfileiramento, consumo do worker, rate limiting e persistência.

## Premissas e Decisões
- O motor do banco de dados (SQLite) será mantido como a fonte de verdade para a fila e locks. Essa decisão aproveita a arquitetura existente e evita o peso de introduzir o Redis.
- Como o SQLite possui controle de lock de concorrência natural no arquivo, a tabela `system_locks` ajudará em nível de aplicação (impedindo disparos duplicados de sincronização por vários usuários na UI).
- O limite estrito da API do runrun.it é considerado como 30 req/min (conforme o pedido), alterando a configuração atual do código que mirava 100 req/min.

## Passos de Verificação
1. Executar bateria de requisições em massa e verificar nos logs/banco se nenhuma janela de 60s excede 30 despachos.
2. Forçar erro na conexão com a API e observar no log os atrasos de 1s, 3s e 9s no Retry.
3. Observar a UI no `index.html` para validar os indicadores de fila e sincronização em tempo real.
4. Testar clique múltiplo no botão de sincronização por vários clientes simultâneos para assegurar que o *lock* distribuído funcione e não duplique os jobs.