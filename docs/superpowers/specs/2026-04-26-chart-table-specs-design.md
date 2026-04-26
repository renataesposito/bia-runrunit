# Design: Implementação das Specs Pendentes do CLAUDE.md

**Data:** 2026-04-26  
**Escopo:** `runrun_report/templates/index.html`  
**Status:** Aprovado

---

## Contexto

O dashboard Núclea (Previsto × Realizado) possui duas specs definidas no `CLAUDE.md` que não estão implementadas no código atual:

1. **Gráfico de barras horizontais** — usa `barmode: 'overlay'` com 2 traces; a spec exige 3 fatias empilhadas com overflow destacado.
2. **Tabela de escopo** — exibe as colunas de mês sempre (com `—` quando sem filtro); a spec exige ocultá-las na visão anual.

O usuário também solicitou duas adições à spec original do gráfico:
- Paleta de cores da identidade visual Núclea (lime/dark/vermelho).
- Exibição do total planejado tanto como label lateral quanto no hover.

---

## Seção 1 — Gráfico: 3 Fatias Empilhadas

### Função alterada
`renderChartEscopo(escopoR)` em `templates/index.html`

### Lógica das fatias

Baseline de comparação: `qtd_ano` (quantidade total contratada no ano).

| Trace | Valor | Cor |
|-------|-------|-----|
| `realizado_seg` | `min(realizado_ano, qtd_ano)` | `#DBED1F` (lime Núclea) |
| `saldo` | `max(qtd_ano - realizado_ano, 0)` | `#1A1A1A` (dark Núclea) |
| `overflow` | `max(realizado_ano - qtd_ano, 0)` | `#DC3545` (vermelho) |

- Quando `realizado_ano ≤ qtd_ano`: `realizado_seg + saldo = qtd_ano` ✓
- Quando `realizado_ano > qtd_ano`: `realizado_seg + overflow = qtd_ano + (realizado_ano - qtd_ano) = realizado_ano` ✓

### Label lateral (total planejado)

Usar `layout.annotations` — **não** um 4º trace (em `barmode: 'stack'` um trace extra soma ao comprimento da barra, distorcendo o gráfico).

Uma annotation por entregável, adicionada ao layout:

```js
annotations: escopoR.map(e => ({
  x: Math.max(e.qtd_ano, e.realizado_ano),  // sempre na borda direita da barra
  y: e.entregavel,
  text: `/ ${e.qtd_ano} plan.`,
  xanchor: 'left',
  yanchor: 'middle',
  showarrow: false,
  font: { size: 10, color: '#6C757D', family: 'Inter' },
  xref: 'x',
  yref: 'y',
}))
```

- `x = max(qtd_ano, realizado_ano)` garante que o label fique sempre à direita, mesmo em caso de overflow.

### Hover (tooltip unificado)

Todos os 3 traces visíveis recebem:
- `customdata`: array `[realizado_ano, qtd_ano, saldo_val, overflow_val, entregavel]` para cada ponto
- `hovertemplate` idêntico nos 3 traces:

```
<b>%{customdata[4]}</b><br>
Realizado: %{customdata[0]}<br>
Planejado: %{customdata[1]}<br>
Saldo: %{customdata[2]}<br>
Acima do previsto: +%{customdata[3]}<extra></extra>
```

- `<extra></extra>` suprime o nome da série no tooltip.
- Quando `overflow = 0`, a linha "Acima do previsto" mostra `+0` — aceitável; não requer lógica condicional no template.

### Layout

```js
{
  barmode: 'stack',
  title: { text: 'Previsto Acumulado vs Realizado por Entregável', font: {size:13, family:'Inter'} },
  height,
  margin: {l:260, r:120, t:40, b:40},  // r aumentado para acomodar label lateral
  xaxis: { title: 'Quantidade' },
  yaxis: { autorange: 'reversed' },
  legend: { orientation: 'h', y: -0.08 },
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: { family: 'Inter' },
}
```

---

## Seção 2 — Tabela: Colunas Condicionais por Periodicidade

### Regra

| Situação | `Previsto Qtd/Mês` | `Realizado Qtd/Mês` |
|----------|--------------------|----------------------|
| Campo "Até" preenchido (`hasDate = true`) | Visível | Visível |
| Campo "Até" vazio (`hasDate = false`) | **Oculta** | **Oculta** |

`hasDate` já existe no código: `const hasDate = f.fim !== ''`.

### Implementação no `<thead>`

Adicionar IDs nos dois `<th>` de mês:

```html
<th id="th-mes-prev" class="text-center sortable" ...>Previsto Qtd/Mês</th>
<th id="th-mes-real" class="text-center sortable" ...>Realizado Qtd/Mês</th>
```

Toggle no início de `renderEscopoTable(escopoR, hasDate)`:

```js
document.getElementById('th-mes-prev').style.display = hasDate ? '' : 'none';
document.getElementById('th-mes-real').style.display = hasDate ? '' : 'none';
```

### Implementação no `<tbody>`

Nas linhas geradas (template string), substituir as células de mês por:

```js
const tdMesPrev = hasDate
  ? `<td class="text-center">${e.qtd_mes > 0 ? e.qtd_mes : '—'}</td>`
  : '';
const tdMesReal = hasDate
  ? `<td class="text-center fw-bold">${e.realizado_mes}</td>`
  : '';
```

E incluir `${tdMesPrev}` e `${tdMesReal}` no lugar certo na string de cada `<tr>`.

---

## Seção 3 — Logo oficial Núclea no header

### Motivação
O header atual usa um SVG genérico (letra "N"). O usuário quer o logo oficial da marca.

### Arquivo
Logo baixado de `https://www.nuclea.com.br/wp-content/uploads/2024/03/logo_NUCLEA_PRETO-1024x374-1.png` e salvo em:
```
runrun_report/static/nuclea-logo.png
```
Flask serve arquivos de `static/` automaticamente em `/static/<filename>`.

### Alteração no header (`templates/index.html`)

Substituir o bloco `.brand-logo` atual:

```html
<!-- ANTES -->
<div class="brand-logo">
  <svg width="28" height="28" ...>...</svg>
  <div>
    <span class="brand-name">núclea</span>
    <span class="brand-sep">|</span>
    <span class="brand-title">Previsto × Realizado</span>
  </div>
</div>

<!-- DEPOIS -->
<div class="brand-logo">
  <img src="/static/nuclea-logo.png"
       alt="Logo Núclea"
       style="height:36px;width:auto;filter:invert(1) brightness(2)">
  <div style="border-left:1px solid #444;padding-left:14px">
    <span class="brand-title">Previsto × Realizado</span>
  </div>
</div>
```

- `filter: invert(1) brightness(2)` torna o logo preto em branco sobre o fundo `#1A1A1A`.
- O `<span class="brand-name">núclea</span>` e o `<span class="brand-sep">|</span>` são removidos — o logo já representa a marca.
- `height: 36px` mantém proporção sem ocupar espaço excessivo.

---

## Arquivos afetados

| Arquivo | Mudança |
|---------|---------|
| `runrun_report/templates/index.html` | Gráfico (Seções 1) + Tabela (Seção 2) + Header (Seção 3) |
| `runrun_report/static/nuclea-logo.png` | Arquivo novo (já criado) |

Nenhuma mudança em `app.py`, `data_processor.py`, `export.py` ou `config.py`.

---

## Fora do escopo

- Gráfico mensal (`g-mensal`) — não alterado.
- Export Excel — não alterado.
- Lógica de matching de tags — não alterada.
- Qualquer outra funcionalidade do dashboard.
