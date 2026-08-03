import io
import json
import os
from datetime import date
from flask import Flask, render_template, jsonify, request, send_file, Response
from functools import wraps
from flask_cors import CORS
from dotenv import load_dotenv
import pandas as pd
import data_processor
import export
import database
import thumbnail_manager

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
    
    # Gera snapshots CTD se não existirem
    data_processor.generate_historical_snapshots(_escopo, _entregas)
    
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
        _scheduler.add_job(
            thumbnail_manager.sync_all_thumbnails,
            'cron',
            hour=2,
            minute=0,
            id='daily_thumbnails_sync',
            name='Sincronização de thumbnails'
        )
        _scheduler.start()
        print("Scheduler iniciado - sincronização diária às 00:00 e thumbnails às 02:00")
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

# ==================== Autenticação Debug ====================

def check_auth(username, password):
    """Verifica se o usuário e senha estão corretos."""
    return password == 'nuclea123' # Senha básica conforme solicitado

def authenticate():
    """Retorna uma resposta 401 que solicita autenticação básica."""
    return Response(
    'Acesso restrito. Por favor, insira a senha.', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# ==================== Rotas ====================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ctd")
def ctd_page():
    return render_template("ctd.html")

@app.route("/api/queue/status")
def api_queue_status():
    """Retorna o status da fila de processamento."""
    return jsonify(queue_manager.get_queue_status())

@app.route("/api/queue/metrics")
def api_queue_metrics():
    """Retorna métricas da API para o dashboard."""
    return jsonify(queue_manager.get_queue_metrics())

@app.route("/debug")
@requires_auth
def debug_page():
    """Página de debug."""
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
    
    # Dados CTD
    ctd_data = data_processor.compute_ctd_viability(_escopo_real)
    ctd_snapshots = database.get_health_snapshots()

    # Novos dados auxiliares CTD
    sla_violations = data_processor.compute_sla_violations(_entregas, _escopo)
    monthly_velocity = data_processor.compute_monthly_velocity(_entregas)
    delivery_meta = data_processor.compute_delivery_meta(
        ctd_data.get("saude", {}),
        _kpis.get("total_contrato", 0),
        _kpis.get("total_realizado", 0),
    )

    return jsonify({
        "kpis": _kpis,
        "escopo": escopo_json,
        "entregas": entregas_json,
        "grupos": grupos,
        "meses_com_dados": meses_com_dados,
        "anos_com_dados": anos_com_dados,
        "ctd": ctd_data,
        "ctd_snapshots": ctd_snapshots,
        "ctd_aux": {
            "sla_violations": sla_violations,
            "monthly_velocity": monthly_velocity,
            "delivery_meta": delivery_meta,
        },
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


@app.route("/api/pdf-report")
# Removido o @requires_auth para permitir acesso via blob/fetch no frontend sem precisar embutir os headers na requisição.
# Ou então precisamos embutir as credenciais na chamada fetch. A remoção simplifica o fluxo na mesma sessão.
def api_pdf_report():
    """Gera e retorna o relatório de status em PDF."""
    mes_ano = request.args.get("mes_ano")
    if not mes_ano:
        return jsonify({"status": "error", "error": "Parâmetro mes_ano é obrigatório."}), 400
        
    try:
        import pdf_generator
        pdf_bytes = pdf_generator.gerar_pdf_status(mes_ano, _escopo, _entregas)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"Relatorio_Status_Nuclea_{mes_ano.replace('/', '-')}.pdf"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/sync", methods=["POST"])
@requires_auth
def api_sync():
    """Endpoint para sincronização manual."""
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


@app.route("/api/sync/progress")
@requires_auth
def api_sync_progress():
    """Retorna o progresso atual da sincronização (passo 0..5 de 5)."""
    return jsonify(data_processor.get_sync_progress())


@app.route("/api/debug/ignored")
@requires_auth
def api_debug_ignored():
    """Retorna itens ignorados, filtrando ignored_comment se solicitado."""
    limit = request.args.get("limit", 100, type=int)
    ignored = database.get_ignored_items(limit)
    
    # Filtra logs de ignored_comment conforme solicitado pelo usuário
    # para evitar verbosidade excessiva no log de requisições à API
    # (Embora aqui seja a tabela de ignorados, a regra se aplica ao log principal)
    return jsonify(ignored)


@app.route("/api/debug/orphan-tasks")
@requires_auth
def api_debug_orphan_tasks():
    """Retorna tasks que têm entregas no dashboard mas não têm arquivos com tags aprovado/aguardando."""
    try:
        # Carrega dados do banco
        entregas = database.load_entregas_from_db()
        anexos = database.load_all_anexos()
        
        # Agrupa anexos por task_id e verifica tags
        def has_valid_file_tags(a_list):
            for a in a_list:
                tags_data = a.get("tags_data")
                if isinstance(tags_data, list):
                    names = [str(t.get("name", "")).lower() for t in tags_data]
                    if any(x in names for x in ["aprovado", "aprovada", "aguardando_aprovacao", "aguardando aprovação"]):
                        return True
            return False

        anexos_por_task = {}
        for a in anexos:
            tid = a.get("task_id")
            if tid not in anexos_por_task: anexos_por_task[tid] = []
            anexos_por_task[tid].append(a)
            
        # Filtra tasks das entregas (dashboard) que não têm anexos válidos
        orphan_tasks = []
        if not entregas.empty:
            # Pega tasks únicas que estão no dashboard (mapeadas)
            dashboard_tasks = entregas[entregas["mapeado"] == True].drop_duplicates(subset=["task_id"])
            
            for _, row in dashboard_tasks.iterrows():
                tid = row["task_id"]
                task_anexos = anexos_por_task.get(tid, [])
                
                if not task_anexos or not has_valid_file_tags(task_anexos):
                    orphan_tasks.append({
                        "task_id": tid,
                        "projeto": row["projeto"],
                        "grupo": row["grupo"],
                        "data_entrega": row["data"]
                    })
                    
        return jsonify(sorted(orphan_tasks, key=lambda x: x["data_entrega"], reverse=True))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/debug/orphan-tag-tasks")
@requires_auth
def api_debug_orphan_tag_tasks():
    """
    Retorna tasks que têm tag(s) mas nenhum comentário registrou quantidade (#slugN).
    Para cada task, inclui todos os comentários e o status de cada tag
    (preenchida = aparece em algum comentário como hashtag).
    """
    try:
        import re as _re
        tasks = database.load_tasks()
        comments_by_task = database.load_comments_by_task()
        result = []

        for t in tasks:
            tags = [str(x).strip() for x in t.get("tags", []) if str(x).strip()]
            if not tags:
                continue
            task_id = t["task_id"]
            comments = comments_by_task.get(task_id, [])

            comment_infos = []
            for c in comments:
                text = c.get("text") or ""
                qty_hashtags = data_processor._parse_hashtags(text)
                plain_hashtags = _re.findall(r"#([^\s#]+)", text.replace("&nbsp;", " "))
                comment_infos.append({
                    "id": c.get("id"),
                    "data": data_processor.to_brasilia_time(c.get("created_at") or ""),
                    "texto": text,
                    "user_email": c.get("user_email") or "",
                    "has_quantidade": bool(qty_hashtags),
                    "hashtags": [h for h in plain_hashtags],
                })

            # Órfã de quantidade: tem tag mas nenhum comentário traz hashtag com número
            if any(ci["has_quantidade"] for ci in comment_infos):
                continue

            # Marca cada tag: preenchida se aparece como hashtag em algum comentário
            tags_status = []
            for tg in tags:
                tslug = data_processor._slug(tg)
                preenchida = False
                for ci in comment_infos:
                    for h in ci["hashtags"]:
                        hs = data_processor._slug(h)
                        if hs and (hs == tslug or (tslug and hs.startswith(tslug) and hs[len(tslug):].isdigit())):
                            preenchida = True
                            break
                    if preenchida:
                        break
                tags_status.append({"tag": tg, "preenchida": preenchida})

            result.append({
                "task_id": task_id,
                "title": t.get("title") or "",
                "projeto": t.get("project_name") or "",
                "grupo": t.get("project_group_name") or "",
                "tags": tags_status,
                "comments": comment_infos,
            })

        result.sort(key=lambda x: (x["grupo"] or "", x["title"] or ""))
        return jsonify({"count": len(result), "tasks": result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/debug/logs")
@requires_auth
def api_debug_logs():
    """Retorna logs de debug, filtrando ignored_comment."""
    limit = request.args.get("limit", 100, type=int)
    logs = database.get_debug_logs(limit)
    
    # Filtra tudo o que for "ignored_comment" no log de requisições
    filtered_logs = [log for log in logs if log.get("endpoint") != "ignored_comment"]
    
    return jsonify(filtered_logs)


@app.route("/api/debug/clear", methods=["POST"])
@requires_auth
def api_debug_clear():
    """Limpa logs de debug."""
    database.clear_debug_logs()
    data_processor.clear_debug_data()
    return jsonify({"status": "success"})


@app.route("/api/debug/status")
def api_debug_status():
    """Retorna status do debug e última sincronização."""
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
