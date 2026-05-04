import threading
import json
import time
import requests
from datetime import datetime, timedelta, timezone
import os
import database
from config import API_BASE_URL

# Configurações do Rate Limiting e Fila
MAX_REQ_PER_MIN = 30
SLIDING_WINDOW_SEC = 60
MAX_RETRIES = 5
RETRY_DELAYS = [2, 5, 10, 30, 60]  # Segundos

_worker_thread = None
_worker_running = False

def start_worker(headers: dict):
    """Inicia a thread do worker que processará a fila em background."""
    global _worker_thread, _worker_running
    if _worker_thread is not None and _worker_thread.is_alive():
        return
        
    _worker_running = True
    _worker_thread = threading.Thread(target=_worker_loop, args=(headers,), daemon=True)
    _worker_thread.start()
    print("Queue worker iniciado com sucesso.")

def stop_worker():
    global _worker_running
    _worker_running = False

def _worker_loop(headers: dict):
    """Loop contínuo do worker da fila."""
    while _worker_running:
        try:
            processed = process_next_job(headers)
            if not processed:
                # Fila vazia ou rate limit atingido
                time.sleep(1)
        except Exception as e:
            print(f"Erro no worker loop: {e}")
            time.sleep(5)

def enqueue(endpoint: str, params: dict = None, priority: int = 3) -> int:
    """Adiciona um job na fila e retorna o ID."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO api_queue (endpoint, params, priority, status)
           VALUES (?, ?, ?, 'pending')""",
        (endpoint, json.dumps(params or {}), priority)
    )
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id

def get_job(job_id: int) -> dict:
    """Retorna o estado e resultado de um job específico."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_queue WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def wait_for_jobs(job_ids: list, timeout_sec: int = 3600) -> dict:
    """Aguarda até que todos os jobs da lista sejam concluídos ou deem erro."""
    start_time = time.time()
    results = {}
    
    while True:
        if time.time() - start_time > timeout_sec:
            break
            
        conn = database.get_connection()
        cursor = conn.cursor()
        
        # Cria a string de parâmetros ( ?, ?, ? )
        placeholders = ','.join(['?'] * len(job_ids))
        cursor.execute(f"SELECT id, status, result, error_log FROM api_queue WHERE id IN ({placeholders})", job_ids)
        rows = cursor.fetchall()
        conn.close()
        
        all_done = True
        for r in rows:
            if r["status"] in ('pending', 'processing'):
                all_done = False
                break
                
        if all_done:
            for r in rows:
                results[r["id"]] = {
                    "status": r["status"],
                    "result": json.loads(r["result"]) if r["result"] else None,
                    "error_log": r["error_log"]
                }
            return results
            
        time.sleep(2)
        
    return results

def get_queue_status() -> dict:
    """Retorna status atual da fila."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM api_queue
    """)
    row = cursor.fetchone()
    conn.close()
    return {
        "pending": row["pending"] or 0,
        "processing": row["processing"] or 0,
        "errors": row["errors"] or 0,
        "completed": row["completed"] or 0
    }

def get_queue_metrics() -> dict:
    """Retorna métricas da API (dashboard)."""
    conn = database.get_connection()
    cursor = conn.cursor()
    # Usamos utcnow formatado pois o CURRENT_TIMESTAMP do SQLite armazena em UTC no formato YYYY-MM-DD HH:MM:SS
    sixty_secs_ago = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Reqs por minuto
    cursor.execute("SELECT COUNT(*) as count FROM api_metrics WHERE timestamp >= ?", (sixty_secs_ago,))
    reqs_min = cursor.fetchone()["count"] or 0
    
    # Taxa de sucesso geral e tempo médio
    cursor.execute("""
        SELECT 
            AVG(duration_ms) as avg_time,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
            COUNT(*) as total
        FROM api_metrics
    """)
    row = cursor.fetchone()
    
    avg_time = int(row["avg_time"]) if row["avg_time"] else 0
    total = row["total"] or 0
    successes = row["successes"] or 0
    success_rate = round((successes / total * 100) if total > 0 else 100, 1)
    
    conn.close()
    return {
        "reqs_per_minute": reqs_min,
        "avg_duration_ms": avg_time,
        "success_rate_pct": success_rate,
        "total_requests": total
    }

def clear_queue():
    """Limpa a fila de processamento."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_queue")
    conn.commit()
    conn.close()

def _check_rate_limit(conn) -> bool:
    """
    Verifica se atingimos o limite de requisições na janela deslizante.
    Retorna True se PODE executar, False se DEVE aguardar.
    """
    cursor = conn.cursor()
    # Usamos o formato YYYY-MM-DD HH:MM:SS em UTC para comparar com o CURRENT_TIMESTAMP do SQLite
    sixty_secs_ago = (datetime.now(timezone.utc) - timedelta(seconds=SLIDING_WINDOW_SEC)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "SELECT COUNT(*) as count FROM api_metrics WHERE timestamp >= ?",
        (sixty_secs_ago,)
    )
    row = cursor.fetchone()
    return (row["count"] or 0) < MAX_REQ_PER_MIN

def _log_metric(conn, endpoint: str, status_code: int, duration_ms: int, success: bool):
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO api_metrics (endpoint, status_code, duration_ms, success)
           VALUES (?, ?, ?, ?)""",
        (endpoint, status_code, duration_ms, 1 if success else 0)
    )
    conn.commit()

def acquire_lock(lock_key: str, expires_in_sec: int = 300) -> bool:
    """Tenta adquirir um lock distribuído no banco."""
    conn = database.get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    
    # Limpa locks expirados
    cursor.execute("DELETE FROM system_locks WHERE expires_at < ?", (now.isoformat(),))
    conn.commit()
    
    try:
        cursor.execute(
            """INSERT INTO system_locks (lock_key, locked_at, expires_at)
               VALUES (?, ?, ?)""",
            (lock_key, now.isoformat(), (now + timedelta(seconds=expires_in_sec)).isoformat())
        )
        conn.commit()
        success = True
    except Exception:
        # Já existe um lock ativo
        success = False
    
    conn.close()
    return success

def release_lock(lock_key: str):
    """Libera um lock distribuído."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM system_locks WHERE lock_key = ?", (lock_key,))
    conn.commit()
    conn.close()

def process_next_job(headers: dict) -> bool:
    """
    Pega o próximo job na fila e o executa.
    Retorna True se processou algo, False se a fila está vazia ou bloqueada pelo rate limit.
    """
    conn = database.get_connection()
    
    # Verifica rate limit antes de iniciar
    if not _check_rate_limit(conn):
        conn.close()
        return False
        
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    # Busca o job pendente de maior prioridade (priority 1 > priority 3)
    # Considera next_attempt_at para os retries
    cursor.execute("""
        SELECT * FROM api_queue 
        WHERE status = 'pending' 
          AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
        ORDER BY priority ASC, created_at ASC
        LIMIT 1
    """, (now,))
    
    job = cursor.fetchone()
    if not job:
        conn.close()
        return False
        
    job_id = job["id"]
    endpoint = job["endpoint"]
    params = json.loads(job["params"])
    attempts = job["attempts"]
    
    # Marca como processing
    cursor.execute("UPDATE api_queue SET status = 'processing' WHERE id = ?", (job_id,))
    conn.commit()
    
    url = f"{API_BASE_URL}/{endpoint}"
    start_time = time.time()
    status_code = 0
    success = False
    error_msg = ""
    result_data = None
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        status_code = resp.status_code
        resp.raise_for_status()
        result_data = resp.json()
        success = True
    except requests.exceptions.RequestException as e:
        if resp is not None:
            status_code = resp.status_code
        error_msg = str(e)
        success = False
        
    duration_ms = int((time.time() - start_time) * 1000)
    
    # Log da métrica (conta pro rate limit)
    _log_metric(conn, endpoint, status_code, duration_ms, success)
    
    # Atualiza o job
    if success:
        cursor.execute(
            """UPDATE api_queue 
               SET status = 'completed', processed_at = ?, result = ?
               WHERE id = ?""",
            (datetime.now().isoformat(), json.dumps(result_data), job_id)
        )
    else:
        attempts += 1
        if attempts >= MAX_RETRIES:
            cursor.execute(
                """UPDATE api_queue 
                   SET status = 'error', processed_at = ?, error_log = ?
                   WHERE id = ?""",
                (datetime.now().isoformat(), error_msg, job_id)
            )
        else:
            # Configura retry
            delay = RETRY_DELAYS[attempts - 1]
            # Adaptive throttling: se for 429, backoff mais agressivo
            if status_code == 429:
                delay += 10
                
            next_attempt = (datetime.now() + timedelta(seconds=delay)).isoformat()
            cursor.execute(
                """UPDATE api_queue 
                   SET status = 'pending', attempts = ?, next_attempt_at = ?, error_log = ?
                   WHERE id = ?""",
                (attempts, next_attempt, error_msg, job_id)
            )
            
    conn.commit()
    conn.close()
    return True
