import io
import json
import os
from datetime import date
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import pandas as pd
import data_processor
import export
import database

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://renataesposito.github.io"])

# Variáveis globais para dados em memória
_escopo = None
_entregas = None
_escopo_real = None
_kpis = None
_scheduler = None


def _load_data_from_db():
    """Carrega dados do banco SQLite."""
    global _escopo, _entregas, _escopo_real, _kpis
    
    print("Carregando dados do banco SQLite...")
    _escopo = database.load_escopo_from_db()
    _entregas = database.load_entregas_from_db()
    
    if _escopo.empty or _entregas.empty:
        print("Banco vazio ou incompleto. Executando carga inicial...")
        return False
    
    _escopo_real = data_processor.escopo_com_realizado(_escopo, _entregas)
    _kpis = data_processor.compute_kpis(_escopo, _entregas)
    print(f"Dados carregados: {len(_escopo)} itens de escopo, {len(_entregas)} entregas")
    return True


import threading

def _async_initial_sync():
    """Roda a sincronização inicial em background."""
    print("Primeira execução - realizando carga completa da API em background...")
    try:
        result = data_processor.sync_data()
        print(f"Carga inicial concluída: {result}")
        # Recarrega os dados em memória após finalizar
        _load_data_from_db()
    except Exception as e:
        print(f"Erro na carga inicial em background: {e}")

def _initial_data_load():
    """Executa carga inicial dos dados (bootstrap)."""
    global _escopo, _entregas, _escopo_real, _kpis
    
    print("Inicializando banco de dados...")
    database.init_database()
    
    # Verifica se precisa executar carga inicial
    is_empty = database.is_database_empty()
    
    if is_empty:
        print("Banco vazio. Inicializando com dados temporários do Excel...")
        try:
            # Tenta carregar pelo menos o escopo do Excel para a UI não quebrar
            _escopo = data_processor.load_escopo()
            database.save_escopo(_escopo)
            _entregas = pd.DataFrame(columns=["task_id","projeto","grupo","hashtag","scope_slug","quantidade","data","mes_ano","mapeado"])
            database.save_entregas(_entregas)
            
            # Dispara a sincronização real pesada em background
            threading.Thread(target=_async_initial_sync, daemon=True).start()
        except Exception as e:
            print(f"Erro ao carregar Excel temporário: {e}")
    else:
        print("Banco já existe - carregando dados existentes...")
    
    # Carrega dados para memória (pode ser os temporários se acabou de inicializar)
    _load_data_from_db()
    
    if _escopo is None or _escopo.empty:
        print("AVISO: falha ao carregar dados — usando dados vazios.")
        _escopo = pd.DataFrame(columns=["grupo","entregavel","qtd_mes","qtd_ano","previsto_acumulado","slug"])
        _entregas = pd.DataFrame(columns=["task_id","projeto","grupo","hashtag","scope_slug","quantidade","data","mes_ano","mapeado"])
    
    _escopo_real = data_processor.escopo_com_realizado(_escopo, _entregas)
    _kpis = data_processor.compute_kpis(_escopo, _entregas)
    print("Dados carregados.")


def _start_scheduler():
    """Inicia o scheduler para sincronização automática."""
    global _scheduler
    
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            data_processor.sync_data,
            'cron',
            hour=0,
            minute=0,
            id='daily_sync',
            name='Sincronização diária'
        )
        _scheduler.start()
        print("Scheduler iniciado - sincronização diária às 00:00")
    except Exception as e:
        print(f"AVISO: não foi possível iniciar o scheduler: {e}")


def _filter(ini: str, fim: str, grupo: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna (escopo_filtrado, entregas_filtradas)."""
    ent = _entregas.copy()
    if not ent.empty:
        if ini:
            ent = ent[ent["data"] >= ini]
        if fim:
            ent = ent[ent["data"] <= fim]
        if grupo:
            ent = ent[ent["grupo"] == grupo]

    esc = _escopo[_escopo["grupo"] == grupo].copy() if grupo else _escopo.copy()
    return esc, ent


import queue_manager

# ==================== Rotas ====================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/queue/status")
def api_queue_status():
    """Retorna o status da fila de processamento."""
    return jsonify(queue_manager.get_queue_status())

@app.route("/api/queue/metrics")
def api_queue_metrics():
    """Retorna métricas da API para o dashboard."""
    return jsonify(queue_manager.get_queue_metrics())

@app.route("/debug")
def debug_page():
    """Página de debug."""
    if not data_processor.is_debug_mode():
        return "Modo debug desabilitado", 403
    return render_template("debug.html")


@app.route("/api/data")
def api_data():
    """Retorna dados do dashboard."""
    escopo_json = json.loads(_escopo_real.to_json(orient="records"))
    entregas_json = json.loads(_entregas.to_json(orient="records")) if not _entregas.empty else []
    grupos = sorted(_escopo["grupo"].dropna().unique().tolist())
    
    # Adiciona informações de meses/anos com dados
    meses_com_dados = data_processor.get_meses_com_dados()
    anos_com_dados = data_processor.get_anos_com_dados()
    
    return jsonify({
        "kpis": _kpis,
        "escopo": escopo_json,
        "entregas": entregas_json,
        "grupos": grupos,
        "meses_com_dados": meses_com_dados,
        "anos_com_dados": anos_com_dados,
    })


@app.route("/api/export")
def api_export():
    """Exporta dados para Excel."""
    esc, ent = _filter(
        request.args.get("ini", ""),
        request.args.get("fim", ""),
        request.args.get("grupo", ""),
    )
    esc_real = data_processor.escopo_com_realizado(esc, ent)
    kpis = data_processor.compute_kpis(esc, ent)
    xlsx = export.gerar_excel(esc_real, ent, kpis)
    return send_file(
        io.BytesIO(xlsx),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="nuclea_previsto_realizado.xlsx",
    )


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """Endpoint para sincronização manual (apenas em modo debug)."""
    if not data_processor.is_debug_mode():
        return jsonify({"status": "error", "error": "Modo debug desabilitado"}), 403
    
    try:
        result = data_processor.sync_data()
        
        # Recarrega dados em memória após sincronização
        if result.get("status") == "success":
            _load_data_from_db()
            
        # O data_processor.sync_data() já retorna um dict que podemos converter para JSON
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/debug/logs")
def api_debug_logs():
    """Retorna logs de debug."""
    if not data_processor.is_debug_mode():
        return jsonify({"error": "Modo debug desabilitado"}), 403
    
    limit = request.args.get("limit", 100, type=int)
    logs = database.get_debug_logs(limit)
    return jsonify(logs)


@app.route("/api/debug/ignored")
def api_debug_ignored():
    """Retorna itens ignorados."""
    if not data_processor.is_debug_mode():
        return jsonify({"error": "Modo debug desabilitado"}), 403
    
    limit = request.args.get("limit", 100, type=int)
    ignored = database.get_ignored_items(limit)
    return jsonify(ignored)


@app.route("/api/debug/clear", methods=["POST"])
def api_debug_clear():
    """Limpa logs de debug."""
    if not data_processor.is_debug_mode():
        return jsonify({"error": "Modo debug desabilitado"}), 403
    
    database.clear_debug_logs()
    data_processor.clear_debug_data()
    return jsonify({"status": "success"})


@app.route("/api/debug/status")
def api_debug_status():
    """Retorna status do debug e última sincronização."""
    if not data_processor.is_debug_mode():
        return jsonify({"enabled": False})
    
    last_sync = database.get_last_sync()
    return jsonify({
        "enabled": True,
        "last_sync": last_sync
    })


@app.route("/api/meses-com-dados")
def api_meses_com_dados():
    """Retorna meses que possuem dados processados."""
    meses = data_processor.get_meses_com_dados()
    return jsonify(meses)


@app.route("/api/anos-com-dados")
def api_anos_com_dados():
    """Retorna anos que possuem dados processados."""
    anos = data_processor.get_anos_com_dados()
    return jsonify(anos)


# ==================== Inicialização ====================

if __name__ == "__main__":
    # Carrega dados iniciais
    _initial_data_load()
    
    # Inicia o worker da fila (agora seguro após o banco inicializar)
    import api_client
    api_client.init_worker()
    
    # Inicia scheduler
    _start_scheduler()
    
    port = int(os.environ.get("PORT", 8050))
    app.run(debug=False, host="0.0.0.0", port=port)
