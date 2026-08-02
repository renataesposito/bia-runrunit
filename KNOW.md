# KNOW.md — Catálogo de Componentes

Catálogo completo de todos os gráficos, tabelas, KPIs e cards do projeto,
organizado por visão. Cada entrada descreve o que é, onde está, o que calcula
e como o cálculo funciona.

---

## Visão Anual (`/`, `index.html`)

### KPI: Saldo Restante

| Campo | Descrição |
|-------|-----------|
| **O que é** | Itens do contrato que ainda não foram entregues |
| **Onde** | `index.html` → `#kpi-saldo`, renderizado por `renderKpis()` |
| **Fórmula** | `total_previsto - total_realizado` |
| **Cálculo** | `previsto = sum(qtd_ano)` de todos os itens de escopo. `realizado = sum(realizado_ano)` com regra de não recorrentes (ver abaixo). Se saldo >= 0 → cor BRAND_DARK (#1A1A1A), se negativo → RED (#DC3545) |
| **Regra não recorrente** | Itens com `qtd_ano < 12` têm realizado limitado a `min(realizado, qtd_ano)` para não inflar o saldo |

### KPI: Entregas Realizadas

| Campo | Descrição |
|-------|-----------|
| **O que é** | Total de entregas registradas via comentários no período |
| **Onde** | `index.html` → `#kpi-realizado`, renderizado por `renderKpis()` |
| **Fórmula** | `sum(realizado_ano)` com regra de não recorrentes |
| **Cálculo** | Soma todas as `quantidade` das entregas mapeadas. Não recorrentes: `min(realizado_ano, qtd_ano)`. Se > 0 → cor BRAND_LIME (#9e91c8), senão BRAND_DARK |

### KPI: % de Realização

| Campo | Descrição |
|-------|-----------|
| **O que é** | Percentual do previsto que já foi realizado |
| **Onde** | `index.html` → `#kpi-pct`, renderizado por `renderKpis()` |
| **Fórmula** | `realizado / previsto_acumulado × 100` |
| **Cálculo** | Usa `total_realizado` (com regra de não recorrentes) e `total_previsto` (soma dos `qtd_ano`). Cor: >= 80% → GREEN (#9e91c8), >= 50% → ORANGE (#E8710A), < 50% → RED (#DC3545) |

### KPI: Escopo Contratado

| Campo | Descrição |
|-------|-----------|
| **O que é** | Total de tarefas previstas no contrato para o período |
| **Onde** | `index.html` → `#kpi-tempo`, renderizado por `renderKpis()` |
| **Fórmula** | Visão Anual: `sum(qtd_ano)`. Visão Mensal: `sum(qtd_ano) / divisor` |
| **Cálculo** | Soma simples de `qtd_ano` de todos os itens. Cor: sempre BRAND_DARK |

### Gráfico: Previsto Acumulado vs Realizado por Entregável

| Campo | Descrição |
|-------|-----------|
| **O que é** | Barras horizontais empilhadas comparando previsto × realizado por entregável |
| **Onde** | `index.html` → `#g-escopo`, renderizado por `renderChartEscopo()` |
| **Dados** | `escopoR`: array com `{entregavel, qtd_ano, realizado_ano, qtd_mes}` |
| **Séries** | 4 séries Plotly em `barmode: 'stack'`: **Realizado (lime/#9e91c8)**, **Saldo (dark/#1A1A1A)**, **Acima do previsto (red/#DC3545)**, e **Ação Não Recorrente (#0D6EFD)** |
| **Cálculo** | Divide itens em Recorrentes (`qtd_ano >= 12`) e Não Recorrentes (`qtd_ano < 12`) com separador visual `"--- NAO RECORRENTES ---"`. Recorrentes usam `qtd_ano / divider` como planejado; não recorrentes usam `qtd_ano`. Realizado de recorrentes é limitado ao planejado (excesso vai para 'Acima do previsto'). Não recorrentes não têm overflow |
| **Anotações** | `/Ano N` ou `/Mes N` ao final de cada barra |
| **Hover** | Nome, tipo (Recorrente/Não Recorrente), Realizado, Planejado, Saldo, Acima do previsto |

### Gráfico: Entregas por Mês

| Campo | Descrição |
|-------|-----------|
| **O que é** | Pizza horizontal mostrando top 5 entregáveis por volume + "Outros" |
| **Onde** | `index.html` → `#g-mensal`, renderizado por `renderChartMensal()` |
| **Dados** | `_data.entregas` filtradas pelo período |
| **Cálculo** | Agrupa entregas mapeadas por `slugToName[scope_slug]`. Pega top 5 por quantidade, junta o resto em "Outros". Total geral exibido no título. Cores da paleta `CORES_PIZZA` |
| **Regra** | Altura sincronizada com o gráfico de escopo via `_lastChartHeight` |

### Tabela: Escopo Contratado — Previsto × Realizado

| Campo | Descrição |
|-------|-----------|
| **O que é** | Tabela de todos os entregáveis com previsto, realizado e barra de progresso |
| **Onde** | `index.html` → `#t-escopo-body`, renderizado por `renderEscopoTable()` |
| **Colunas** | Grupo, Entregável, Previsto Qtd/Ano (ou Qtd/Mês na visão mensal), Realizado Qtd/Ano (ou Qtd/Mês), Progresso (barra colorida + %) |
| **Cálculo** | Progresso = `min(100, realizado / previsto × 100)`. Barra sempre BRAND_LIME. Hover detail mostra até 8 entregas (data, projeto, quantidade) |
| **Ordenação** | Colunas clicáveis (sortável). Padrão: ordem do escopo |

### Tabela: Histórico de Entregas (comentários)

| Campo | Descrição |
|-------|-----------|
| **O que é** | Detalhamento de cada comentário parseado com hashtag |
| **Onde** | `index.html` → `#t-hist-body`, renderizado por `renderHistTable()` |
| **Colunas** | Data, Mês/Ano, Grupo, Projeto, Entregável, Qtd, Mapeado (✓/⚠) |
| **Ordenação** | Padrão: data desc. Todas as colunas são sortáveis |
| **Regra** | Linhas com `mapeado = false` recebem classe `table-warning` |

### Alerta: Entregas não mapeadas

| Campo | Descrição |
|-------|-----------|
| **O que é** | Banner amarelo quando há entregas com hashtag não reconhecido |
| **Onde** | `index.html` → `#alert-unmapped`, renderizado por `checkUnmapped()` |
| **Regra** | Exibe contagem de entregas não mapeadas. Pode ser dispensado pelo usuário |

---

## Visão Mensal (`/`, `index.html`)

### KPIs: mesmo layout da Anual, labels diferentes

| Campo | Descrição |
|-------|-----------|
| **Diferença** | `setKpiLabels('mensal')` altera os títulos dos 4 KPIs para "Tarefas Pendentes no Mês", "Entregas Realizadas", "% de Realização", "Tarefas por Mês" |
| **Cálculo** | Usa `qtd_mes` quando disponível, ou `qtd_ano / 12 × meses_selecionados`. Divisor mensal = `12 / numMeses` |

### Gráficos e Tabelas

Os mesmos componentes da visão Anual, mas:
- **Filtro**: dropdown de Ano + botões de mês clicáveis (apenas meses com dados) + dropdown de Grupo
- **Gráfico de barras**: usa `divider = 12 / numMeses` para proportionar o previsto. Anotações mostram `/Mes N`
- **Tabela**: colunas trocam Qtd/Ano por Qtd/Mês

---

## Visão CTD (`/ctd`, `ctd.html`)

### KPI: Saúde do Contrato

| Campo | Descrição |
|-------|-----------|
| **O que é** | Indicador geral de saúde baseado em quantos entregáveis estão em risco |
| **Onde** | `ctd.html` → `#ctd-saude-val`, calculado em `updateCTD()` |
| **Fórmula** | `qtd_em_risco == 0` → Verde ("Saudável"), `1-2` → Amarelo ("Atenção"), `>= 3` → Vermelho ("Crítico") |
| **Cálculo** | `compute_ctd_viability()` em `data_processor.py` conta itens com `status == "Em Risco"` no dict `viabilidade_list` |

### KPI: Tipos em Risco

| Campo | Descrição |
|-------|-----------|
| **O que é** | Quantos entregáveis estão com status "Em Risco" |
| **Onde** | `ctd.html` → `#ctd-risco-val`, calculado em `updateCTD()` |
| **Fórmula** | `qtd_em_risco` (contagem de `viabilidade` com status "Em Risco") |
| **Cálculo** | Se `qtd_em_risco > 0` → cor RED, senão GREEN |

### KPI: Dias Restantes

| Campo | Descrição |
|-------|-----------|
| **O que é** | Dias até o fim do contrato |
| **Onde** | `ctd.html` → `#ctd-dias-val` |
| **Fórmula** | `(FIM_CONTRATO - get_reference_date()).days` |
| **Fonte** | `FIM_CONTRATO = 2027-02-26` em `config.py`. Data de referência = último dia do mês corrente |

### KPI: Progresso CTD

| Campo | Descrição |
|-------|-----------|
| **O que é** | Percentual do contrato já realizado |
| **Onde** | `ctd.html` → `#ctd-prog-val` |
| **Fórmula** | `total_realizado / total_contrato × 100` |
| **Dados** | `_data.kpis.total_contrato` e `total_realizado` |

### KPI: Meta de Entrega

| Campo | Descrição |
|-------|-----------|
| **O que é** | Unidades por dia (e por mês) necessárias para cumprir o contrato |
| **Onde** | `ctd.html` → `#ctd-meta-val`, calculado por `renderCTDMeta()` |
| **Fórmula** | `por_dia = pendentes / dias_restantes`. `por_mes = pendentes / max(1, dias_restantes / 30)` |
| **Fonte** | `compute_delivery_meta()` em `data_processor.py` |

### Card: Top 3 Urgências

| Campo | Descrição |
|-------|-----------|
| **O que é** | 3 cards com os entregáveis mais críticos (pior folga) |
| **Onde** | `ctd.html` → `#ctd-top3-container`, renderizado por `renderCTDTop3()` |
| **Cálculo** | Filtra `viabilidade` por `status == "Em Risco"`, ordena por `folga` ascendente, pega os 3 primeiros. Exibe: grupo, déficit em dias, pendentes |

### Card: Concluídos do Mês

| Campo | Descrição |
|-------|-----------|
| **O que é** | Pills verdes com entregáveis que já foram 100% concluídos |
| **Onde** | `ctd.html` → `#ctd-concluidos-container`, renderizado por `renderCTDConcluidos()` |
| **Cálculo** | Filtra `viabilidade` por `status == "Concluido"`. Exibe nome em badge verde |

### Gráfico: Burndown — Saldo Restante

| Campo | Descrição |
|-------|-----------|
| **O que é** | Curva ideal vs real do saldo restante ao longo do contrato |
| **Onde** | `ctd.html` → `#g-ctd-burndown`, renderizado por `renderCTDBurndown()` |
| **Dados** | Eixo X: meses dos `ctd_snapshots`. Linha ideal: reta de `total_contrato` até 0. Linha real: `total_contrato - cumulativo(monthly_velocity)` |
| **Cálculo** | `yActual[mes] = totalContrato - sum(entregas ate aquele mes)`. Usa `velMap` de `monthly_velocity` para acumular progressivamente. Se só 1 snapshot, mostra reta. Cor: Ideal = cinza tracejado, Real = BRAND_LIME |

### Gráfico: Folga por Entregável

| Campo | Descrição |
|-------|-----------|
| **O que é** | Barras horizontais mostrando dias de folga para itens com SLA |
| **Onde** | `ctd.html` → `#g-ctd-folga`, renderizado por `renderCTDFolga()` |
| **Dados** | Itens com `sla_dias > 0` e `status != "Concluido"`. Ordenados por folga ascendente |
| **Fórmula** | `folga = dias_restantes - (pendentes × sla_dias)`. Verde se >= 0, Vermelho se < 0 |

### Gráfico: Velocidade Mensal de Entregas

| Campo | Descrição |
|-------|-----------|
| **O que é** | Barras de entregas por mês com linha da meta necessária |
| **Onde** | `ctd.html` → `#g-ctd-velocidade`, renderizado por `renderCTDVelocidade()` |
| **Dados** | `monthly_velocity` do backend: array `{mes_ano, total}` |
| **Meta** | `metaMes = pendentes / max(1, dias_restantes / 30)`. Linha horizontal tracejada em vermelho |

### Gráfico: Volume Mensal com Alvo Dinâmico

| Campo | Descrição |
|-------|-----------|
| **O que é** | Mesmas barras de volume mensal, mas com alvo que se recalcula a cada mês |
| **Onde** | `ctd.html` → `#g-ctd-volume-alvo`, renderizado por `renderCTDVolumeAlvo()` |
| **Cálculo** | Para cada mês (usando `mesIndex` real desde o início do contrato): `alvo = (totalContrato - cumReal) / (12 - mesIndex)`. Déficits de meses anteriores são redistribuídos automaticamente — se um mês entrega menos que o alvo, o saldo falta é incorporado aos meses seguintes |
| **Exemplo** | Mês 1 (mesIndex=0): alvo = total/12. Se entregou menos, o déficit faz o alvo do mês 2 subir proporcionalmente |
| **Constantes** | `MES_INICIO = 3` (março), `ANO_INICIO = 2026`, `TOTAL_MESES = 12` |

### Gráfico: Evolução da Saúde (Timeline)

| Campo | Descrição |
|-------|-----------|
| **O que é** | Barras coloridas mensais mostrando a quantidade de itens em risco |
| **Onde** | `ctd.html` → `#g-ctd-timeline-snapshots`, renderizado por `renderCTDTimeline()` |
| **Dados** | `ctd_snapshots`: `{mes_ano, qtd_em_risco, status_geral}` |
| **Cálculo** | Altura da barra = `qtd_em_risco / max(qtd_em_risco) × 100%`. Cor: Verde (#198754), Amarelo (#FF9F00), Vermelho (#DC3545) conforme `status_geral` |
| **Formato** | HTML puro (sem Plotly) com divs estilizadas |

### Gráfico: Distribuição do Contrato (Treemap)

| Campo | Descrição |
|-------|-----------|
| **O que é** | Mapa hierárquico tipo treemap: grupos como raízes, entregáveis como filhos |
| **Onde** | `ctd.html` → `#g-ctd-treemap`, renderizado por `renderCTDTreemap()` |
| **Dados** | `viabilidade` com `{grupo, entregavel, pendentes, sla_dias, status}` |
| **Cálculo** | Tamanho = `max(1, pendentes + (sla_dias > 0 ? sla_dias : 1))`. Cor = `{Concluido: verde, No Prazo: azul, Em Risco: vermelho, N/A: cinza}` |
| **Hierarquia** | Grupos são adicionados como nós raiz (`parent = ''`), entregáveis como filhos (`parent = grupo`) |

### Tabela: Matriz de Risco por Grupo

| Campo | Descrição |
|-------|-----------|
| **O que é** | Heatmap com grupos nas linhas, entregáveis únicos nas colunas, células coloridas por status |
| **Onde** | `ctd.html` → `#t-matriz-headers` + `#t-ctd-matriz-body`, renderizado por `renderCTDMatrizRisco()` |
| **Dados** | `viabilidade` — deduplica slugs de entregáveis como colunas, agrupa por grupo nas linhas |
| **Cores** | Concluído = verde (`#d1e7dd`), No Prazo = azul (`#cfe2ff`), Em Risco = vermelho (`#f8d7da`), N/A = cinza (`#e2e3e5`). Símbolos: OK / ! / - |
| **Extra** | Linha de legenda textual acima dos grupos mostrando o status de cada entregável |

### Tabela: Ações Recomendadas (Itens em Risco)

| Campo | Descrição |
|-------|-----------|
| **O que é** | Tabela condensada apenas com entregáveis em risco |
| **Onde** | `ctd.html` → `#panel-acoes-rec`, visível apenas se `emRisco.length > 0` |
| **Colunas** | Entregável, Pendentes, SLA (dias), Dias Mínimos, Restam, Status (badge vermelho com déficit) |
| **Cálculo** | Filtro: `viabilidade.filter(v => v.status === "Em Risco")` |

### Tabela: Quase em Risco

| Campo | Descrição |
|-------|-----------|
| **O que é** | Itens "No Prazo" mas com folga pequena (alerta preventivo) |
| **Onde** | `ctd.html` → `#panel-quase-risco`, visível se houver itens |
| **Critério** | `status == "No Prazo" && folga >= 0 && folga < 30` |
| **Colunas** | Entregável, Folga (dias), SLA (dias), Pendentes |

### Tabela: Resumo por Grupo

| Campo | Descrição |
|-------|-----------|
| **O que é** | Agregação dos dados de viabilidade por grupo |
| **Onde** | `ctd.html` → `#t-ctd-resumo-grupo-body`, renderizado por `renderCTDResumoGrupo()` |
| **Colunas** | Grupo, Itens, Em Risco, % Saudável, Pendentes Total, Folga Média |
| **Cálculo** | `pctSaudavel = (total - risco) / total × 100`. `folgaMedia = sum(folgas) / len(folgas)` |

### Tabela: Comparativo Mês a Mês

| Campo | Descrição |
|-------|-----------|
| **O que é** | Compara todos os itens entre o mês atual e o anterior (collapsível) |
| **Onde** | `ctd.html` → `#ctd-comparativo-content`, renderizado por `renderCTDComparativo()` |
| **Dados** | Usa `ctd_snapshots[atual].detalhes_json` e `ctd_snapshots[anterior].detalhes_json` |
| **Variação** | "Melhorou" (estava em risco, não está mais), "Piorou" (não estava, está), "Ainda em risco", "OK" (nunca esteve) |
| **Extra** | Usa TODOS os itens da viabilidade atual, não apenas os que estiveram em risco |

### Tabela: Viabilidade CTD por Entregável

| Campo | Descrição |
|-------|-----------|
| **O que é** | Tabela completa com todos os dados de viabilidade para cada entregável |
| **Onde** | `ctd.html` → `#t-ctd-body`, renderizado em `updateCTD()` |
| **Colunas** | Grupo, Entregável, Pendentes, SLA (dias), Mín. Necessário, Restantes, Folga, Status |
| **Cálculo** | `pendentes = max(0, round(qtd_ano) - round(realizado))`. `dias_minimos = pendentes × sla_dias`. `folga = dias_restantes - dias_minimos`. Status: Concluído (pendentes = 0), Em Risco (dias_minimos > dias_restantes), No Prazo, N/A (sem SLA) |
| **sla_dias** | Aceita float. Lido do Excel com vírgula pt-BR (ex: `0,5`). |
| **Badges** | Concluído = verde, Em Risco = vermelho, No Prazo = azul info, N/A = cinza |

---

## Debug (`/debug`, `debug.html`)

### Painel: Última Sincronização

| Campo | Descrição |
|-------|-----------|
| **O que é** | Informações da última sincronização (início, fim, status, registros) |
| **Endpoint** | `GET /api/debug/status` → `{enabled, last_sync}` |
| **Dados** | `sync_log` no SQLite |

### Painel: Monitoramento da Fila

| Campo | Descrição |
|-------|-----------|
| **O que é** | 6 cards com métricas da fila de requisições, atualizados a cada 3s |
| **Endpoints** | `GET /api/queue/status` (pending, processing, errors, completed) e `GET /api/queue/metrics` (reqs_per_minute, avg_duration_ms, success_rate_pct) |
| **Alertas** | Vermelho se `pending > 100` |

### Painel: Logs de Requisições

| Campo | Descrição |
|-------|-----------|
| **O que é** | Tabela com 250 linhas de log de requisições à API |
| **Endpoint** | `GET /api/debug/logs?limit=250` |
| **Filtro** | Remove `ignored_comment` do log |

### Painel: Itens Ignorados

| Campo | Descrição |
|-------|-----------|
| **O que é** | Tabela de hashtags não mapeados, comentários sem quantidade, etc. |
| **Endpoint** | `GET /api/debug/ignored?limit=100` |
| **Fonte** | `data_processor._ignored_items` populado durante `load_entregas()` |

### Painel: Tarefas Órfãs

| Campo | Descrição |
|-------|-----------|
| **O que é** | Tasks com entregas no dashboard mas sem arquivos com tag aprovado/aguardando |
| **Endpoint** | `GET /api/debug/orphan-tasks` |
| **Critério** | Task tem entregas mapeadas, mas nenhum anexo com tags "aprovado" ou "aguardando" |

### Exportação: Excel

| Campo | Descrição |
|-------|-----------|
| **O que é** | Planilha Excel com 3 abas: Resumo KPIs, Escopo x Realizado, Histórico Entregas |
| **Endpoint** | `GET /api/export?ini=YYYY-MM-DD&fim=YYYY-MM-DD&grupo=...` |
| **Template** | Usa `yesh_nuclea_template.xlsx` se existir, senão gera do zero via `_gerar_excel_fallback()` |
| **Formatação** | Preserva estilos, bordas e imagens do template. Cabeçalho azul escuro (`#1F3864`) com fonte branca |

### Exportação: PDF de Status

| Campo | Descrição |
|-------|-----------|
| **O que é** | Relatório mensal em PDF com capa, tabela de entregas e grid de mídias |
| **Endpoint** | `GET /api/pdf-report?mes_ano=YYYY-MM` |
| **Dimensões** | 1440×810px (A4 paisagem) |
| **Páginas** | Capa (template), Tabela de Entregas, Páginas de mídia (grid 3×3 por task), Última página |
| **Seções** | 1. Aprovados, 2. Aguardando Aprovação, 3. Correções (mídias com competência diferente do mês de entrega) |

---

## Dados Compartilhados

| Campo | Endpoint | Descrição |
|-------|----------|-----------|
| `kpis` | `GET /api/data` | `total_previsto`, `total_realizado`, `total_contrato`, `saldo_escopo`, `pct_realizacao`, `meses_decorridos`, `tempo_contrato_meses`, `escopo_nome` |
| `ctd` | `GET /api/data` | `viabilidade[]` (grupo, entregavel, pendentes, sla_dias, dias_minimos, dias_restantes, folga, status, slug) + `saude` (status_geral, qtd_em_risco, dias_restantes, ref_date, fim_contrato) |
| `ctd_snapshots` | `GET /api/data` | `[]` de `{mes_ano, qtd_em_risco, status_geral, detalhes_json}` |
| `ctd_aux` | `GET /api/data` | `sla_violations`, `monthly_velocity` (`{mes_ano, total}`), `delivery_meta` (`pendentes`, `por_dia`, `por_mes`, `dias_restantes`) |
| `queue/status` | `GET /api/queue/status` | `pending`, `processing`, `errors`, `completed` |
| `queue/metrics` | `GET /api/queue/metrics` | `reqs_per_minute`, `avg_duration_ms`, `success_rate_pct` |

---

## Constantes e Configurações

| Constante | Arquivo | Valor | Uso |
|-----------|---------|-------|-----|
| `DATA_INICIO` | `config.py` | `2026-03-01` | Marco zero do contrato |
| `FIM_CONTRATO` | `config.py` | `2027-02-26` | Fim do contrato |
| `TEMPO_CONTRATO_MESES` | `data_processor.py` | `12` | Duração em meses |
| `TZ_BRASIL` | `data_processor.py` | `GMT-3` | Fuso horário Brasília |
| `ESCOPO_NOME` | `data_processor.py` | `"YESH HUB"` | Nome do contrato no header |
| `CLIENT_NAME` | `config.py` | `"NÚCLEA"` | Nome do cliente na API |
| `BRAND_DARK` | `index.html` / `ctd.html` | `#1A1A1A` | Cor principal escura |
| `BRAND_LIME` | `index.html` / `ctd.html` | `#9e91c8` | Cor de destaque (realizado) |
| `API_BASE_URL` | `config.py` | `https://runrun.it/api/v1.0` | URL base da API RunRun.it |
| `MAX_REQ_PER_MIN` | `queue_manager.py` | `30` | Limite de requisições por minuto |
