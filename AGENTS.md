# AGENTS.md

Guia de contexto técnico e convenções para agentes trabalhando no projeto **Bia Runrun.it**.

## Comandos Essenciais

### Desenvolvimento Local
```powershell
cd runrun_report
python app.py
```
- Acessível em `http://localhost:8050`.
- **Reiniciar (Windows):** `Get-Process -Name python* | Stop-Process -Force`

### Docker
```powershell
docker compose up -d    # Sobe app e cloudflared
docker compose restart  # Aplica mudanças de código/env
```

## Arquitetura e Fluxo de Dados

- **Entrypoint:** `runrun_report/app.py`.
- **Config:** `runrun_report/config.py` — `DATA_INICIO=2026-03-01`, `FIM_CONTRATO=2027-02-26`, `CLIENT_NAME="NÚCLEA"`, `API_BASE_URL="https://runrun.it/api/v1.0"`.
- **Banco de Dados:** SQLite em `runrun_report/data/nuclea.db` (configurável via `SQLITE_DB_PATH`).
- **Rate Limiting:** A API do Runrun.it permite **75 req/min** (configurável em `queue_manager.py:11`). Use o `queue_manager.py` para requisições em lote com sliding window de 60s, retry com backoff progressivo `[2, 5, 10, 30, 60]s`, máx 5 retries e até 25 workers paralelos.
- **Sincronização:** Lê Excel (`Escopo Nuclea.xlsx`), busca dados da API via fila e persiste em SQLite. Lock distribuído via tabela `system_locks` para evitar concorrência.
- **Progresso do Sync:** `data_processor.py` mantém `_sync_progress_step` (0..5) avançado após cada etapa de `load_entregas()`: get_clients (1/5) → get_tasks (2/5) → get_comments_batch (3/5) → get_task_attachments_batch (4/5) → get_document_details_batch (5/5). Exposto via `GET /api/sync/progress`.

## Convenções de Negócio (Crítico)

### Geração de PDF (`pdf_generator.py`)
- **Grid de Mídias:** Layout fixo 3x3 (máx 9 itens por página). Dimensões: `1440x810px` (landscape A4 alta resolução).
- **Margem de Segurança:** 10% de respiro no lado direito (`PAGE_W * 0.10`) para evitar sobreposição com o logotipo.
- **Alinhamento de Títulos:** Títulos de tarefas devem usar `Paragraph` para quebra de linha e manter `y=730`-`740` para consistência visual.
- **Ordenação das Seções no PDF:** ① Aprovados (sem correção), ② Aguardando Aprovação (sem correção), ③ Aprovados - Correção, ④ Aguardando Aprovação - Correção.
- **Páginas Template:** `NucleaReport1stPage.pdf` (capa), `2ndPage.pdf` (tabela entregas), `3rdPage.pdf` (mídias genérica), `Approved.pdf`, `WaitingApprove.pdf`, `FixAndOthers.pdf`, `LastPage.pdf`.

### Lógica de Documentos e "Correções"
- **Filtro de Arquivos:** Coletar apenas documentos com a tag `"name": "aprovado"` via endpoint `/api/v1.0/documents/{id}`.
- **Seção de Correções:** Localizada apenas ao final do PDF. Inclui mídias onde a tag de competência (MM/YYYY) difere do mês de entrega da tarefa.
- **Formatação de Tags:** Tags MM/YYYY **devem** ser convertidas para `YYYY-MM` antes de qualquer comparação lógica para evitar falhas silenciosas (função `get_file_competence_yyyy_mm()` em `pdf_generator.py`).

### Thumbnails (`thumbnail_manager.py`)
- **Cache:** Thumbnails salvos em `data/thumbnails/{id}.jpg` (1200x900px, fundo branco).
- **Formatos Suportados:** Imagens (jpg/png/gif/webp), PDFs (primeira página via pdf2image), Office (xls/xlsx/doc/docx/ppt/pptx via LibreOffice), Vídeos (mp4 via FFmpeg, frame em 1s).
- **Sincronização Automática:** `sync_all_thumbnails()` executada via scheduler às 02:00.

### Dashboard — Gráficos (`templates/index.html`)
- **Cor única para "Realizado":** Recorrentes e Não Recorrentes usam **a mesma cor** roxa (`BRAND_LIME = '#9e91c8'`). **Não** criar trace/legenda separada para "Ação Não Recorrente". A variável `GREEN` possui o **mesmo hex** que `BRAND_LIME`.
- **Tabela "Escopo Contratado":** Barra de progresso usa **sempre** `BRAND_LIME` (sem farol verde/amarelo/vermelho, sem azul para não recorrentes). Hover detail mostra até 8 entregas.
- **Anotações `/Mês N` ou `/Ano N`:** Posicionadas por linha, no final da própria barra (`realizado + saldo + overflow`, com 2% de folga). Posição global causava sobreposição — não voltar a usar `maxX` global.

### Dashboard — KPIs
Os títulos e legendas dos 4 cards de KPI são **dinâmicos** via `setKpiLabels(view)` em `renderKpis()`:
- **Visão Anual:** "Saldo Restante" + "itens restantes no contrato" / "Escopo Contratado" + "total previsto no ano" / "realizado / previsto no ano". Use sempre termos relacionados a **ano**.
- **Visão Mensal:** "Tarefas Pendentes no Mês" + "itens restantes no período" / "Tarefas por Mês" + "previsto no período" / "realizado / previsto no período". Use sempre termos relacionados a **mês**.
- **Cores dos KPIs:** `kpi-saldo`: BRAND_DARK (≥0) ou RED (<0). `kpi-realizado`: BRAND_LIME (>0) ou BRAND_DARK. `kpi-pct`: GREEN (≥80%), ORANGE (≥50%), RED (<50%).

### Dashboard — CTD (SLA-to-Delivery)
- **Visão ativada** pelo botão "CTD" no header da página inicial.
- **KPIs:** 5 cards — Saúde do Contrato, Tipos em Risco, Dias Restantes, Progresso CTD, **Meta de Entrega** (unidades/dia necessárias para cumprir o contrato).
- **Cards auxiliares:** "Top 3 Urgências" (itens mais críticos) e "Concluídos do Mês" (entregáveis finalizados).
- **Gráficos:**
  - **Burndown** — curva ideal vs real de saldo restante ao longo dos meses.
  - **Folga por Entregável** — barras horizontais verdes/vermelhas mostrando a folga em dias de cada item com SLA.
  - **Velocidade Mensal** — barras de entregas por mês com linha da meta necessária.
  - **Evolução da Saúde** — barras coloridas por mês mostrando a quantidade de itens em risco.
  - **Treemap** — distribuição hierárquica do contrato por grupo/entregável, colorido por status.
- **Matriz de Risco por Grupo** — tabela heatmap com status por entregável.
- **Tabelas:** "Ações Recomendadas" (itens em risco com SLA), "Quase em Risco" (folga < 30 dias), "Resumo por Grupo" (agregação), "Comparativo Mês a Mês" (variação de risco), e "Viabilidade CTD por Entregável" (completa).
- **Alertas:** 🚨 SLA desrespeitado quando duas entregas do mesmo item ocorrem em intervalo menor que o SLA configurado. Dados servidos via `ctd_aux.sla_violations` no payload `/api/data`.
- **Snapshots históricos** gerados retroativamente por `generate_historical_snapshots()` e servidos via `ctd_snapshots` no payload `/api/data`.

### Dashboard — Filtros
- A visão **Anual** **não tem mais filtros locais** (De/Até/Grupo/Exportar foram movidos para `/debug`).
- A visão **Mensal** mantém os filtros próprios (Ano, Mês, Grupo) em `#filtros-mensal`.
- A tela **Debug** (`/debug`) é onde ficam o filtro (De/Até/Grupo) e o botão "Exportar Excel" para a API `/api/export`. Endpoint `loadGrupos()` popula o select via `/api/data`.

## Configuração de Ambiente
- Requer arquivo `.env` baseado em `.env.example`.
- Variáveis obrigatórias: `APP_KEY`, `USER_TOKEN`.
- `CLOUDFLARE_TUNNEL_TOKEN`: Token do túnel Cloudflare para exposição externa.
- `DEBUG_MODE_ENABLED=true`: Habilita link para tela de debug no header do dashboard.
- `FETCH_ALL_TASKS=true`: Busca todas as tarefas (não apenas `closed=true`) — útil para debug.
- `ALLOWED_DATE_OVERRIDE_EMAILS`: Emails permitidos para sobrescrever data do comentário via data MM/DD/AAAA no final do texto.
- `SQLITE_DB_PATH`: Caminho do banco SQLite (padrão: `data/nuclea.db`).

## Tela de Debug (`templates/debug.html`)

- **Filtros e Exportação:** De/Até (date inputs), Grupo (select), botão "Exportar Excel" → `GET /api/export?ini=&fim=&grupo=`.
- **Log de Requisições à API:** Mostra 250 linhas e exibe até 250 caracteres da coluna Parâmetros. Aumento justificado pela verbosidade de `JSON.stringify(params)`.
- **Sincronismo silencioso:** `syncNow()` **não** exibe `alert()` de erro. O progresso é mostrado no card "Pendente da task" (`metric-sync-progress`, formato `0/5` a `5/5`), atualizado por polling de 3s em `/api/sync/progress`. Cores: muted (inativo), warning (active), success (completo).
- **Card "Pendente da task"** substituiu o antigo "Taxa Sucesso" (que sempre tenderia a 100% em ambiente revisado).
- **Monitoramento da Fila:** 6 cards atualizados a cada 3s via `/api/queue/status` e `/api/queue/metrics`: Reqs/Min, Pendente da task (`sync-progress`), Tempo Médio, Pendente, Processando, Erros/Retries. Alerta visual se pendente > 100.
- **Tasks sem Arquivos (Órfãos):** Tabela via `/api/debug/orphan-tasks` mostrando tasks com entregas mas sem arquivos aprovados/aguardando.
- **Endpoint `GET /api/sync/progress`** (autenticado): retorna `{step, total, active}`.

## Exportação Excel (`export.py`)
- Usa template `yesh_nuclea_template.xlsx` com 3 sheets: Resumo KPIs, Escopo x Realizado, Histórico Entregas.
- Fallback para `_gerar_excel_fallback()` se template não existir.
- Preserva estilos e imagens do template ao preencher dados.

## API — Rotas Principais

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/` | Não | Dashboard principal (`index.html`) |
| GET | `/debug` | **Sim** | Tela de debug (`debug.html`) |
| GET | `/api/data` | Não | KPIs, escopo, entregas, grupos, meses/anos, CTD & snapshots |
| GET | `/api/export` | Não | Exporta Excel filtrado |
| GET | `/api/pdf-report?mes_ano=` | Não | Gera relatório PDF |
| POST | `/api/sync` | **Sim** | Sincronização manual |
| GET | `/api/sync/progress` | **Sim** | Progresso `{step, total, active}` |
| GET | `/api/queue/status` | Não | Status da fila `{pending, processing, errors, completed}` |
| GET | `/api/queue/metrics` | Não | Métricas `{reqs_per_minute, avg_duration_ms, success_rate_pct}` |
| GET | `/api/debug/logs` | **Sim** | Logs de requisições |
| GET | `/api/debug/ignored` | **Sim** | Itens ignorados |
| GET | `/api/debug/orphan-tasks` | **Sim** | Tasks sem arquivos |
| POST | `/api/debug/clear` | **Sim** | Limpa logs |
| GET | `/api/debug/status` | Não | `{enabled, last_sync}` |

## Referências Úteis
- `CLAUDE.md`: Detalhamento completo da arquitetura e esquema do banco.
- `runrun_report/pdf_generator.py`: Lógica principal de layout e grid.
- `runrun_report/data_processor.py`: Regras de processamento de tags, KPIs, CTD e progresso de sync.
- `runrun_report/thumbnail_manager.py`: Gerenciamento de cache de thumbnails.
- `runrun_report/export.py`: Exportação Excel com template.
- `runrun_report/config.py`: Constantes de negócio (datas, cliente, API base URL).
- `runrun_report/queue_manager.py`: Configurações de rate limit e fila.
- `runrun_report/templates/index.html`: Dashboard principal (visão Anual/Mensal/CTD).
- `runrun_report/templates/debug.html`: Tela de diagnóstico, filtros e exportação.
