import os
import time
import requests
from dotenv import load_dotenv
from config import API_BASE_URL, DATA_INICIO

load_dotenv()

_HEADERS = {
    "App-Key": os.getenv("APP_KEY"),
    "User-Token": os.getenv("USER_TOKEN"),
    "Content-Type": "application/json",
}

_REQUEST_INTERVAL = 0.7  # ~85 req/min, abaixo do limite de 100


def _get(endpoint: str, params: dict = None) -> list | dict:
    url = f"{API_BASE_URL}/{endpoint}"
    resp = requests.get(url, headers=_HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_paginated(endpoint: str, params: dict = None) -> list:
    params = params or {}
    params["limit"] = 100
    results = []
    page = 1
    while True:
        params["page"] = page
        data = _get(endpoint, params)
        if not data:
            break
        results.extend(data if isinstance(data, list) else [data])
        if len(data) < 100:
            break
        page += 1
        time.sleep(_REQUEST_INTERVAL)
    return results


def get_client_id(client_name: str) -> int | None:
    clients = _get_paginated("clients")
    for c in clients:
        if client_name.lower() in c.get("name", "").lower():
            return c["id"]
    return None


def get_gestao_tasks(client_id: int) -> list:
    """Retorna todas as tarefas 'Gestão de Atendimento' do cliente (abertas e fechadas)."""
    open_tasks   = _get_paginated("tasks", {"client_id": client_id})
    closed_tasks = _get_paginated("tasks", {"client_id": client_id, "is_closed": "true"})
    all_tasks = {t["id"]: t for t in open_tasks + closed_tasks}.values()
    return [
        t for t in all_tasks
        if "gest" in t.get("title", "").lower() and "atend" in t.get("title", "").lower()
    ]


def get_comments(task_id: int) -> list:
    """Retorna comentários humanos (não sistema) de uma tarefa."""
    comments = _get_paginated("comments", {"task_id": task_id})
    return [c for c in comments if not c.get("is_system_message", False)]
