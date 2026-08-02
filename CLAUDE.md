# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Dashboard de acompanhamento de escopo do cliente **NÚCLEA** no RunRun.it. Compara entregas **previstas** (Excel) com entregas **realizadas** (comentários do RunRun.it). O nome exibido no header como identificação do contrato é **YESH HUB**.

- Cliente (API): `NÚCLEA`
- Escopo/contrato (header): `YESH HUB`
- Marco zero do contrato (`DATA_INICIO`): `2026-03-01`
- Vigência: 12 meses (março → fevereiro)

## Como rodar

### Modo local (Python direto)

```powershell
# A partir da pasta runrun_report
cd runrun_report
python app.py
```

Acesse em `http://localhost:8050`. A porta pode ser sobrescrita pela env var `PORT`. O CORS está habilitado para `https://renataesposito.github.io` (origem da página estática consumidora).

### Modo Docker

```powershell
# A partir da raiz do repo
docker compose up -d
```

Sobe dois containers:
- `app` — Flask + scheduler (porta 8050, healthcheck a cada 30s)
- `cloudflared` — tunnel Cloudflare usando `CLOUDFLARE_TUNNEL_TOKEN` (opcional, ignorado se vazio)

O `Dockerfile` usa `python:3.11-slim`, instala `requirements.txt` e roda `python app.py`.

### Reiniciar o servidor

```powershell
# Local
Get-Process -Name python* | Stop-Process -Force

# Docker
docker compose restart app
```

## Arquitetura

### Stack e camadas

```
                            ┌──────────────────────────────────────────┐
                            │  templates/index.html  (SPA, Plotly)    │
                            │  templates/ctd.html   (CTD dedicado)    │
                            │  templates/debug.html  (modo debug)     │
                            └──────────────────┬───────────────────────┘
                                               │ fetch (GET)
                            ┌──────────────────▼───────────────────────┐
                            │  app.py  (Flask, porta 8050)             │
                            │  /  /ctd  /api/data  /api/export        │
                            │  /api/pdf-report  /api/sync  /api/queue/*│
                            │  /api/debug/*  /debug                   │
                               │                             │
                ┌──────────────▼─────────────┐   ┌───────────▼──────────────┐
                │  data_processor.py         │   │  export.py / pdf_generator│
                │  (parse Excel, hashtags,   │   │  (openpyxl, reportlab)   │
                │   _match_tag, KPIs)        │   └──────────────────────────┘
                └──────┬─────────┬───────────┘
                       │         │
          ┌────────────▼───┐  ┌──▼────────────────┐
          │  api_client.py │  │  database.py      │
          │  (get_client_  │  │  (SQLite:         │
          │   id, tasks,   │  │   data/nuclea.db) │
          │   comments)    │  │                   │
          └──────┬─────────┘  └───────────────────┘
                 │
          ┌──────▼──────────────────────────┐
          │  queue_manager.py               │
          │  - Fila persistente no SQLite   │
          │  - Sliding-window 30 req/min    │
          │  - Retries com backoff          │
          │  - Worker thread em background  │
          └─────────────────────────────────┘
```

### Persistência (SQLite)

Banco: `data/nuclea.db` (caminho configurável via `SQLITE_DB_PATH`). Tabelas:

| Tabela | Função |
|--------|--------|
| `escopo` | Cache do Excel (id, grupo, entregavel, qtd_mes, qtd_ano, previsto_acumulado, slug) |
| `entregas` | Entregas extraídas da API (task_id, projeto, grupo, hashtag, scope_slug, quantidade, data, mes_ano, mapeado) |
| `sync_log` | Histórico de sincronizações (início, fim, status, registros, erro) |
| `api_queue` | Fila persistente de requisições HTTP (status, attempts, next_attempt_at, result, error_log) |
| `api_metrics` | Métricas por requisição (timestamp, endpoint, status_code, duration_ms, success) |
| `system_locks` | Lock distribuído para evitar syncs concorrentes |
| `debug_log` | Logs e itens ignorados durante sync |
| `config` | Pares chave/valor de configuração |

### Carga inicial (bootstrap)

1. `app.py:_initial_data_load()` chama `database.init_database()` (cria tabelas se não existem)
2. Se o banco está vazio: carrega o Excel temporariamente para a UI não quebrar, e dispara `sync_data()` em **background thread** (a sincronização pesada da API não bloqueia o start)
3. Caso contrário, lê direto do banco
4. Em seguida, `api_client.init_worker()` liga o **worker da fila** e `_start_scheduler()` agenda sync diário às 00:00 (`apscheduler`)

Para forçar reload dos dados, use `POST /api/sync` (autenticado) ou clique em **"Sincronizar Agora"** em `/debug`.

### Sincronização (`data_processor.sync_data`)

- Adquire lock distribuído `sync_lock` (TTL 600s) para evitar execuções paralelas
- Carrega escopo do Excel → salva no banco
- Para cada task de "Gestão de Atendimento" do cliente, enfileira busca de comentários na fila e aguarda
- Salva entregas no banco
- Logs de início/fim em `sync_log` (com `sync_id`)
- Rate limit é controlado pelo `queue_manager` (ver abaixo)

### Fila e rate limiting (`queue_manager.py`)

Todas as chamadas à API RunRun.it passam pela fila persistente. Configuração:

| Parâmetro | Valor | Efeito |
|-----------|-------|--------|
| `MAX_REQ_PER_MIN` | `30` | Limite por janela deslizante |
| `SLIDING_WINDOW_SEC` | `60` | Tamanho da janela |
| `MAX_RETRIES` | `5` | Tentativas em caso de falha |
| `RETRY_DELAYS` | `[2, 5, 10, 30, 60]` s | Backoff progressivo; +10s extra em HTTP 429 |

**Prioridades:** 1 = clientes (crítico), 2 = tasks, 3 = comentários/anexos (maior volume).

O worker usa `BEGIN EXCLUSIVE TRANSACTION` para evitar race conditions e insere um placeholder em `api_metrics` antes da chamada HTTP, garantindo que o rate limit seja contado **antes** da requisição sair.

### Endpoints da API RunRun.it

- Base: `https://runrun.it/api/v1.0`
- Headers: `App-Key` e `User-Token` (env vars `APP_KEY` e `USER_TOKEN`)
- Endpoints usados: `clients`, `tasks`, `comments`, `documents` (anexos)
- Comentários de sistema (`is_system_message: true`) são ignorados
- O endpoint `time_worked` não existe — horas ficam em `time_worked` na própria task

## Configuração

### `config.py`

```python
DATA_INICIO = date(2026, 3, 1)
CLIENT_NAME = "NÚCLEA"
API_BASE_URL = "https://runrun.it/api/v1.0"
ESCOPO_NOME = "YESH HUB"          # exibido no header
TEMPO_CONTRATO_MESES = 12         # vigência anual
ALLOWED_DATE_OVERRIDE_EMAILS = [] # emails que podem sobrescrever a data do comentário via prefixo "DD/MM/YYYY"
```

### `.env` (copie de `.env.example`)

```env
APP_KEY=...
USER_TOKEN=...
CLOUDFLARE_TUNNEL_TOKEN=...       # opcional (Docker)

DEBUG_MODE_ENABLED=false          # exibe botão "⚙ Debug" no header
FETCH_ALL_TASKS=false             # true = ignora filtro "gestão de atendimento" e traz todas as tasks
SQLITE_DB_PATH=data/nuclea.db     # caminho do SQLite
ALLOWED_DATE_OVERRIDE_EMAILS=...  # csv de emails autorizados a usar override de data
```

### Dependências (`requirements.txt`)

```
requests, pandas, flask, flask-cors, openpyxl, python-dotenv,
apscheduler, reportlab, Pillow
```

## Como as entregas são registradas no RunRun.it

Cada projeto do cliente deve ter uma tarefa chamada **"Gestão de Atendimento"** (matching por substring no título: `gest` + `atend`). O fluxo:

1. A tarefa recebe uma **tag** identificando o entregável (ex.: `Posts pré-evento Núclea Day`).
2. Quando uma entrega ocorre, o responsável posta um **comentário** com o padrão `#slugN`, onde `slug` é o nome da tag normalizado (minúsculas, sem acentos, sem espaços) e `N` é a quantidade. Exemplo: `#postspre-eventonucleaday3`.
3. **Data do comentário** (convertida para GMT-3) determina o mês de entrega.
4. **Opcionalmente**, o comentário pode terminar com uma data `DD/MM/YYYY` — ela sobrescreve a data do comentário (somente para autores em `ALLOWED_DATE_OVERRIDE_EMAILS`).
5. Um comentário pode conter **múltiplos hashtags**: `#posts5 #reels2`.
6. **Cada comentário soma à quantidade já realizada** — não substitui.
7. Qualquer entregável pode ser realizado em qualquer grupo (matching por nome, não por grupo da task).

## Matching tag → escopo (`_match_tag`)

Em `data_processor.py`, vinculado em 3 passos:

1. **Match exato**: `_slug(tag) == escopo.slug`
2. **Substring**: `escopo.slug` está contido em `tag.slug` (permite prefixos como `n_` para Núclea Day ou `ep_` para eventos patrocinados)
3. **Similaridade** (≥ 92%) usando `difflib.SequenceMatcher` — ignora hífens e prefixos conhecidos na comparação

A busca não é restrita ao `project_group_name` da task.

**Convenção recomendada**: usar o nome exato do ENTREGÁVEL como tag no RunRun.it → garante match exato e elimina ambiguidade.

## Regras de Contagem (convenção operacional)

**Posts de Redes Sociais:** se a arte for igual mas a legenda mudar para redes diferentes (Instagram vs. LinkedIn), conta-se como **2 posts**. Se arte e legenda forem 100% replicadas, conta-se como **1 post**. Esta regra é convenção documentada para fins de auditoria — o sistema contabiliza puramente pelas hashtags, então a responsabilidade de seguir a regra é de quem posta o comentário.

**Reels/Vídeos curtos:** cada upload é 1 unidade no escopo, independente da duração.

**Recorrentes vs Não Recorrentes** (regra de visualização): o frontend classifica cada entregável como **recorrente** quando `qtd_ano >= 12` e **não recorrente** caso contrário. Não recorrentes:
- não exibem barra de "Acima do previsto" (overflow) no gráfico
- no KPI de "Entregas Realizadas", o valor é limitado a `min(realizado, previsto)` para não inflar o saldo

## Escopo — Excel

Arquivo: `runrun_report/Escopo Nuclea.xlsx`, aba **`PROD`**. A primeira coluna é descartada (índice vazio). Estrutura:

| GRUPOS | ENTREGÁVEIS | QUANTIDADE/MÊS | QUANTIDADE/ANO |
|--------|-------------|----------------|----------------|
| `03_Eventos` | `Posts pré-evento Núclea Day` | `1` | `12` |

- `GRUPOS` é só organização visual; não restringe matching de entregas
- `QUANTIDADE/MÊS = 0` ou vazio → usa fórmula proporcional ao ano: `round(qtd_ano * meses / 12)`
- `QUANTIDADE/MÊS > 0` → usa `round(qtd_mes * meses_decorridos)`
- Linhas com `qtd_mes = 0` e `qtd_ano = 0` são descartadas (cabeçalho/rodapé)

## Frontend

Páginas servidas pelo Flask:

- `templates/index.html` — dashboard principal (visões Anual e Mensal) em `/`
- `templates/ctd.html` — dashboard CTD dedicado em `/ctd` (página autônoma extraída do index.html)
- `templates/debug.html` — ferramentas de diagnóstico em `/debug` (autenticado)

Todas as páginas consomem `GET /api/data` na inicialização. Bibliotecas via CDN: Bootstrap 5, Plotly.js, Inter font.

### Dashboard — componentes (`index.html`)

**Header**: logo Núclea, toggle **Anual/Mensal** (com link para `/ctd`), badge de status de sincronização, badge da fila (`Fila: N itens`), última atualização.

**Toggle Anual/Mensal**:
- **Anual** — filtros: `De` (data), `Até` (data), `Grupo`; exporta Excel com o range aplicado
- **Mensal** — filtros: `Ano` (dropdown), botões de mês clicáveis (apenas meses com dados habilitados), `Grupo`

**4 KPI cards** (cores mudam por threshold):
| KPI | Cálculo | Cores |
|-----|---------|-------|
| **Tarefas Pendentes no Mês** | previsto − realizado (período) | preto se saldo ≥ 0, vermelho se negativo |
| **Entregas Realizadas** | soma de `realizado` no período | lime se > 0 |
| **% de Realização** | `realizado / previsto` × 100 | verde ≥ 80%, laranja ≥ 50%, vermelho < 50% |
| **Tarefas por Mês** | `previsto` (recorrente → `qtd_ano/divisor`; não recorrente → `qtd_ano`) | preto |

**Regra dos KPIs** (anual e mensal): para entregáveis **não recorrentes** (`qtd_ano < 12`), o realizado é capeado em `min(realizado, previsto)` para não inflar o saldo do contrato.

### Gráfico: Previsto Acumulado vs Realizado por Entregável

Barras horizontais empilhadas, **4 séries**:

| Série (cor) | Significado |
|-------------|-------------|
| **Realizado (Recorrente)** — lime (`#9e91c8`) | Realizado, apenas para `qtd_ano >= 12`, limitado ao planejado |
| **Ação Não Recorrente** — azul (`#0D6EFD`) | Realizado, apenas para `qtd_ano < 12`, sem trava de planejado |
| **Saldo** — dark (`#1A1A1A`) | `max(planejado − realizado, 0)` |
| **Acima do previsto** — vermelho (`#DC3545`) | `max(realizado − planejado, 0)`, apenas para recorrentes |

Separador visual `─── NÃO RECORRENTES ───` aparece entre as duas seções quando há entregas recorrentes e não recorrentes. O divisor padrão anual é 1; na visão mensal com N meses selecionados, o divisor é `12/N` (só para recorrentes).

**Hover** exibe: nome, tipo (Recorrente/Não Recorrente), Realizado, Planejado, Saldo, e "Acima do previsto: +N" se houver overflow.

**Anotações inline** mostram `label valor` (ex.: `/Ano 12`) ao final de cada barra.

### Gráfico: Entregas por Mês

Pizza horizontal mostrando o top 5 entregáveis por volume + agrupamento "Outros" (cinza). Total geral no título. Sincroniza altura com o gráfico de escopo.

### Tabela: Escopo Contratado — Previsto × Realizado

Colunas:

| Coluna | Visão Anual | Visão Mensal |
|--------|-------------|--------------|
| Grupos | ✓ | ✓ |
| Entregáveis | ✓ | ✓ |
| Previsto Qtd/Mês | oculta | ✓ (mostra `qtd_mes` ou `—` se 0) |
| Previsto Qtd/Ano | ✓ | oculta |
| Realizado Qtd/Mês | oculta | ✓ |
| Realizado Qtd/Ano | ✓ | oculta |
| Progresso | ✓ (barra colorida por threshold + %) | ✓ |

Linhas com entregas detalhadas exibem um card flutuante (`#hover-detail`) no mouseover com até 8 entregas (data, projeto, quantidade) + "… e mais N".

### Tabela: Histórico de Entregas (comentários)

Detalhe de cada comentário parseado: Data, Mês/Ano, Grupo, Projeto, Entregável, Qtd, badge Mapeado ✓/⚠. Linhas com `mapeado = false` recebem `table-warning`. A ordenação default é `data desc`; todas as colunas são sortáveis.

### Alerta de entregas não mapeadas

Banner amarelo automático quando há comentários cujo hashtag não foi vinculado a nenhum item do escopo. Sinaliza que o nome da tag precisa ser corrigido.

### Polling

- `GET /api/queue/status` a cada 5s para atualizar badge da fila
- `GET /api/debug/status` quando a fila esvazia, para atualizar "Última atualização"

### Página CTD (`/ctd`, `templates/ctd.html`)

Página autônoma extraída do index.html. Mesmo endpoint `/api/data`, sem polling de fila.

**Header**: logo, botões "Anual/Mensal" (link para `/`) e "CTD" (active), última atualização.

**5 KPI cards**:
| KPI | Cálculo |
|-----|---------|
| **Saúde do Contrato** | Verde (0 risco), Amarelo (1-2), Vermelho (3+) |
| **Tipos em Risco** | Contagem de entregáveis com `status = "Em Risco"` |
| **Dias Restantes** | `FIM_CONTRATO - ref_date` |
| **Progresso CTD** | `total_realizado / total_contrato × 100` |
| **Meta de Entrega** | `pendentes / dias_restantes` (unidades/dia) + `pendentes / (dias_restantes/30)` (unidades/mês) |

**Cards auxiliares**: "Top 3 Urgências" (3 itens com pior folga) e "Concluídos do Mês" (status = "Concluído").

**Gráficos**:
- **Burndown**: linha ideal (reta de total_contrato até 0) vs linha real (acumulado de `monthly_velocity`). Eixo X = meses desde DATA_INICIO.
- **Folga por Entregável**: barras horizontais de `folga = dias_restantes - dias_minimos`. Verde se >= 0, vermelho se < 0. Apenas itens com SLA > 0 e não concluídos.
- **Velocidade Mensal**: barras de entregas por mês + linha de meta fixa (`pendentes / (dias_restantes / 30)`).
- **Volume Mensal com Alvo Dinâmico**: barras iguais à velocidade, mas alvo recalcula a cada mês: `alvo = (totalContrato - cumReal) / (12 - mesIndex)`. Déficits são redistribuídos.
- **Evolução da Saúde**: barras coloridas por mês a partir de `ctd_snapshots`. Altura proporcional a `qtd_em_risco`, cor conforme `status_geral`.
- **Treemap**: hierarquia grupo → entregável. Tamanho = peso no contrato (pendentes + sla). Cor = status. Grupos como nós raiz.

**Tabelas**:
- **Matriz de Risco**: colunas = entregáveis únicos (slug), linhas = grupos. Células OK/!/- coloridas por status. Linha de legenda textual.
- **Ações Recomendadas**: itens "Em Risco" com pendentes, SLA, dias mínimos, déficit.
- **Quase em Risco**: itens "No Prazo" com folga >= 0 e < 30 dias.
- **Resumo por Grupo**: agregação (itens, em risco, % saudável, pendentes, folga média).
- **Comparativo Mês a Mês**: todos os itens comparando mês atual vs anterior (Melhorou/Piorou/OK). Colapsável.
- **Viabilidade CTD**: completa com grupo, entregável, pendentes, SLA, dias mínimos, restantes, folga, status.

**Dados**: `sla_dias` aceita float (lido do Excel com vírgula pt-BR, ex: 0,5).

## Modo Debug (`/debug`)

Acesso via header (botão **⚙ Debug** aparece quando `DEBUG_MODE_ENABLED=true`) ou diretamente em `/debug`. Protegido por **autenticação básica HTTP** (`requires_auth` em `app.py`).

Credenciais hardcoded (temporário, substituir por auth real): usuário qualquer, senha `nuclea123`.

Funcionalidades expostas:
- Última sincronização (início, fim, status, registros)
- Botão **"Sincronizar Agora"** → `POST /api/sync`
- Botão **"Limpar Logs"** → `POST /api/debug/clear`
- Geração de **Relatório de Status em PDF** (`/api/pdf-report?mes_ano=YYYY-MM`)
- Monitoramento da fila: reqs/min, taxa de sucesso, tempo médio, pending, processing, errors
- Alerta vermelho se `pending > 100`
- Tabela de logs de requisições
- Tabela de itens ignorados (hashtags não mapeados, comentários sem quantidade, etc.)

## PDF de Status (`pdf_generator.py`)

Endpoint: `GET /api/pdf-report?mes_ano=YYYY-MM` (sem auth, para consumo via `fetch` no frontend).

Conteúdo:
1. **Capa**: título, cliente (NÚCLEA), referência do mês, data de geração
2. **Histórico de Entregas**: tabela com Data, Grupo, Projeto, Entregável, Qtd (ordenada por data desc)
3. **Corpo**: para cada task que teve entregas no mês, exibe título, data de entrega e grid 3×2 com thumbnails dos anexos (imagens) baixados da API (`/documents/{id}/download`) e processados com Pillow em 150 DPI

Usa ReportLab + PIL; orientação paisagem A4.

## Export Excel (`export.py`)

Endpoint: `GET /api/export?ini=YYYY-MM-DD&fim=YYYY-MM-DD&grupo=...`

Usa o template `runrun_report/yesh_nuclea_template.xlsx` (3 abas):
- **Resumo KPIs** — Meses decorridos, Entregas Previstas, Entregas Realizadas, % de Realização
- **Escopo x Realizado** — Grupo, Entregável, Qtd/Mês, Escopo Ano, Previsto Acumulado, Realizado
- **Histórico Entregas** — Mês/Ano, Grupo, Projeto, Entregável, Quantidade

A função `_clear_and_fill_table` preserva o template (estilos, imagens-âncora) limpando só o conteúdo das células, sem deletar linhas. Se o template não existir, gera do zero via `_gerar_excel_fallback`.

## CORS

`CORS(app, origins=["https://renataesposito.github.io"])` — permite que a página estática publicada em `renataesposito.github.io` consuma a API. Para outras origens, ajustar em `app.py`.

## `.gitignore`

Ignora: `*.pyc`, `__pycache__/`, `.env`, `.superpowers/`, `plans/validacao-reuniao-vs-codebase.md`.

> ⚠️ O arquivo `plans/validacao-reuniao-vs-codebase.md` está no repositório local mas listado no `.gitignore` — é um documento histórico da reunião de validação, preservado localmente mas não commitado.
