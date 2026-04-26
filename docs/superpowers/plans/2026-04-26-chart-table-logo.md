# Chart Redesign, Tabela Condicional e Logo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar as specs pendentes do CLAUDE.md no dashboard Núclea: gráfico de 3 fatias empilhadas com cores da marca + label/hover do planejado, colunas de mês condicionais na tabela, e logo oficial no header.

**Architecture:** Todas as mudanças são client-side em `runrun_report/templates/index.html`. Nenhum arquivo Python é alterado. O logo estático já existe em `runrun_report/static/nuclea-logo.png`. Flask serve arquivos de `static/` automaticamente em `/static/<filename>`.

**Tech Stack:** Plotly.js 2.32.0, Bootstrap 5.3.2, Flask (servidor local porta 8050)

---

## File Map

| Arquivo | Ação | Seção modificada |
|---------|------|-----------------|
| `runrun_report/templates/index.html` | Modificar | Header (logo), `renderChartEscopo()`, `<thead>` da tabela, `renderEscopoTable()` |
| `runrun_report/static/nuclea-logo.png` | Já existe | — |

---

## Pré-requisito: inicializar git (uma vez)

O projeto ainda não tem repositório git. Antes de começar, rodar:

```powershell
cd C:\Users\r.esposito\vs_code_files\bia\runrun
git init
git add .
git commit -m "chore: initial commit"
```

Se preferir não usar git, ignorar os passos de `git commit` em cada task — eles servem apenas como pontos de checkpoint.

---

## Como rodar o servidor para testar

```powershell
cd C:\Users\r.esposito\vs_code_files\bia\runrun\runrun_report
C:\Users\r.esposito\AppData\Local\Python\bin\python.exe app.py
```

Acesse `http://localhost:8050`. Para reiniciar após alterações:

```powershell
Get-Process -Name python* | Stop-Process -Force
```

---

## Task 1: Logo oficial Núclea no header

**Files:**
- Modify: `runrun_report/templates/index.html` (linhas 99–112 aproximadamente — bloco `<header>`)

- [ ] **Step 1: Localizar o bloco de header no arquivo**

Abrir `runrun_report/templates/index.html` e localizar este trecho exato:

```html
<header id="site-header">
  <div class="brand-logo">
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <path d="M4 24V4L24 24V4" stroke="#DBED1F" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <div>
      <span class="brand-name">núclea</span>
      <span class="brand-sep">|</span>
      <span class="brand-title">Previsto × Realizado</span>
    </div>
  </div>
  <p id="header-sub">Escopo: YESH HUB  |  A partir de 01/03/2026</p>
</header>
```

- [ ] **Step 2: Substituir o bloco pelo novo header com logo**

Substituir o trecho acima por:

```html
<header id="site-header">
  <div class="brand-logo">
    <img src="/static/nuclea-logo.png"
         alt="Logo Núclea"
         style="height:36px;width:auto;filter:invert(1) brightness(2)">
    <div style="border-left:1px solid #444;padding-left:14px">
      <span class="brand-title">Previsto × Realizado</span>
    </div>
  </div>
  <p id="header-sub">Escopo: YESH HUB  |  A partir de 01/03/2026</p>
</header>
```

Nota: o SVG, `brand-name` e `brand-sep` são removidos — o logo já representa a marca.

- [ ] **Step 3: Verificar no browser**

Iniciar servidor e abrir `http://localhost:8050`.

Checar:
- Logo Núclea branco aparece no lado esquerdo do header
- "Previsto × Realizado" aparece à direita do logo, separado por linha vertical
- Fundo escuro `#1A1A1A` mantido, borda lime no rodapé do header
- Sem quebra de layout em larguras diferentes de janela

- [ ] **Step 4: Commit**

```powershell
cd C:\Users\r.esposito\vs_code_files\bia\runrun
git add runrun_report/templates/index.html runrun_report/static/nuclea-logo.png
git commit -m "feat: replace SVG placeholder with official Nuclea logo in header"
```

---

## Task 2: Gráfico — 3 fatias empilhadas com cores Núclea + label + hover

**Files:**
- Modify: `runrun_report/templates/index.html` (função `renderChartEscopo`, ~linhas 397–420)

- [ ] **Step 1: Localizar a função `renderChartEscopo`**

Encontrar este bloco no arquivo:

```js
function renderChartEscopo(escopoR) {
  const height     = Math.max(320, escopoR.length * 28 + 80);
  const labels     = escopoR.map(e => e.entregavel);
  const contratado = escopoR.map(e => e.qtd_ano);
  const realizado  = escopoR.map(e => e.realizado_ano);

  Plotly.react('g-escopo', [
    { name:'Total Contratado', y:labels, x:contratado, type:'bar', orientation:'h',
      marker:{color:BRAND_DARK}, hovertemplate:'%{x}<extra></extra>' },
    { name:'Realizado',        y:labels, x:realizado,  type:'bar', orientation:'h',
      marker:{color:BRAND_LIME}, hovertemplate:'%{x}<extra></extra>' },
  ], {
    barmode: 'overlay',
    title:   { text:'Total Contratado vs Realizado por Entregável', font:{size:13, family:'Inter'} },
    height,
    margin:  {l:260, r:20, t:40, b:40},
    xaxis:   {title:'Quantidade'},
    yaxis:   {autorange:'reversed'},
    legend:  {orientation:'h', y:-0.08},
    paper_bgcolor:'white', plot_bgcolor:'white',
    font:    {family:'Inter'},
  }, {responsive:true, displayModeBar:false});
}
```

- [ ] **Step 2: Substituir pela implementação de 3 fatias**

Substituir a função inteira por:

```js
function renderChartEscopo(escopoR) {
  const height = Math.max(320, escopoR.length * 28 + 80);
  const labels = escopoR.map(e => e.entregavel);

  const realizadoSeg = escopoR.map(e => Math.min(e.realizado_ano, e.qtd_ano));
  const saldo        = escopoR.map(e => Math.max(e.qtd_ano - e.realizado_ano, 0));
  const overflow     = escopoR.map(e => Math.max(e.realizado_ano - e.qtd_ano, 0));

  const customdata = escopoR.map(e => [
    e.realizado_ano,
    e.qtd_ano,
    Math.max(e.qtd_ano - e.realizado_ano, 0),
    Math.max(e.realizado_ano - e.qtd_ano, 0),
    e.entregavel,
  ]);

  const hoverTpl = '<b>%{customdata[4]}</b><br>Realizado: %{customdata[0]}<br>Planejado: %{customdata[1]}<br>Saldo: %{customdata[2]}<br>Acima do previsto: +%{customdata[3]}<extra></extra>';

  const annotations = escopoR.map(e => ({
    x: Math.max(e.qtd_ano, e.realizado_ano),
    y: e.entregavel,
    text: `/ ${e.qtd_ano} plan.`,
    xanchor: 'left',
    yanchor: 'middle',
    showarrow: false,
    font: { size: 10, color: '#6C757D', family: 'Inter' },
    xref: 'x',
    yref: 'y',
  }));

  Plotly.react('g-escopo', [
    { name: 'Realizado', y: labels, x: realizadoSeg, type: 'bar', orientation: 'h',
      marker: { color: BRAND_LIME }, customdata, hovertemplate: hoverTpl },
    { name: 'Saldo', y: labels, x: saldo, type: 'bar', orientation: 'h',
      marker: { color: BRAND_DARK }, customdata, hovertemplate: hoverTpl },
    { name: 'Acima do previsto', y: labels, x: overflow, type: 'bar', orientation: 'h',
      marker: { color: RED }, customdata, hovertemplate: hoverTpl },
  ], {
    barmode: 'stack',
    title:   { text: 'Previsto Acumulado vs Realizado por Entregável', font: { size: 13, family: 'Inter' } },
    height,
    margin:  { l: 260, r: 120, t: 40, b: 40 },
    xaxis:   { title: 'Quantidade' },
    yaxis:   { autorange: 'reversed' },
    legend:  { orientation: 'h', y: -0.08 },
    annotations,
    paper_bgcolor: 'white', plot_bgcolor: 'white',
    font: { family: 'Inter' },
  }, { responsive: true, displayModeBar: false });
}
```

- [ ] **Step 3: Verificar no browser**

Reiniciar servidor e abrir `http://localhost:8050`.

Checar todos os cenários:

| Cenário | O que verificar |
|---------|----------------|
| Entregável com realizado < planejado | Barra lime (realizado) + barra dark (saldo) empilhadas. Total = qtd_ano |
| Entregável com realizado = 0 | Barra 100% dark (saldo). Sem lime |
| Entregável com realizado > planejado | Barra lime até qtd_ano + barra vermelha (overflow) |
| Hover sobre qualquer fatia | Tooltip mostra: nome em negrito, Realizado, Planejado, Saldo, Acima do previsto |
| Label lateral | `/ N plan.` aparece à direita de cada barra |
| Legenda | 3 itens: "Realizado" (lime), "Saldo" (dark), "Acima do previsto" (vermelho) |

- [ ] **Step 4: Commit**

```powershell
git add runrun_report/templates/index.html
git commit -m "feat: redesign chart with 3-segment stacked bars and Nuclea brand colors"
```

---

## Task 3: Tabela — colunas de mês condicionais

**Files:**
- Modify: `runrun_report/templates/index.html` — `<thead>` da tabela (~linha 202–208) e função `renderEscopoTable` (~linha 455)

- [ ] **Step 1: Adicionar IDs aos `<th>` de mês no `<thead>`**

Localizar no `<thead>` da tabela de escopo:

```html
<th class="text-center sortable" onclick="sortEscopo('qtd_mes')">Previsto Qtd/Mês <span id="srt-qtd_mes"></span></th>
```

e

```html
<th class="text-center sortable" onclick="sortEscopo('realizado_mes')">Realizado Qtd/Mês <span id="srt-realizado_mes"></span></th>
```

Adicionar `id="th-mes-prev"` e `id="th-mes-real"` respectivamente:

```html
<th id="th-mes-prev" class="text-center sortable" onclick="sortEscopo('qtd_mes')">Previsto Qtd/Mês <span id="srt-qtd_mes"></span></th>
```

```html
<th id="th-mes-real" class="text-center sortable" onclick="sortEscopo('realizado_mes')">Realizado Qtd/Mês <span id="srt-realizado_mes"></span></th>
```

- [ ] **Step 2: Substituir a função `renderEscopoTable`**

Localizar o início da função:

```js
function renderEscopoTable(escopoR, hasDate) {
  _lastEscopoR = escopoR;
  _lastHasDate = hasDate;
  _lastSorted  = getSortedEscopo(escopoR);

  document.getElementById('t-escopo-body').innerHTML = _lastSorted.map((e, i) => {
    const pct    = e.qtd_ano > 0 ? Math.min(100, Math.round(100 * e.realizado_ano / e.qtd_ano)) : 0;
    const barClr = pct >= 80 ? BRAND_LIME : (pct >= 50 ? ORANGE : (pct > 0 ? RED : GRAY));
    const txtClr = pct >= 80 ? GREEN      : (pct >= 50 ? ORANGE : (pct > 0 ? RED : GRAY));
    const realMes   = hasDate ? e.realizado_mes : '—';
    const hasDetail = e.entregas_detail?.length > 0;
    const tdExtra   = hasDetail
      ? `data-row="${i}" style="color:${txtClr};cursor:help"`
      : `style="color:${txtClr}"`;
    return `<tr>
      <td>${esc(e.grupo)}</td>
      <td>${esc(e.entregavel)}</td>
      <td class="text-center">${e.qtd_mes > 0 ? e.qtd_mes : '—'}</td>
      <td class="text-center">${e.qtd_ano > 0 ? e.qtd_ano : '—'}</td>
      <td class="text-center fw-bold">${realMes}</td>
      <td class="text-center fw-bold" ${tdExtra}>${e.realizado_ano}</td>
      <td>
        <div class="progress mb-1" role="progressbar"
             aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
          <div class="progress-bar" style="width:${pct}%;background:${barClr}"></div>
        </div>
        <small class="text-muted">${pct}%</small>
      </td>
    </tr>`;
  }).join('');
}
```

Substituir por:

```js
function renderEscopoTable(escopoR, hasDate) {
  _lastEscopoR = escopoR;
  _lastHasDate = hasDate;
  _lastSorted  = getSortedEscopo(escopoR);

  document.getElementById('th-mes-prev').style.display = hasDate ? '' : 'none';
  document.getElementById('th-mes-real').style.display = hasDate ? '' : 'none';

  document.getElementById('t-escopo-body').innerHTML = _lastSorted.map((e, i) => {
    const pct    = e.qtd_ano > 0 ? Math.min(100, Math.round(100 * e.realizado_ano / e.qtd_ano)) : 0;
    const barClr = pct >= 80 ? BRAND_LIME : (pct >= 50 ? ORANGE : (pct > 0 ? RED : GRAY));
    const txtClr = pct >= 80 ? GREEN      : (pct >= 50 ? ORANGE : (pct > 0 ? RED : GRAY));
    const hasDetail = e.entregas_detail?.length > 0;
    const tdExtra   = hasDetail
      ? `data-row="${i}" style="color:${txtClr};cursor:help"`
      : `style="color:${txtClr}"`;
    const tdMesPrev = hasDate ? `<td class="text-center">${e.qtd_mes > 0 ? e.qtd_mes : '—'}</td>` : '';
    const tdMesReal = hasDate ? `<td class="text-center fw-bold">${e.realizado_mes}</td>` : '';
    return `<tr>
      <td>${esc(e.grupo)}</td>
      <td>${esc(e.entregavel)}</td>
      ${tdMesPrev}
      <td class="text-center">${e.qtd_ano > 0 ? e.qtd_ano : '—'}</td>
      ${tdMesReal}
      <td class="text-center fw-bold" ${tdExtra}>${e.realizado_ano}</td>
      <td>
        <div class="progress mb-1" role="progressbar"
             aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
          <div class="progress-bar" style="width:${pct}%;background:${barClr}"></div>
        </div>
        <small class="text-muted">${pct}%</small>
      </td>
    </tr>`;
  }).join('');
}
```

- [ ] **Step 3: Verificar no browser**

Reiniciar servidor e abrir `http://localhost:8050`.

| Cenário | O que verificar |
|---------|----------------|
| Campo "Até" vazio (padrão) | Colunas "Previsto Qtd/Mês" e "Realizado Qtd/Mês" **não aparecem** na tabela |
| Preencher campo "Até" com uma data | As duas colunas **aparecem**; "Realizado Qtd/Mês" mostra entregas do período |
| Limpar campo "Até" | Colunas **somem** novamente |
| Ordenação | Clicar em colunas visíveis continua ordenando normalmente |

- [ ] **Step 4: Commit**

```powershell
git add runrun_report/templates/index.html
git commit -m "feat: hide month columns in scope table when no date filter is active"
```

---

## Verificação final integrada

- [ ] **Reiniciar o servidor e abrir `http://localhost:8050`**

Checar que as três features funcionam juntas sem regressão:

- [ ] Header: logo Núclea branco visível
- [ ] Gráfico: 3 fatias empilhadas, cores lime/dark/vermelho, label `/ N plan.` ao lado, hover com detalhes
- [ ] Tabela: visão anual (sem "Até") não mostra colunas de mês; visão mensal (com "Até") mostra
- [ ] Gráfico mensal (`g-mensal`): inalterado
- [ ] Botão "Exportar Excel": funciona normalmente
- [ ] Filtro de grupo: gráfico e tabela atualizam corretamente
- [ ] Hover na tabela (card flutuante de detalhe): continua funcionando
