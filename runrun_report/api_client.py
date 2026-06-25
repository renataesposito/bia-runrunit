import os
import requests
from dotenv import load_dotenv
from config import API_BASE_URL, DATA_INICIO
import queue_manager

load_dotenv()

_HEADERS = {
    "App-Key": os.getenv("APP_KEY"),
    "User-Token": os.getenv("USER_TOKEN"),
    "Content-Type": "application/json",
}

def init_worker():
    """Inicializa o worker da fila."""
    queue_manager.start_worker(_HEADERS)

FETCH_ALL_TASKS = os.getenv("FETCH_ALL_TASKS", "false").lower() == "true"


def _get(endpoint: str, params: dict = None, priority: int = 3) -> list | dict:
    """Submete a requisição à fila persistente e aguarda o resultado."""
    job_id = queue_manager.enqueue(endpoint, params, priority)
    
    # Aguarda o job finalizar (pode demorar devido ao rate limiting)
    results = queue_manager.wait_for_jobs([job_id])
    job_result = results.get(job_id)
    
    if job_result and job_result["status"] == "completed":
        return job_result["result"]
    elif job_result and job_result["status"] == "error":
        raise Exception(f"Erro na requisição da fila: {job_result['error_log']}")
    
    raise Exception("Timeout aguardando processamento da fila")


def _get_paginated(endpoint: str, params: dict = None, priority: int = 3) -> list:
    params = params or {}
    params["limit"] = 100
    results = []
    page = 1
    while True:
        params["page"] = page
        data = _get(endpoint, params, priority=priority)
        if not data:
            break
        results.extend(data if isinstance(data, list) else [data])
        if len(data) < 100:
            break
        page += 1
    return results


def get_client_id(client_name: str) -> int | None:
    clients = _get_paginated("clients", priority=1)
    for c in clients:
        if client_name.lower() in c.get("name", "").lower():
            return c["id"]
    return None


def get_gestao_tasks(client_id: int) -> list:
    """Retorna tarefas com prioridade 2"""
    if FETCH_ALL_TASKS:
        open_tasks   = _get_paginated("tasks", {"client_id": client_id}, priority=2)
        closed_tasks = _get_paginated("tasks", {"client_id": client_id, "is_closed": "true"}, priority=2)
        all_tasks = open_tasks + closed_tasks
    else:
        open_tasks   = _get_paginated("tasks", {"client_id": client_id}, priority=2)
        closed_tasks = _get_paginated("tasks", {"client_id": client_id, "is_closed": "true"}, priority=2)
        all_tasks = open_tasks + closed_tasks

    unique_tasks = {t["id"]: t for t in all_tasks}.values()

    if FETCH_ALL_TASKS:
        return list(unique_tasks)

    return [
        t for t in unique_tasks
        if str(t.get("title", "")).strip().endswith("- Gestão de Atendimento")
    ]


def get_comments(task_id: int) -> list:
    """Função legada para compatibilidade. Use get_comments_batch preferencialmente."""
    comments = _get_paginated("comments", {"task_id": task_id}, priority=3)
    return [c for c in comments if not c.get("is_system_message", False)]


def get_comments_batch(task_ids: list[int]) -> dict:
    """
    Enfileira a busca de comentários para múltiplas tarefas de uma vez.
    Retorna um dicionário {task_id: [comments]}
    """
    # Enfileira todos
    job_map = {}
    for tid in task_ids:
        # Nota: assumimos que comentários geralmente vêm em < 100 por tarefa,
        # para evitar complexidade de paginação em batch.
        jid = queue_manager.enqueue("comments", {"task_id": tid, "limit": 100}, priority=3)
        job_map[jid] = tid
        
    # Aguarda todos
    results = queue_manager.wait_for_jobs(list(job_map.keys()))
    
    final_data = {}
    for jid, tid in job_map.items():
        res = results.get(jid)
        if res and res["status"] == "completed" and res["result"] is not None:
            comments = res["result"]
            final_data[tid] = [c for c in comments if not c.get("is_system_message", False)]
        elif res and res["status"] == "error":
            raise Exception(f"Falha definitiva ao buscar comentários da tarefa {tid}: {res.get('error_log')}")
        else:
            final_data[tid] = []
            
    return final_data


def get_task_attachments_batch(task_ids: list[int]) -> dict:
    """
    Enfileira a busca de documentos (anexos) para múltiplas tarefas.
    Retorna um dicionário {task_id: [documents]}
    """
    job_map = {}
    for tid in task_ids:
        # A API correta para anexos é /documents?task_id={id}
        jid = queue_manager.enqueue("documents", {"task_id": tid, "limit": 100}, priority=3)
        job_map[jid] = tid
        
    results = queue_manager.wait_for_jobs(list(job_map.keys()))
    
    final_data = {}
    for jid, tid in job_map.items():
        res = results.get(jid)
        if res and res["status"] == "completed" and res["result"] is not None:
            final_data[tid] = res["result"]
        elif res and res["status"] == "error":
            print(f"Erro ao buscar anexos da task {tid}: {res.get('error_log')}")
            final_data[tid] = []
        else:
            final_data[tid] = []
            
    return final_data


def get_document_details_batch(doc_ids: list[int]) -> dict:
    """
    Busca os detalhes de múltiplos documentos para obter tags_data, etc.
    Retorna um dicionário {doc_id: document_data}
    """
    job_map = {}
    for did in doc_ids:
        jid = queue_manager.enqueue(f"documents/{did}", {}, priority=3)
        job_map[jid] = did
        
    results = queue_manager.wait_for_jobs(list(job_map.keys()))
    
    final_data = {}
    for jid, did in job_map.items():
        res = results.get(jid)
        if res and res["status"] == "completed" and res["result"] is not None:
            final_data[did] = res["result"]
        else:
            final_data[did] = None
            
    return final_data
