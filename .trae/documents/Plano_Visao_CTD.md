# Plano de Implementação: Visão CTD (Contract To Today)

## 1. Resumo e Objetivo

Criar uma terceira visão no dashboard atual chamada **CTD**, focada na saúde do contrato como um todo, desde o início (01/03/2026) até o fim (26/02/2027). A visão introduzirá a lógica de "Cooldown", avaliando se os entregáveis pendentes podem ser concluídos no tempo restante, consolidando tudo em um indicador de Temperatura de Saúde.

## 2. Estrutura de Dados e Modificações

Para atender ao requisito de facilidade de manutenção sem exigir novas fontes de dados:

* **Planilha de Escopo (`Escopo Nuclea.xlsx`)**: Adicionar uma coluna `cooldown_dias` na aba `PROD`. O usuário poderá preencher o valor em dias para os entregáveis aplicáveis.

* **Banco de Dados (`database.py`)**:

  * Atualizar a criação da tabela `escopo` para incluir o campo `cooldown_dias INTEGER DEFAULT 0`.

  * Criar uma nova tabela `health_snapshots` para armazenar o histórico mensal da saúde: `id`, `mes_ano` (ex: "2026-07"), `qtd_em_risco` (int), `status_geral` (Verde/Amarelo/Vermelho).

* **Backend (`data_processor.py`** **/** **`app.py`)**:

  * Atualizar `load_escopo()` para ler e processar a nova coluna `cooldown_dias`.

  * Expor esses dados via a rota `/api/data` para consumo no frontend.

## 3. Lógica e Algoritmo de Cálculo

* **Data de Referência (Centralizada)**:
  Criar uma função utilitária em `data_processor.py` que sempre retorne o último dia do mês corrente:

  ```python
  import calendar
  from datetime import date

  def get_reference_date(current_date=None):
      if current_date is None:
          current_date = date.today()
      last_day = calendar.monthrange(current_date.year, current_date.month)[1]
      return date(current_date.year, current_date.month, last_day)
  ```

* **Cálculo de Viabilidade (Pseudocódigo)**:

  ```python
  FIM_CONTRATO = date(2027, 2, 26)
  ref_date = get_reference_date()
  dias_restantes = (FIM_CONTRATO - ref_date).days

  for item in escopo:
      pendentes = max(0, item.qtd_ano - item.realizado_ano)
      
      if item.cooldown_dias > 0:
          dias_minimos_necessarios = pendentes * item.cooldown_dias
          folga = dias_restantes - dias_minimos_necessarios
          
          if pendentes == 0:
              item.status_viabilidade = "Concluído"
          elif dias_minimos_necessarios > dias_restantes:
              item.status_viabilidade = "Em Risco" # Vermelho
          else:
              item.status_viabilidade = "No Prazo" # Verde
      else:
          item.status_viabilidade = "N/A" # Apenas contagem simples
  ```

* **Temperatura de Saúde Geral**:
  Consolidada com base na quantidade de itens "Em Risco":

  * `0 riscos`: Verde (Contrato Saudável)

  * `1 a 2 riscos`: Amarelo (Atenção)

  * `3+ riscos`: Vermelho (Crítico)

## 4. Proposta de Interface de Usuário (UI)

A aba CTD será uma página nova construída do zero, reaproveitando as variáveis de CSS e estilo do dashboard existente, mas sem herdar a lógica de JS do Anual/Mensal.

* **Header**: Adicionar o botão "CTD" no `view-toggle`.

* **KPI Cards (Topo)**:

  1. **Saúde do Contrato**: Indicador Verde/Amarelo/Vermelho baseado nos riscos.
  2. **Entregáveis em Risco**: Contagem de tipos que não cabem no prazo.
  3. **Dias Restantes**: Dias até 26/02/2027.
  4. **Progresso CTD**: % total concluído considerando todo o contrato.

* **Gráficos**:

  1. **Semáforo / Gauge**: Representação visual do indicador de saúde geral.
  2. **Barras Empilhadas por Ano**: Mostrando o volume de entregas feitas em 2026 vs 2027.
  3. **Histórico de Saúde (Linha)**: Gráfico de série temporal mostrando a evolução da quantidade de riscos (extraído da tabela `health_snapshots`).

* **Tabelas**:

  1. **Tabela de Viabilidade (Principal)**: Listando Tipo | Pendentes | Cooldown | Dias Necessários | Dias Restantes | Folga | Status.
  2. **Ações Recomendadas**: Tabela condensada exibindo apenas os itens "Em Risco", destacando a necessidade de priorização.

## 5. Escopo e Classificação dos Entregáveis

A definição exata virá da planilha editada pelo usuário, mas a regra no código tratará:

* **Com Cooldown (`cooldown_dias > 0`)**: Entram no cálculo de viabilidade, geram folga e podem sinalizar risco, impactando a temperatura de saúde geral.

* **Contagem Simples (`cooldown_dias == 0`** **ou vazio)**: Ignorados pelo cálculo de risco de prazo. Contam apenas para o progresso geral e volume de entregas.

## 6. Tratamento de Edge Cases

1. **Sem histórico (Nenhuma entrega ainda)**: Conforme definido com o usuário, o cálculo assumirá que 100% dos itens contratados estão pendentes, exigindo o tempo máximo de cooldown.
2. **Contrato já vencido (`dias_restantes < 0`)**: Qualquer entregável com pendências e cooldown ativo será automaticamente marcado como "Em Risco".
3. **Entregável sem itens pendentes (`pendentes == 0`)**: Status será imediatamente Verde ("Concluído"), isentando o item de cálculos de risco, mesmo que a data esteja próxima.
4. **Item sem cooldown configurado**: Não participa do cômputo de "Em Risco", não afetando a temperatura de saúde.

## 7. Perguntas/Assunções Restantes (Para Validação)

* *Assunção*: A data fim do contrato (26/02/2027) será adicionada como uma constante em `config.py` (`FIM_CONTRATO = date(2027, 2, 26)`) para facilitar alterações em renovações futuras.

* *Assunção*: Para gerar o gráfico histórico de imediato, o sistema calculará retroativamente os snapshots de saúde para os meses anteriores na primeira vez que rodar, populando a tabela `health_snapshots`.

