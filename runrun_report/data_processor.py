import re
import os
import unicodedata
import time
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv
import pandas as pd
from config import CLIENT_NAME, DATA_INICIO
import api_client
import database

load_dotenv()

EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Escopo Nuclea.xlsx")
TEMPO_CONTRATO_MESES = 12  # contrato anual: março a fevereiro
ESCOPO_NOME = "YESH HUB"   # nome do escopo/contrato (usado no header)

# Debug mode flag
DEBUG_MODE = os.getenv("DEBUG_MODE_ENABLED", "false").lower() == "true"

# Timezone GMT-3 (Brasília)
TZ_BRASIL = timezone(timedelta(hours=-3))

def to_brasilia_time(utc_str: str) -> str:
    """Converte string ISO UTC para data string em GMT-3 (Brasília)."""
    if not utc_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        dt_brasilia = dt.astimezone(TZ_BRASIL)
        return dt_brasilia.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return utc_str[:10] if utc_str else ""

# Lista global para armazenar logs de debug em memória (para sincronização rápida)
_debug_logs = []
_ignored_items = []


def _slug(text: str) -> str:
    """Normaliza: minúsculas, remove acentos, remove espaços."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", "", text)
    return text


def _meses_decorridos() -> float:
    hoje = date.today()
    delta = (hoje.year - DATA_INICIO.year) * 12 + (hoje.month - DATA_INICIO.month)
    return max(delta + hoje.day / 30, 0)


def load_escopo() -> pd.DataFrame:
    """Lê a aba PROD do Excel e calcula previsto acumulado."""
    df = pd.read_excel(EXCEL_PATH, sheet_name="PROD")
    df = df.iloc[:, 1:]  # descarta coluna de índice vazia
    df.columns = ["grupo", "entregavel", "qtd_mes", "qtd_ano"]
    df = df.dropna(subset=["entregavel"]).copy()
    df["qtd_mes"] = pd.to_numeric(df["qtd_mes"], errors="coerce").fillna(0)
    df["qtd_ano"] = pd.to_numeric(df["qtd_ano"], errors="coerce").fillna(0)
    df = df[(df["qtd_mes"] > 0) | (df["qtd_ano"] > 0)]  # remove linhas de cabeçalho ou vazias

    meses = _meses_decorridos()
    df["previsto_acumulado"] = df.apply(
        lambda r: round(r["qtd_mes"] * meses) if r["qtd_mes"] > 0
                  else round(r["qtd_ano"] * meses / 12),
        axis=1,
    ).astype(int)
    df["slug"] = df["entregavel"].apply(_slug)
    return df.reset_index(drop=True)


def _parse_hashtags(text: str) -> list[tuple[str, int]]:
    """
    Extrai [(slug, quantidade)] de um texto de comentário.
    Ex.: '#e-mailsdeconvitenucleasday2' → [('e-mailsdeconvitenucleasday', 2)]
    """
    results = []
    for token in re.findall(r"#([^\s#]+)", text):
        m = re.match(r"^(.*\D)(\d+)$", token)
        if m:
            results.append((_slug(m.group(1)), int(m.group(2))))
    return results


def _match_tag(tag_slug: str, grupo: str, escopo: pd.DataFrame) -> str | None:
    """
    Casa um slug de tag com um item do escopo (busca em todo o escopo, sem restrição de grupo).
    Primeiro tenta match exato, depois verifica se o slug do entregável
    é substring do slug da tag (para suportar prefixos como 'n_', 'ep_', etc.).
    """
    # 1. Match exato
    exact = escopo[escopo["slug"] == tag_slug]
    if len(exact) == 1:
        return exact.iloc[0]["slug"]

    # 2. Slug do entregável é substring do slug da tag (tag tem prefixo extra)
    candidates = escopo[escopo["slug"].apply(lambda s: len(s) > 4 and s in tag_slug)]
    if len(candidates) == 1:
        return candidates.iloc[0]["slug"]

    return None


def load_entregas(escopo: pd.DataFrame) -> pd.DataFrame:
    """
    Busca as tarefas de Gestão de Atendimento do cliente, lê os comentários
    e extrai as entregas registradas via hashtag (#entregávelN).
    """
    import time
    
    # Limpa dados de debug anteriores
    clear_debug_data()
    
    print("Buscando cliente " + CLIENT_NAME + "...")
    start = time.time()
    client_id = api_client.get_client_id(CLIENT_NAME)
    duration = int((time.time() - start) * 1000)
    
    if not client_id:
        raise ValueError("Cliente '" + CLIENT_NAME + "' não encontrado na API.")
    
    log_api_request("clients", {"name": CLIENT_NAME}, "success", duration, 1)

    print("Buscando tarefas de Gestão de Atendimento...")
    start = time.time()
    gestao_tasks = api_client.get_gestao_tasks(client_id)
    duration = int((time.time() - start) * 1000)
    print(str(len(gestao_tasks)) + " tarefas de Gestão encontradas.")
    log_api_request("tasks", {"client_id": client_id}, "success", duration, len(gestao_tasks))

    rows = []
    ignored_count = 0
    
    for task in gestao_tasks:
        task_tags = task.get("task_tags") or []
        if isinstance(task_tags, str):
            task_tags = [task_tags] if task_tags else []

        grupo = (task.get("project_group_name") or "").strip()

        # Monta {tag_slug → scope_slug} para esta tarefa
        tag_map: dict[str, str | None] = {}
        for raw_tag in task_tags:
            ts = _slug(raw_tag)
            tag_map[ts] = _match_tag(ts, grupo, escopo)

        task_id = task["id"]
        
        # Log da requisição de comentários
        start = time.time()
        comments = api_client.get_comments(task_id)
        duration = int((time.time() - start) * 1000)
        log_api_request(f"comments/task_{task_id}", {}, "success", duration, len(comments))

        for comment in comments:
            data_str = to_brasilia_time(comment.get("created_at") or "")
            text = comment.get("text") or ""
            
            hashtags_found = _parse_hashtags(text)
            
            if not hashtags_found:
                has_valid_tag = any(v for v in tag_map.values())
                if has_valid_tag:
                    task_title = task.get("title") or ""
                    if DEBUG_MODE:
                        add_ignored_item("task", str(task_id), f"Tarefa '{task_title}' tem tags mapeadas mas comentário sem quantidade")
                else:
                    if DEBUG_MODE:
                        add_ignored_item("comment", str(comment.get("id")), "Comentário sem hashtag de entrega")
                ignored_count += 1
                continue

            for comment_slug, qty in hashtags_found:
                scope_slug = (
                    tag_map.get(comment_slug)
                    or _match_tag(comment_slug, grupo, escopo)
                )
                
                if not scope_slug:
                    if DEBUG_MODE:
                        add_ignored_item("hashtag", comment_slug, f"Hashtag '#{comment_slug}' não mapeada ao escopo")
                    ignored_count += 1
                
                rows.append({
                    "task_id":    task_id,
                    "projeto":    (task.get("project_name") or task.get("title") or "").strip(),
                    "grupo":      grupo,
                    "hashtag":    comment_slug,
                    "scope_slug": scope_slug or "",
                    "quantidade": qty,
                    "data":       data_str,
                    "mes_ano":    data_str[:7],
                    "mapeado":    bool(scope_slug),
                })

    _COLS = ["task_id", "projeto", "grupo", "hashtag", "scope_slug",
             "quantidade", "data", "mes_ano", "mapeado"]
    
    print(f"Total: {len(rows)} entregas processadas, {ignored_count} itens ignorados")
    
    return pd.DataFrame(rows, columns=_COLS) if rows else pd.DataFrame(columns=_COLS)


def escopo_com_realizado(escopo: pd.DataFrame, entregas: pd.DataFrame) -> pd.DataFrame:
    """Junta escopo com total realizado por item."""
    df = escopo.copy()
    if not entregas.empty:
        totals = (
            entregas[entregas["mapeado"]]
            .groupby("scope_slug")["quantidade"]
            .sum()
        )
        df["realizado"] = df["slug"].map(totals).fillna(0).astype(int)
    else:
        df["realizado"] = 0
    return df


def compute_kpis(escopo: pd.DataFrame, entregas: pd.DataFrame) -> dict:
    total_previsto = int(escopo["previsto_acumulado"].sum())
    total_realizado = int(entregas.loc[entregas["mapeado"], "quantidade"].sum()) if not entregas.empty else 0
    total_contrato = int(escopo["qtd_ano"].sum()) if not escopo.empty else 0
    saldo_escopo = total_contrato - total_realizado
    pct = round(100 * total_realizado / total_previsto, 1) if total_previsto else 0
    return {
        "total_previsto":       total_previsto,
        "total_realizado":      total_realizado,
        "total_contrato":      total_contrato,
        "saldo_escopo":         saldo_escopo,
        "pct_realizacao":       pct,
        "meses_decorridos":      round(_meses_decorridos(), 1),
        "tempo_contrato_meses": TEMPO_CONTRATO_MESES,
        "escopo_nome":          ESCOPO_NOME,
    }


# ==================== Funções de Debug ====================

def log_api_request(endpoint: str, params: dict, status: str, duration_ms: int, records_count: int, ignored_reason: str = None):
    """Registra uma requisição à API no log de debug."""
    global _debug_logs
    
    log_entry = {
        "endpoint": endpoint,
        "params": params,
        "status": status,
        "duration_ms": duration_ms,
        "records_count": records_count,
        "ignored_reason": ignored_reason,
    }
    _debug_logs.append(log_entry)
    
    # Se debug mode estiver ativo, salva no banco também
    if DEBUG_MODE:
        database.log_debug_request(endpoint, params, status, duration_ms, records_count, ignored_reason)


def add_ignored_item(item_type: str, item_id: str, reason: str):
    """Adiciona um item ignorado à lista."""
    global _ignored_items
    
    ignored_entry = {
        "type": item_type,
        "id": item_id,
        "reason": reason,
    }
    _ignored_items.append(ignored_entry)
    
    if DEBUG_MODE:
        database.log_debug_request(
            endpoint=f"ignored_{item_type}",
            params={"id": item_id},
            status="ignored",
            duration_ms=0,
            records_count=0,
            ignored_reason=reason
        )


def get_debug_logs() -> list:
    """Retorna os logs de debug."""
    return _debug_logs


def get_ignored_items() -> list:
    """Retorna os itens ignorados."""
    return _ignored_items


def clear_debug_data():
    """Limpa os dados de debug em memória."""
    global _debug_logs, _ignored_items
    _debug_logs = []
    _ignored_items = []


def is_debug_mode() -> bool:
    """Retorna se o modo debug está ativo."""
    return DEBUG_MODE


# ==================== Funções de Sincronização ====================

def sync_data() -> dict:
    """
    Executa sincronização completa dos dados da API.
    Retorna dict com status e informações da sincronização.
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    sync_id = database.log_sync_start("full_sync")
    start_time = time.time()
    
    try:
        # Carrega escopo do Excel
        print("Carregando escopo do Excel...")
        escopo = load_escopo()
        database.save_escopo(escopo)
        
        # Carrega entregas da API
        print("Carregando entregas da API...")
        entregas = load_entregas(escopo)
        database.save_entregas(entregas)
        
        duration = time.time() - start_time
        records_count = len(entregas)
        
        database.log_sync_complete(sync_id, records_count, "success")
        
        return {
            "status": "success",
            "sync_id": sync_id,
            "records_fetched": records_count,
            "duration_seconds": round(duration, 2),
            "message": f"Sincronização concluída: {records_count} registros"
        }
        
    except Exception as e:
        duration = time.time() - start_time
        database.log_sync_complete(sync_id, 0, "error", str(e))
        
        return {
            "status": "error",
            "sync_id": sync_id,
            "error": str(e),
            "duration_seconds": round(duration, 2),
            "message": f"Erro na sincronização: {str(e)}"
        }


def get_meses_com_dados() -> list[str]:
    """Retorna lista de meses que possuem dados processados."""
    return database.get_meses_com_dados()


def get_anos_com_dados() -> list[str]:
    """Retorna lista de anos que possuem dados processados."""
    return database.get_anos_com_dados()
