import re
import os
import unicodedata
from datetime import date
import pandas as pd
from config import CLIENT_NAME, DATA_INICIO
import api_client

EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Escopo Nuclea.xlsx")
TEMPO_CONTRATO_MESES = 12  # contrato anual: março a fevereiro
ESCOPO_NOME = "YESH HUB"   # nome do escopo/contrato (usado no header)


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
    print("Buscando cliente " + CLIENT_NAME + "...")
    client_id = api_client.get_client_id(CLIENT_NAME)
    if not client_id:
        raise ValueError("Cliente '" + CLIENT_NAME + "' não encontrado na API.")

    print("Buscando tarefas de Gestão de Atendimento...")
    gestao_tasks = api_client.get_gestao_tasks(client_id)
    print(str(len(gestao_tasks)) + " tarefas de Gestão encontradas.")

    rows = []
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
        comments = api_client.get_comments(task_id)

        for comment in comments:
            data_str = (comment.get("created_at") or "")[:10]  # YYYY-MM-DD
            text = comment.get("text") or ""

            for comment_slug, qty in _parse_hashtags(text):
                scope_slug = (
                    tag_map.get(comment_slug)
                    or _match_tag(comment_slug, grupo, escopo)
                )
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
        "total_contrato":       total_contrato,
        "saldo_escopo":         saldo_escopo,
        "pct_realizacao":       pct,
        "meses_decorridos":      round(_meses_decorridos(), 1),
        "tempo_contrato_meses": TEMPO_CONTRATO_MESES,
        "escopo_nome":          ESCOPO_NOME,
    }
