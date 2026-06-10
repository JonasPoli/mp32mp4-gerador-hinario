#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
admin/app.py — Painel administrativo do Hinário CCB
Servido via Flask. Conecta ao progresso.db e ao CSV do hinário.

Rodar:
  cd /Volumes/Dados/work/hinário/admin
  source ../.venv/bin/activate
  pip install flask
  python app.py
"""

import csv
import re
import sqlite3
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT  = Path(__file__).parent.parent          # /Volumes/Dados/work/hinário
DB    = ROOT / "progresso.db"
CSV   = ROOT / "fontes" / "hinario4_sequential.csv"
ADMIN = Path(__file__).parent                 # pasta admin/

app = Flask(__name__, static_folder=str(ADMIN / "static"), static_url_path="/static")


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def remover_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def camel_case(texto: str) -> str:
    sem = remover_acentos(texto)
    return "".join(p.capitalize() for p in re.findall(r"[A-Za-z0-9]+", sem))


def _db():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def carregar_csv() -> dict[int, str]:
    hinos: dict[int, str] = {}
    try:
        with open(CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    hinos[int(row["Número"])] = row["Nome"].strip()
                except (KeyError, ValueError):
                    pass
    except FileNotFoundError:
        pass
    return hinos


HINOS = carregar_csv()


def gerar_metadados(numero: int, nome: str) -> dict:
    """Retorna dict com título, descrição, tags gerados da mesma forma que gerar_videos.py."""
    tag_hino = f"Hino{numero}"
    tag_nome = camel_case(nome)
    nome_sem = remover_acentos(nome).lower()
    n = numero

    titulo = f"Hino {n} - {nome} | Hinário 4 CCB | Teclado Yamaha PSR"

    descricao = (
        f"Hino {n} - {nome}\n"
        f"Hinário 4 - Congregação Cristã no Brasil\n\n"
        f"Execução instrumental no teclado Yamaha PSR.\n\n"
        f"Este vídeo apresenta o áudio do hino {n}, \"{nome}\", tocado em teclado, "
        f"com uma interpretação simples e reverente para momentos de meditação, "
        f"estudo, louvor e acompanhamento musical.\n\n"
        f"Que esta melodia possa trazer paz, comunhão e edificação.\n\n"
        f"🎹 Instrumento: Teclado Yamaha PSR\n"
        f"🎵 Hino: {n}\n"
        f"📖 Hinário: Hinário 4\n"
        f"🎶 Título: {nome}\n\n"
        f"Inscreva-se no canal para acompanhar mais hinos instrumentais da CCB no teclado.\n\n"
        f"#{tag_hino} #Hinario4 #CCB"
    )

    tags = (
        f"hino {n}, hino {n} ccb, {nome_sem}, hinário 4, hinario 4, ccb hino {n}, "
        f"hinos ccb, hinos da ccb, congregação cristã no brasil, congregacao crista no brasil, "
        f"hinos tocados no teclado, hino no teclado, teclado yamaha psr, yamaha psr, "
        f"hinos ccb teclado, hino instrumental ccb, ccb instrumental, hinário ccb, hinario ccb, "
        f"hinos para meditação, hinos para meditacao, música instrumental cristã, "
        f"musica instrumental crista, louvor instrumental, teclado evangélico, "
        f"hinos evangélicos no teclado, hino {n} instrumental"
    )

    return {"titulo": titulo, "descricao": descricao, "tags": tags}


def video_para_dict(row, data_postagem: str | None = None) -> dict:
    numero = row["numero"]
    nome   = HINOS.get(numero, f"Hino {numero}")
    meta   = gerar_metadados(numero, nome)

    # Arquivo de vídeo gerado
    output = row["output"] or ""
    video_file = Path(output).name if output else ""

    # Thumb
    thumb_file = f"hino_{numero:03d}.png"
    thumb_exists = (ROOT / "thumbs" / thumb_file).exists()

    return {
        "numero":        numero,
        "hinario":       row["hinario"],
        "status":        row["status"],
        "mp3_file":      Path(row["mp3_file"]).name if row["mp3_file"] else "",
        "video_file":    video_file,
        "thumb_file":    thumb_file if thumb_exists else "",
        "titulo":        meta["titulo"],
        "descricao":     meta["descricao"],
        "tags":          meta["tags"],
        "criado_em":     row["criado_em"] or "",
        "atualizado_em": row["atualizado_em"] or "",
        "data_postagem": data_postagem or row["data_postagem"] if "data_postagem" in row.keys() else "",
        "erro_msg":      row["erro_msg"] or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Migração: coluna data_postagem
# ─────────────────────────────────────────────────────────────────────────────

def migrar():
    with _db() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(videos)")]
        if "data_postagem" not in cols:
            conn.execute("ALTER TABLE videos ADD COLUMN data_postagem TEXT")
            conn.commit()


migrar()


# ─────────────────────────────────────────────────────────────────────────────
# Rotas API
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(ADMIN), "index.html")


@app.route("/api/stats")
def api_stats():
    conn = _db()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM videos GROUP BY status"
    ).fetchall()
    stats = {r["status"]: r["n"] for r in rows}
    total = conn.execute("SELECT COUNT(*) AS n FROM videos").fetchone()["n"]
    conn.close()
    return jsonify({"total": total, **stats})


@app.route("/api/videos")
def api_videos():
    """Lista todos os vídeos (concluídos), paginado."""
    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    status   = request.args.get("status", "concluido")
    offset   = (page - 1) * per_page

    conn  = _db()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM videos WHERE status = ?", (status,)
    ).fetchone()["n"]
    rows  = conn.execute(
        "SELECT * FROM videos WHERE status = ? ORDER BY numero LIMIT ? OFFSET ?",
        (status, per_page, offset),
    ).fetchall()
    conn.close()

    return jsonify({
        "total":   total,
        "page":    page,
        "pages":   (total + per_page - 1) // per_page,
        "videos":  [video_para_dict(r) for r in rows],
    })


@app.route("/api/videos/search")
def api_search():
    """Busca vídeo pelo nome do arquivo (video_file ou mp3_file)."""
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"videos": []})

    conn = _db()
    rows = conn.execute(
        "SELECT * FROM videos WHERE LOWER(output) LIKE ? OR LOWER(mp3_file) LIKE ? ORDER BY numero",
        (f"%{q}%", f"%{q}%"),
    ).fetchall()
    conn.close()

    return jsonify({"videos": [video_para_dict(r) for r in rows]})


@app.route("/api/videos/<int:numero>")
def api_video_detail(numero: int):
    conn = _db()
    row  = conn.execute("SELECT * FROM videos WHERE numero = ?", (numero,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "Não encontrado"}), 404
    return jsonify(video_para_dict(row))


@app.route("/api/schedule", methods=["POST"])
def api_schedule():
    """
    Gera datas de postagem sequenciais a partir de uma data base.
    Payload JSON:
      {
        "data_base": "2026-07-01",   ← data ISO da primeira postagem
        "intervalo_dias": 1,          ← dias entre postagens (default: 1)
        "hora": "15:00"               ← horário para todas (default: "15:00")
      }
    Salva data_postagem em cada vídeo concluído, em ordem numérica.
    """
    body          = request.get_json(force=True)
    data_base_str = body.get("data_base", "")
    intervalo     = int(body.get("intervalo_dias", 1))
    hora          = body.get("hora", "15:00")

    try:
        base = date.fromisoformat(data_base_str)
    except (ValueError, TypeError):
        return jsonify({"error": "data_base inválida. Use formato YYYY-MM-DD."}), 400

    conn  = _db()
    rows  = conn.execute(
        "SELECT numero FROM videos WHERE status = 'concluido' ORDER BY numero"
    ).fetchall()

    atualizados = []
    for i, row in enumerate(rows):
        numero      = row["numero"]
        data_post   = base + timedelta(days=i * intervalo)
        data_str    = f"{data_post.isoformat()}T{hora}:00"
        conn.execute(
            "UPDATE videos SET data_postagem = ? WHERE numero = ?",
            (data_str, numero),
        )
        atualizados.append({"numero": numero, "data_postagem": data_str})

    conn.commit()
    conn.close()
    return jsonify({"atualizados": len(atualizados), "videos": atualizados})


@app.route("/api/videos/<int:numero>/postagem", methods=["PATCH"])
def api_update_postagem(numero: int):
    """Atualiza a data_postagem de um vídeo individual."""
    body = request.get_json(force=True)
    data = body.get("data_postagem", "")
    conn = _db()
    conn.execute(
        "UPDATE videos SET data_postagem = ? WHERE numero = ?", (data, numero)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM videos WHERE numero = ?", (numero,)).fetchone()
    conn.close()
    return jsonify(video_para_dict(row))


if __name__ == "__main__":
    print("🎹 Painel Hinário CCB — http://localhost:5000")
    app.run(debug=True, port=5000)
