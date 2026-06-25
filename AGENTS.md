# AGENTS.md

Guia de contexto técnico e convenções para agentes trabalhando no projeto **Bia Runrun.it**.

## Comandos Essenciais

### Desenvolvimento Local
```powershell
# Iniciar servidor Flask (Dashboard + API)
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
- **Banco de Dados:** SQLite em `runrun_report/data/nuclea.db`.
- **Rate Limiting:** A API do Runrun.it é limitada a **30 req/min**. Use o `queue_manager.py` para requisições em lote.
- **Sincronização:** Compara Excel (`Escopo Nuclea.xlsx`) com dados da API.

## Convenções de Negócio (Crítico)

### Geração de PDF (`pdf_generator.py`)
- **Grid de Mídias:** Layout fixo 3x3 (máx 9 itens por página).
- **Margem de Segurança:** 10% de respiro no lado direito para evitar sobreposição com o logotipo.
- **Alinhamento de Títulos:** Títulos de tarefas devem usar `Paragraph` para quebra de linha e manter `y=730` para consistência visual.

### Lógica de Documentos e "Correções"
- **Filtro de Arquivos:** Coletar apenas documentos com a tag `"name": "aprovado"` via endpoint `/api/v1.0/documents/{id}`.
- **Seção de Correções:** Localizada apenas ao final do PDF. Inclui mídias onde a tag de competência (MM/YYYY) difere do mês de entrega da tarefa.
- **Formatação de Tags:** Tags MM/YYYY **devem** ser convertidas para `YYYY-MM` antes de qualquer comparação lógica para evitar falhas silenciosas.

## Configuração de Ambiente
- Requer arquivo `.env` baseado em `.env.example`.
- Variáveis obrigatórias: `APP_KEY`, `USER_TOKEN`.
- `DEBUG_MODE_ENABLED=true` habilita ferramentas de inspeção no dashboard.

## Referências Úteis
- `CLAUDE.md`: Detalhamento completo da arquitetura e esquema do banco.
- `runrun_report/pdf_generator.py`: Lógica principal de layout e grid.
- `runrun_report/data_processor.py`: Regras de processamento de tags e KPIs.
