import os
import sqlite3
import json
from datetime import datetime
from typing import Optional
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("SQLITE_DB_PATH", "data/nuclea.db")


def get_connection() -> sqlite3.Connection:
    """Retorna conexão com o banco de dados."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Inicializa o banco de dados com as tabelas necessárias."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de escopo (do Excel)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS escopo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT,
            entregavel TEXT,
            qtd_mes INTEGER,
            qtd_ano INTEGER,
            previsto_acumulado INTEGER,
            slug TEXT UNIQUE
        )
    """)

    # Tabela de entregas (da API)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            projeto TEXT,
            grupo TEXT,
            hashtag TEXT,
            scope_slug TEXT,
            quantidade INTEGER,
            data TEXT,
            mes_ano TEXT,
            mapeado INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela de log de sincronização
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            records_fetched INTEGER,
            status TEXT,
            error_message TEXT
        )
    """)

    # Fila da API (Rate Limiting)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            params TEXT,
            priority INTEGER DEFAULT 3,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            next_attempt_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            error_log TEXT,
            result TEXT
        )
    """)

    # Lock Distribuído
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_locks (
            lock_key TEXT PRIMARY KEY,
            locked_at TIMESTAMP,
            locked_by TEXT,
            expires_at TIMESTAMP
        )
    """)

    # Métricas da API
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            endpoint TEXT,
            status_code INTEGER,
            duration_ms INTEGER,
            success INTEGER
        )
    """)

    # Tabela de debug log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debug_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            endpoint TEXT,
            params TEXT,
            status TEXT,
            duration_ms INTEGER,
            records_count INTEGER,
            ignored_reason TEXT
        )
    """)

    # Tabela de configuração
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Criar indexes para otimização
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entregas_data ON entregas(data)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entregas_mes_ano ON entregas(mes_ano)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entregas_grupo ON entregas(grupo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entregas_scope_slug ON entregas(scope_slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entregas_task_id ON entregas(task_id)")

    conn.commit()
    conn.close()


def database_exists() -> bool:
    """Verifica se o banco de dados existe."""
    return os.path.exists(DB_PATH)


def is_database_empty() -> bool:
    """Verifica se o banco não tem dados de escopo."""
    if not database_exists():
        return True
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM escopo")
    count = cursor.fetchone()[0]
    conn.close()
    return count == 0


# ==================== Operações de Escopo ====================

def save_escopo(escopo_df: pd.DataFrame):
    """Salva o escopo no banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    # Limpa tabela existente
    cursor.execute("DELETE FROM escopo")

    # Insere novos dados
    for _, row in escopo_df.iterrows():
        cursor.execute(
            "INSERT INTO escopo (grupo, entregavel, qtd_mes, qtd_ano, previsto_acumulado, slug) VALUES (?, ?, ?, ?, ?, ?)",
            (row.get("grupo"), row.get("entregavel"), row.get("qtd_mes"), row.get("qtd_ano"),
             row.get("previsto_acumulado"), row.get("slug"))
        )

    conn.commit()
    conn.close()
    print(f"Escopo salvo no banco: {len(escopo_df)} registros")


def load_escopo_from_db() -> pd.DataFrame:
    """Carrega o escopo do banco de dados."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM escopo", conn)
    conn.close()
    return df


# ==================== Operações de Entregas ====================

def save_entregas(entregas_df: pd.DataFrame):
    """Salva as entregas no banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    # Limpa tabela existente
    cursor.execute("DELETE FROM entregas")

    # Insere novos dados
    for _, row in entregas_df.iterrows():
        cursor.execute(
            """INSERT INTO entregas (task_id, projeto, grupo, hashtag, scope_slug, quantidade, data, mes_ano, mapeado)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("task_id"), row.get("projeto"), row.get("grupo"), row.get("hashtag"),
             row.get("scope_slug"), row.get("quantidade"), row.get("data"), row.get("mes_ano"),
             1 if row.get("mapeado") else 0)
        )

    conn.commit()
    conn.close()
    print(f"Entregas salvas no banco: {len(entregas_df)} registros")


def load_entregas_from_db() -> pd.DataFrame:
    """Carrega as entregas do banco de dados."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM entregas", conn)
    conn.close()
    # Converte coluna mapeado para booleano (SQLite retorna como int)
    if 'mapeado' in df.columns:
        df['mapeado'] = df['mapeado'].astype(bool)
    return df


def load_entregas_by_period(ini: str = None, fim: str = None, grupo: str = None) -> pd.DataFrame:
    """Carrega entregas filtradas por período e grupo."""
    conn = get_connection()
    query = "SELECT * FROM entregas WHERE 1=1"
    params = []

    if ini:
        query += " AND data >= ?"
        params.append(ini)
    if fim:
        query += " AND data <= ?"
        params.append(fim)
    if grupo:
        query += " AND grupo = ?"
        params.append(grupo)

    df = pd.read_sql_query(query, conn, params=params if params else None)
    conn.close()
    return df


def get_meses_com_dados() -> list[str]:
    """Retorna lista de meses (YYYY-MM) que possuem dados processados."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT mes_ano FROM entregas WHERE mes_ano IS NOT NULL AND mes_ano != '' ORDER BY mes_ano")
    meses = [row[0] for row in cursor.fetchall()]
    conn.close()
    return meses


def get_anos_com_dados() -> list[str]:
    """Retorna lista de anos que possuem dados processados."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT substr(data, 1, 4) as ano FROM entregas WHERE data IS NOT NULL AND data != '' ORDER BY ano DESC")
    anos = [row[0] for row in cursor.fetchall()]
    conn.close()
    return anos


# ==================== Operações de Sync Log ====================

def log_sync_start(sync_type: str) -> int:
    """Registra início de sincronização e retorna o ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sync_log (sync_type, started_at, status) VALUES (?, ?, 'running')",
        (sync_type, datetime.now().isoformat())
    )
    conn.commit()
    sync_id = cursor.lastrowid
    conn.close()
    return sync_id


def log_sync_complete(sync_id: int, records_fetched: int, status: str = "success", error_message: str = None):
    """Registra conclusão de sincronização."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE sync_log 
           SET completed_at = ?, records_fetched = ?, status = ?, error_message = ?
           WHERE id = ?""",
        (datetime.now().isoformat(), records_fetched, status, error_message, sync_id)
    )
    conn.commit()
    conn.close()


def get_last_sync() -> dict:
    """Retorna informações sobre a última sincronização."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}


# ==================== Operações de Debug Log ====================

def log_debug_request(endpoint: str, params: dict, status: str, duration_ms: int, records_count: int, ignored_reason: str = None):
    """Registra uma requisição no log de debug."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Certifica-se de que se o valor for numérico ou string, tentaremos convertê-lo em JSON
    # Mas se for dicionário, ele faz o dump sem problemas
    try:
        params_str = json.dumps(params, ensure_ascii=False)
    except (TypeError, ValueError):
        params_str = str(params)
        
    cursor.execute(
        """INSERT INTO debug_log (endpoint, params, status, duration_ms, records_count, ignored_reason)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (endpoint, params_str, status, duration_ms, records_count, ignored_reason)
    )
    conn.commit()
    conn.close()


def get_debug_logs(limit: int = 100) -> list[dict]:
    """Retorna os logs de debug mais recentes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM debug_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_ignored_items(limit: int = 100) -> list[dict]:
    """Retorna os itens ignorados mais recentes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM debug_log WHERE ignored_reason IS NOT NULL AND ignored_reason != '' ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def clear_debug_logs():
    """Limpa os logs de debug."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM debug_log")
    conn.commit()
    conn.close()


# ==================== Operações de Configuração ====================

def get_config(key: str, default: str = None) -> str:
    """Retorna valor de configuração."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default


def set_config(key: str, value: str):
    """Define valor de configuração."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# ==================== Queries Otimizadas ====================

def get_entregas_mensais(ano: str = None, mes: str = None) -> pd.DataFrame:
    """Retorna entregas filtradas por ano e mês específico."""
    conn = get_connection()
    query = "SELECT * FROM entregas WHERE 1=1"
    params = []

    if ano and mes:
        query += " AND mes_ano = ?"
        params.append(f"{ano}-{mes}")
    elif ano:
        query += " AND substr(data, 1, 4) = ?"
        params.append(ano)

    df = pd.read_sql_query(query, conn, params=params if params else None)
    conn.close()
    return df


def get_entregas_anuais(ano: str = None) -> pd.DataFrame:
    """Retorna entregas de um ano específico."""
    conn = get_connection()
    query = "SELECT * FROM entregas WHERE 1=1"
    params = []

    if ano:
        query += " AND substr(data, 1, 4) = ?"
        params.append(ano)

    df = pd.read_sql_query(query, conn, params=params if params else None)
    conn.close()
    return df


def get_agrupamento_mensal() -> pd.DataFrame:
    """Retorna agregação de entregas por mês."""
    conn = get_connection()
    query = """
        SELECT mes_ano, scope_slug, SUM(quantidade) as total
        FROM entregas
        WHERE mapeado = 1 AND scope_slug IS NOT NULL AND scope_slug != ''
        GROUP BY mes_ano, scope_slug
        ORDER BY mes_ano
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_agrupamento_por_entregavel() -> pd.DataFrame:
    """Retorna agregação de entregas por entregável."""
    conn = get_connection()
    query = """
        SELECT scope_slug, SUM(quantidade) as total
        FROM entregas
        WHERE mapeado = 1 AND scope_slug IS NOT NULL AND scope_slug != ''
        GROUP BY scope_slug
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df