import re
import os
import unicodedata
import time
import difflib
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv
import pandas as pd
from config import CLIENT_NAME, DATA_INICIO, ALLOWED_DATE_OVERRIDE_EMAILS
import api_client
import database

load_dotenv()

EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Escopo Nuclea.xlsx")
TEMPO_CONTRATO_MESES = 12  # contrato anual: março a fevereiro
ESCOPO_NOME = "YESH HUB"   # nome do escopo/contrato (usado no header)

# Debug mode flag - Sempre ativo por padrão
DEBUG_MODE = True

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
    1. Tenta match exato.
    2. Verifica se o slug do entregável é substring do slug da tag (prefixos).
    3. Tenta match por similaridade de grafia (fuzzy) >= 92%.
    """
    # 1. Match exato
    exact = escopo[escopo["slug"] == tag_slug]
    if len(exact) == 1:
        return exact.iloc[0]["slug"]

    # 2. Slug do entregável é substring do slug da tag (tag tem prefixo extra)
    candidates = escopo[escopo["slug"].apply(lambda s: len(s) > 4 and s in tag_slug)]
    if len(candidates) == 1:
        return candidates.iloc[0]["slug"]

    # 3. Tratamento de prefixos comuns (ex: n_, ep_)
    # Remove prefixos conhecidos antes de calcular a similaridade para melhorar o match
    clean_tag = tag_slug
    for prefix in ['n_', 'ep_']:
        if clean_tag.startswith(prefix):
            clean_tag = clean_tag[len(prefix):]
            break
            
    # Remove hífens para comparar apenas as letras
    clean_tag_no_hyphen = clean_tag.replace('-', '')
            
    # 4. Match por similaridade de grafia (>= 92%)
    best_match = None
    best_ratio = 0.0
    
    for scope_slug in escopo["slug"].unique():
        if not scope_slug:
            continue
            
        clean_scope = scope_slug.replace('-', '')
        
        # Tenta a similaridade com a tag original e com a tag sem prefixo/hífen
        ratio1 = difflib.SequenceMatcher(None, tag_slug, scope_slug).ratio()
        ratio2 = difflib.SequenceMatcher(None, clean_tag_no_hyphen, clean_scope).ratio()
        
        ratio = max(ratio1, ratio2)
        
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = scope_slug
            
    if best_ratio >= 0.92 and best_match:
        return best_match

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
    
    # Buscamos os comentários em lote usando a nova fila centralizada
    print(f"Enfileirando busca de comentários para {len(gestao_tasks)} tarefas...")
    task_ids = [t["id"] for t in gestao_tasks]
    start = time.time()
    all_comments = api_client.get_comments_batch(task_ids)
    duration = int((time.time() - start) * 1000)
    log_api_request("comments_batch", {"task_count": len(task_ids)}, "success", duration, sum(len(c) for c in all_comments.values()))
    
    print(f"Enfileirando busca de anexos para {len(gestao_tasks)} tarefas...")
    start = time.time()
    all_task_attachments = api_client.get_task_attachments_batch(task_ids)
    duration = int((time.time() - start) * 1000)
    log_api_request("documents_batch", {"task_count": len(task_ids)}, "success", duration, sum(len(a) for a in all_task_attachments.values()))

    # Coleta todos os IDs de documentos encontrados para buscar detalhes (tags_data)
    doc_ids_to_fetch = set()
    temp_anexos = []
    for tid in task_ids:
        for a in all_task_attachments.get(tid, []):
            if "id" in a:
                doc_ids_to_fetch.add(a["id"])
                a["task_id"] = tid
                temp_anexos.append(a)
        for c in all_comments.get(tid, []):
            c_attachments = c.get("attachments", []) or c.get("documents", [])
            for a in c_attachments:
                if "id" in a:
                    doc_ids_to_fetch.add(a["id"])
                    a["task_id"] = tid
                    temp_anexos.append(a)

    print(f"Buscando detalhes de {len(doc_ids_to_fetch)} documentos para obter tags...")
    start = time.time()
    doc_details = api_client.get_document_details_batch(list(doc_ids_to_fetch))
    duration = int((time.time() - start) * 1000)
    log_api_request("document_details_batch", {"doc_count": len(doc_ids_to_fetch)}, "success", duration, len(doc_details))

    # Processamento de todos os anexos para salvar no banco
    anexos_unicos = {}
    
    def get_relevant_tag(anexo):
        # Tags de interesse em ordem de prioridade
        targets = ["aprovado", "aguardando_aprovacao", "correcao"]
        tags_data = anexo.get("tags_data")
        if isinstance(tags_data, list):
            tag_names = [str(t.get("name", "")).lower() for t in tags_data]
            for target in targets:
                if target in tag_names:
                    return target
            # Se tiver outras tags mas não as prioritárias, retorna a primeira
            if tag_names:
                return tag_names[0]
        return None

    for a in temp_anexos:
        did = a["id"]
        detail = doc_details.get(did)
        if detail:
            a.update(detail)
            # Salva apenas se tiver alguma tag (critério para o relatório)
            if get_relevant_tag(a):
                anexos_unicos[did] = a
                    
    database.save_anexos(list(anexos_unicos.values()))
    
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
        
        comments = all_comments.get(task_id, [])

        for comment in comments:
            data_str = to_brasilia_time(comment.get("created_at") or "")
            text = comment.get("text") or ""
            
            # Remove entidades HTML comuns de espaço antes do regex para não falhar
            clean_text = text.replace("&nbsp;", " ")
            
            # Tenta extrair o email ou outro identificador válido (a API Runrun.it às vezes retorna no author_id/user_id)
            user_data = comment.get("user") or {}
            user_email = (comment.get("user_email") or user_data.get("email") or "").strip().lower()
            
            # Se a API não retornar o e-mail de forma óbvia, no payload parece ter author_id e user_id. 
            # O sistema pode ser adaptado depois se precisarmos bater o author_id.
            
            # Avalia se deve sobrescrever a data (filtro de email temporariamente desativado, 
            # ou ative verificando: `if not ALLOWED_DATE_OVERRIDE_EMAILS or user_email in ALLOWED_DATE_OVERRIDE_EMAILS:`)
            
            date_match = re.search(r'(?:^|\s+)(\d{2}/\d{2}/\d{4})(?:\s*)$', clean_text)
            if date_match:
                # Opcionalmente reativar a checagem:
                # if ALLOWED_DATE_OVERRIDE_EMAILS and user_email not in ALLOWED_DATE_OVERRIDE_EMAILS:
                #     pass # Não sobrescreve
                # else:
                date_str_br = date_match.group(1)
                try:
                    day, month, year = date_str_br.split('/')
                    data_str = f"{year}-{month}-{day}"
                    # Limpa a data do texto para que o parse da hashtag não confunda a hashtag caso ela esteja colada
                    text = clean_text[:date_match.start()].strip()
                except ValueError:
                    pass
            
            hashtags_found = _parse_hashtags(text)
            
            if not hashtags_found:
                has_valid_tag = any(v for v in tag_map.values())
                if has_valid_tag:
                    task_title = task.get("title") or ""
                    if DEBUG_MODE:
                        add_ignored_item("task", str(task_id), f"Tarefa '{task_title}' tem tags mapeadas mas comentário sem quantidade")
                else:
                    if DEBUG_MODE:
                        add_ignored_item("comment", str(comment.get("id")), "Comentário sem hashtag de entrega", comment_text=text)
                ignored_count += 1
                continue

            for comment_slug, qty in hashtags_found:
                scope_slug = (
                    tag_map.get(comment_slug)
                    or _match_tag(comment_slug, grupo, escopo)
                )
                
                if not scope_slug:
                    if DEBUG_MODE:
                        add_ignored_item("hashtag", comment_slug, f"Hashtag '#{comment_slug}' não mapeada ao escopo", comment_text=text)
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


def add_ignored_item(item_type: str, item_id: str, reason: str, comment_text: str = None):
    """Adiciona um item ignorado à lista."""
    global _ignored_items
    
    ignored_entry = {
        "type": item_type,
        "id": item_id,
        "reason": reason,
        "comment_text": comment_text,
    }
    _ignored_items.append(ignored_entry)
    
    if DEBUG_MODE:
        params = {"id": item_id}
        if comment_text:
            params["comment_text"] = comment_text
            
        database.log_debug_request(
            endpoint=f"ignored_{item_type}",
            params=params,
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
    import queue_manager
    from dotenv import load_dotenv
    load_dotenv()
    
    # Adquire lock distribuído para evitar múltiplas execuções
    if not queue_manager.acquire_lock("sync_lock", expires_in_sec=600):
        return {
            "status": "error",
            "error": "Sincronização já em andamento por outro processo/usuário.",
            "message": "Uma sincronização já está rodando. Aguarde a conclusão."
        }
    
    sync_id = database.log_sync_start("full_sync")
    start_time = time.time()
    
    try:
        # Limpa fila de execuções anteriores para evitar métricas antigas no dashboard e retries infinitos
        queue_manager.clear_queue()
        
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
        queue_manager.release_lock("sync_lock")
        
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
        queue_manager.release_lock("sync_lock")
        
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
