import io
import json
import os
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import pandas as pd
import data_processor
import export

app = Flask(__name__)
CORS(app, origins=["https://renataesposito.github.io"])

print("Carregando escopo contratado...")
try:
    _escopo = data_processor.load_escopo()
    print("Carregando entregas do RunRun.it...")
    _entregas = data_processor.load_entregas(_escopo)
except Exception as _err:
    print(f"AVISO: falha ao carregar dados — {_err}")
    print("Servidor iniciado com dados vazios.")
    _escopo   = pd.DataFrame(columns=["grupo","entregavel","qtd_mes","qtd_ano","previsto_acumulado","slug"])
    _entregas = pd.DataFrame(columns=["task_id","projeto","grupo","hashtag","scope_slug","quantidade","data","mes_ano","mapeado"])

_escopo_real = data_processor.escopo_com_realizado(_escopo, _entregas)
_kpis = data_processor.compute_kpis(_escopo, _entregas)
print("Dados carregados.")


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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    escopo_json  = json.loads(_escopo_real.to_json(orient="records"))
    entregas_json = json.loads(_entregas.to_json(orient="records")) if not _entregas.empty else []
    grupos = sorted(_escopo["grupo"].dropna().unique().tolist())
    return jsonify({
        "kpis":     _kpis,
        "escopo":   escopo_json,
        "entregas": entregas_json,
        "grupos":   grupos,
    })


@app.route("/api/export")
def api_export():
    esc, ent = _filter(
        request.args.get("ini", ""),
        request.args.get("fim", ""),
        request.args.get("grupo", ""),
    )
    esc_real = data_processor.escopo_com_realizado(esc, ent)
    kpis     = data_processor.compute_kpis(esc, ent)
    xlsx     = export.gerar_excel(esc_real, ent, kpis)
    return send_file(
        io.BytesIO(xlsx),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="nuclea_previsto_realizado.xlsx",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(debug=False, host="0.0.0.0", port=port)
