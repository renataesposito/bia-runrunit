# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Como rodar

```powershell
# Python está em:
C:\Users\r.esposito\AppData\Local\Python\bin\python.exe

# Iniciar o servidor (sempre a partir da pasta runrun_report):
cd C:\Users\r.esposito\vs_code_files\bia\runrun\runrun_report
C:\Users\r.esposito\AppData\Local\Python\bin\python.exe app.py
```

Acesse em `http://localhost:8050`. O servidor carrega todos os dados da API na inicialização — pode levar alguns segundos.

Para matar o servidor e reiniciar após alterações:
```powershell
Get-Process -Name python* | Stop-Process -Force
```

## Arquitetura

### Visão geral

Dashboard de acompanhamento de escopo do cliente **NÚCLEA** (id `1356501` no RunRun.it). Compara entregas **previstas** (Excel) com entregas **realizadas** (comentários do RunRun.it).

```
Escopo Nuclea.xlsx (aba PROD)   →  data_processor.load_escopo()
RunRun.it API (comentários)     →  data_processor.load_entregas()
                                        ↓
                               app.py  (Flask, porta 8050)
                                        ↓
                          GET /api/data  →  templates/index.html (Bootstrap + Plotly.js)
                          GET /api/export → export.py (openpyxl)
```

Todos os dados são carregados **uma única vez na inicialização** do servidor (`app.py` módulo-level). Não há banco de dados; para atualizar os dados é preciso reiniciar o servidor.

### Como as entregas são registradas no RunRun.it

Cada projeto do cliente deve ter uma tarefa chamada **"Gestão de Atendimento"**. O fluxo é:

1. A tarefa recebe uma **tag** identificando qual entregável do escopo aquele projeto entrega (ex.: `Posts pré-evento Núclea Day`).
2. Quando uma entrega ocorre, a responsável posta um **comentário** com o padrão `#slugN`, onde `slug` é o nome da tag normalizado (minúsculas, sem acentos, sem espaços) e `N` é a quantidade numérica.  
   Exemplo: `#postspre-eventonucleaday3`
3. A **data do comentário** determina o mês de entrega no relatório.
4. Um comentário pode conter múltiplos hashtags: `#posts5 #reels2`.
5. **Cada novo comentário soma à quantidade já realizada** — não substitui. O total realizado de um entregável é o somatório de todos os `N` encontrados em todos os comentários da tarefa ao longo do tempo.
6. **Qualquer entregável pode ser realizado em qualquer grupo**, independentemente do grupo ao qual ele pertence nas colunas "GRUPOS" e "ENTREGÁVEIS" do Excel. O vínculo entre tag e escopo é feito pelo nome da tag, não pelo grupo da tarefa.

### Matching tag → escopo

A função `_match_tag()` em `data_processor.py` vincula o slug da tag ao item do escopo em dois passos:
1. **Match exato**: `_slug(tag) == escopo.slug`
2. **Match por substring**: o slug do entregável está contido no slug da tag — permite prefixos como `n_` (Núclea Day) ou `ep_` (eventos patrocinados) sem quebrar o vínculo.

A busca **não é restrita ao grupo da tarefa**; um entregável pode ser realizado em qualquer projeto independentemente do `project_group_name`.

**Convenção recomendada**: usar o nome exato do ENTREGÁVEL como nome da tag no RunRun.it. Isso garante match exato e elimina ambiguidade.

### Regras de Contagem

**Posts de Redes Sociais:** Se a arte for igual, mas a legenda mudar para redes diferentes (Instagram vs. LinkedIn), conta-se como **2 posts**. Se arte e legenda forem 100% replicadas, conta-se como **1 post**. Esta regra é uma convenção operacional documentada para fins de auditoria — o sistema contabiliza baseado puramente nas hashtags inseridas nos comentários, então a responsabilidade de seguir esta regra é de quem postar o comentário.

**Reels/Vídeos curtos:** Contam como items отдельные distinctos no escopo. Cada upload é contabilizado como 1 unidade, independente da duração.

### Escopo — Excel

Arquivo: `Escopo Nuclea.xlsx`, aba **`PROD`**.  
Estrutura das colunas (a primeira coluna é ignorada — índice vazio):

| GRUPOS | ENTREGÁVEIS | QUANTIDADE/MÊS | QUANTIDADE/ANO |
|--------|-------------|----------------|----------------|
| `03_Eventos` | `Posts pré-evento Núclea Day` | `1` | `12` |

- `GRUPOS` é usado apenas para organização visual no relatório; não restringe o matching de entregas.
- Itens com `QUANTIDADE/MÊS = 0` ou vazio usam a fórmula proporcional ao ano: `round(qtd_ano * meses / 12)`.
- Itens com `QUANTIDADE/MÊS > 0` usam: `round(qtd_mes * meses_decorridos)`.

`DATA_INICIO = 2026-03-01` (definido em `config.py`) é o marco zero para o cálculo de meses decorridos.

### API RunRun.it

- Base URL: `https://runrun.it/api/v1.0`
- Credenciais: `APP_KEY` e `USER_TOKEN` em `.env`
- Rate limit respeitado: 0,7 s entre páginas paginadas (~85 req/min)
- Endpoints utilizados: `clients`, `tasks`, `comments`
- O endpoint `time_worked` **não existe** na API — as horas ficam no campo `time_worked` da própria task
- Comentários de sistema (`is_system_message: true`) são ignorados

### Frontend

`templates/index.html` é uma SPA servida pelo Flask. Faz uma única chamada `GET /api/data` e todo o restante é renderizado client-side com Plotly.js e Bootstrap 5 (CDN). Filtros por data e grupo recalculam `realizado` no browser sem nova requisição ao servidor.

O alerta de "entrega não mapeada" aparece automaticamente quando um hashtag não encontra correspondência no escopo — sinal de que o nome da tag precisa ser corrigido.

---

## Relatório — Especificação dos componentes visuais

### Gráfico: Previsto Acumulado vs Realizado por Entregável

Gráfico de barras horizontais, uma linha por entregável do escopo. Cada barra é composta por **três fatias sobrepostas**, da esquerda para a direita:

| Fatia | Cor | Valor |
|-------|-----|-------|
| Realizado | Verde | Quantidade total entregue (soma de todos os comentários mapeados) |
| Saldo | Azul escuro | `Previsto Qtd/Ano − Realizado`, quando realizado < previsto |
| Overflow | Vermelho | `Realizado − Previsto Qtd/Ano`, quando realizado > previsto (fatia extra além do azul) |

**Implementação das fatias:**
- Implementar como três séries de barras empilhadas: `realizado`, `saldo`, `overflow`.
- Quando `realizado ≤ previsto`: `saldo = previsto − realizado`, `overflow = 0`.
- Quando `realizado > previsto`: `saldo = 0`, `overflow = realizado − previsto`.
- A largura total da barra sempre representa o maior entre `previsto` e `realizado`.

**Comportamento do hover:**
- Exibir apenas os valores numéricos ao passar o mouse, sem rótulos de série ou texto adicional.

---

### Tabela: Escopo Contratado — Previsto × Realizado

Tabela detalhada com uma linha por entregável. A linha de cabeçalho do dataset **não deve ser exibida como dado** — somente as linhas de conteúdo.

**Colunas:**

| Coluna | Descrição |
|--------|-----------|
| **Grupos** | Grupo do entregável conforme coluna `GRUPOS` do Excel |
| **Entregáveis** | Nome do entregável conforme coluna `ENTREGÁVEIS` do Excel |
| **Previsto Qtd/Mês** | Quantidade prevista por mês (`QUANTIDADE/MÊS` do Excel) |
| **Previsto Qtd/Ano** | Quantidade total prevista no ano (`QUANTIDADE/ANO` do Excel) |
| **Realizado Qtd/Mês** | Soma das entregas registradas via tags × comentários no mês selecionado no filtro de periodicidade |
| **Realizado Qtd/Ano** | Soma de todas as entregas registradas via tags × comentários no acumulado do ano |
| **Progresso** | `Realizado Qtd/Ano ÷ Previsto Qtd/Ano`, exibido como percentual |

**Regras de exibição por periodicidade:**

- **Com filtro de mês selecionado**: todas as colunas são exibidas normalmente; `Realizado Qtd/Mês` reflete o período selecionado.
- **Sem filtro de mês (visão anual)**: as colunas `Previsto Qtd/Mês` e `Realizado Qtd/Mês` são **ocultadas**; apenas as colunas de ano e o progresso são apresentados.

---

## Configuração (`config.py`)

```python
DATA_INICIO = date(2026, 3, 1)   # marco zero do contrato
CLIENT_NAME = "NÚCLEA"           # nome exato como aparece na API (com acento)
API_BASE_URL = "https://runrun.it/api/v1.0"
```

Para mudar o cliente ou a data de início, edite apenas este arquivo.

## Dependências

```
requests, pandas, flask, openpyxl, python-dotenv
```

Instalar:
```powershell
C:\Users\r.esposito\AppData\Local\Python\bin\python.exe -m pip install -r runrun_report\requirements.txt
```
