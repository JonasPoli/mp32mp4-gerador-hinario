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
import json
import re
import sqlite3
import unicodedata
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT  = Path(__file__).parent.parent          # /Volumes/Dados/work/hinário
DB    = ROOT / "progresso.db"
ADMIN = Path(__file__).parent                 # pasta admin/

app = Flask(__name__, static_folder=str(ADMIN / "static"), static_url_path="/static")


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários e Projetos
# ─────────────────────────────────────────────────────────────────────────────

def carregar_projetos() -> dict:
    caminho = ROOT / "projetos.json"
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


PROJETOS = carregar_projetos()


def carregar_csv_projeto(csv_path: Path) -> dict:
    """Retorna dicionário {numero: nome} a partir do CSV do hinário com suporte a colunas dinâmicas."""
    hinos = {}
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    num_key = next((k for k in row.keys() if "número" in k.lower() or "numero" in k.lower()), None)
                    nome_key = next((k for k in row.keys() if "nome" in k.lower() or "título" in k.lower() or "titulo" in k.lower()), None)
                    if num_key and nome_key:
                        num_str = row[num_key].strip()
                        try:
                            num = int(num_str)
                        except ValueError:
                            num = num_str
                        hinos[num] = row[nome_key].strip()
                except (KeyError, ValueError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    return hinos


# Cache dos hinos por projeto
HINOS_PROJETOS = {
    p_name: carregar_csv_projeto(ROOT / p_cfg["csv_path"])
    for p_name, p_cfg in PROJETOS.items()
}


def remover_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def camel_case(texto: str) -> str:
    sem = remover_acentos(texto)
    return "".join(p.capitalize() for p in re.findall(r"[A-Za-z0-9]+", sem))


def carregar_templates_youtube() -> dict:
    youtube_path = ROOT / "youtube.md"
    if not youtube_path.exists():
        return {}
    try:
        linhas = youtube_path.read_text(encoding="utf-8").splitlines()
        secoes = {}
        secao_atual = None
        linhas_secao = []
        
        for linha in linhas:
            linha_stripped = linha.strip()
            if linha_stripped.startswith("## "):
                if secao_atual:
                    secoes[secao_atual] = "\n".join(linhas_secao).strip()
                secao_atual = linha_stripped[3:].strip()
                linhas_secao = []
            elif secao_atual is not None:
                linhas_secao.append(linha)
                
        if secao_atual:
            secoes[secao_atual] = "\n".join(linhas_secao).strip()
            
        templates = {}
        for nome_secao, conteudo in secoes.items():
            if "título" in nome_secao.lower() or "titulo" in nome_secao.lower():
                templates["titulo"] = conteudo
            elif "descrição" in nome_secao.lower() or "descricao" in nome_secao.lower():
                templates["descricao"] = conteudo
            elif "tags" in nome_secao.lower():
                templates["tags"] = conteudo
                
        return templates
    except Exception as e:
        print(f"[aviso] Erro ao carregar youtube.md: {e}")
        return {}


def formatar_template(template: str, variables: dict) -> str:
    res = template
    
    # 1. Substituir pares de tags/nomes para evitar duplicatas erradas
    res = re.sub(
        r'<nome-do-hino>\s*,\s*<nome-do-hino>',
        f"{variables.get('nome', '')}, {variables.get('nome_sem_acento', '')}",
        res
    )
    
    res = re.sub(
        r'<nome-do-projeto>\s*,\s*<nome-do-projeto>',
        f"{variables.get('nome_exibicao', '')}, {variables.get('nome_exibicao', '').lower()}",
        res
    )
    
    # 2. Substituir variáveis explícitas
    res = res.replace("<numero-do-hino>", variables.get("numero", ""))
    res = res.replace("<numero-do-hino", variables.get("numero", ""))  # Tratar falta de fechamento
    res = res.replace("<nome-do-hino>", variables.get("nome", ""))
    res = res.replace("<nome-do-projeto>", variables.get("nome_exibicao", ""))
    res = res.replace("<nome-sem-acento>", variables.get("nome_sem_acento", ""))
    res = res.replace("<numero-do-hinario>", variables.get("numero_do_hinario", ""))
    
    # 3. Resolver amostra literal solicitada
    res = res.replace("cristo jesus sua mao me da", variables.get("nome_sem_acento", ""))
    res = res.replace("cristo jesus sua mão me dá", variables.get("nome", ""))
    
    # 4. Suportar chaves legadas (caso projetos.json ou banco use)
    for k, v in variables.items():
        res = res.replace("{" + k + "}", str(v))
        
    return res


def _db():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def gerar_metadados(numero: int, nome: str, projeto_nome: str, projeto_cfg: dict) -> dict:
    """Retorna dict com título, descrição, tags gerados a partir do template do projeto."""
    tag_hino = f"Hino{numero}"
    tag_nome = camel_case(nome)
    nome_sem = remover_acentos(nome).lower()

    titulo_temp = projeto_cfg.get("titulo_template", "Hino {numero} - {nome}")
    desc_temp = projeto_cfg.get("descricao", "")
    tags_temp = projeto_cfg.get("palavras_chaves", "")

    yt_templates = carregar_templates_youtube()
    if yt_templates:
        titulo_temp = yt_templates.get("titulo", titulo_temp)
        desc_temp = yt_templates.get("descricao", desc_temp)
        tags_temp = yt_templates.get("tags", tags_temp)

    csv_path = projeto_cfg.get("csv_path", "")
    if "hinario4" in csv_path:
        numero_do_hinario = "4"
    elif "hinario5" in csv_path:
        numero_do_hinario = "5"
    else:
        match = re.search(r'\d+', csv_path)
        if match:
            numero_do_hinario = match.group(0)
        else:
            match = re.search(r'\d+', projeto_nome)
            numero_do_hinario = match.group(0) if match else ""

    variables = {
        "numero": str(numero),
        "nome": nome,
        "tag_hino": tag_hino,
        "tag_nome": tag_nome,
        "nome_sem_acento": nome_sem,
        "nome_projeto": projeto_nome,
        "nome_exibicao": projeto_cfg.get("nome_exibicao", projeto_nome),
        "numero_do_hinario": numero_do_hinario
    }

    titulo = formatar_template(titulo_temp, variables)
    descricao = formatar_template(desc_temp, variables)
    tags = formatar_template(tags_temp, variables)

    # Garantir limite de 500 caracteres, removendo as últimas tags se passar
    if len(tags) > 500:
        parts = [t.strip() for t in tags.split(",") if t.strip()]
        valid_parts = []
        current_len = 0
        for part in parts:
            added_len = len(part) + (2 if valid_parts else 0)
            if current_len + added_len <= 500:
                valid_parts.append(part)
                current_len += added_len
            else:
                break
        tags = ", ".join(valid_parts)

    return {"titulo": titulo, "descricao": descricao, "tags": tags}


def formatar_numero_completo(numero) -> str:
    if isinstance(numero, int):
        return f"{numero:03d}"
    num_str = str(numero).strip()
    if num_str.isdigit():
        return f"{int(num_str):03d}"
    if num_str.upper().startswith("C") and num_str[1:].isdigit():
        return f"C{int(num_str[1:]):03d}"
    return num_str


def video_para_dict(row, data_postagem: str | None = None) -> dict:
    projeto = row["projeto"]
    numero  = row["numero"]
    hinos_projeto = HINOS_PROJETOS.get(projeto, {})
    nome = hinos_projeto.get(numero) or hinos_projeto.get(str(numero)) or hinos_projeto.get(int(numero) if str(numero).isdigit() else None) or f"Hino {numero}"
    
    projeto_cfg = PROJETOS.get(projeto, {})
    meta = gerar_metadados(numero, nome, projeto, projeto_cfg)
 
    # Arquivo de vídeo gerado
    output = row["output"] or ""
    video_file = Path(output).name if output else ""
 
    # Thumb
    thumb_file = f"hino-{projeto}-{formatar_numero_completo(numero)}.png"
    thumb_exists = (ROOT / "thumbs" / thumb_file).exists()

    return {
        "numero":        numero,
        "projeto":       projeto,
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
# Migração: coluna data_postagem e estrutura de projetos
# ─────────────────────────────────────────────────────────────────────────────

def migrar():
    with _db() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(videos)")]
        if "projeto" not in cols:
            print("[banco] Migrando banco de dados para suportar múltiplos projetos...")
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute("ALTER TABLE videos RENAME TO _videos_old")
                conn.execute("""
                    CREATE TABLE videos (
                        projeto       TEXT NOT NULL DEFAULT 'hinario4',
                        numero        INTEGER NOT NULL,
                        mp3_file      TEXT NOT NULL,
                        hinario       TEXT NOT NULL DEFAULT 'hinario4',
                        status        TEXT NOT NULL DEFAULT 'pendente',
                        output        TEXT,
                        erro_msg      TEXT,
                        criado_em     TEXT,
                        atualizado_em TEXT,
                        data_postagem TEXT,
                        PRIMARY KEY (projeto, numero)
                    )
                """)
                cols_to_copy = "numero, mp3_file, hinario, status, output, erro_msg, criado_em, atualizado_em"
                if "data_postagem" in cols:
                    cols_to_copy += ", data_postagem"
                    conn.execute(f"INSERT INTO videos (projeto, numero, mp3_file, hinario, status, output, erro_msg, criado_em, atualizado_em, data_postagem) SELECT 'hinario4', {cols_to_copy} FROM _videos_old")
                else:
                    conn.execute(f"INSERT INTO videos (projeto, numero, mp3_file, hinario, status, output, erro_msg, criado_em, atualizado_em) SELECT 'hinario4', {cols_to_copy} FROM _videos_old")
                conn.execute("DROP TABLE _videos_old")
                
                c_cursor = conn.execute("PRAGMA table_info(clipes)")
                c_cols = [r[1] for r in c_cursor.fetchall()]
                if c_cols:
                    conn.execute("ALTER TABLE clipes RENAME TO _clipes_old")
                    conn.execute("""
                        CREATE TABLE clipes (
                            id             INTEGER PRIMARY KEY AUTOINCREMENT,
                            caminho        TEXT UNIQUE NOT NULL,
                            fonte          TEXT,
                            duracao_s      REAL,
                            projeto_usado  TEXT,
                            usado_em       INTEGER,
                            vezes_usado    INTEGER NOT NULL DEFAULT 0,
                            FOREIGN KEY (projeto_usado, usado_em) REFERENCES videos(projeto, numero)
                        )
                    """)
                    conn.execute("INSERT INTO clipes (id, caminho, fonte, duracao_s, projeto_usado, usado_em, vezes_usado) SELECT id, caminho, fonte, duracao_s, CASE WHEN usado_em IS NOT NULL THEN 'hinario4' ELSE NULL END, usado_em, CASE WHEN usado_em IS NOT NULL THEN 1 ELSE 0 END FROM _clipes_old")
                    conn.execute("DROP TABLE _clipes_old")
                conn.commit()
                print("[banco] Migração concluída com sucesso.")
            except Exception as e:
                conn.execute("ROLLBACK")
                print(f"[banco] ERRO na migração: {e}")
                raise
        # Garante data_postagem
        cols = [r[1] for r in conn.execute("PRAGMA table_info(videos)")]
        if "data_postagem" not in cols:
            conn.execute("ALTER TABLE videos ADD COLUMN data_postagem TEXT")
            conn.commit()

        # Garante coluna vezes_usado
        c_cursor = conn.execute("PRAGMA table_info(clipes)")
        c_cols = [r[1] for r in c_cursor.fetchall()]
        if c_cols and "vezes_usado" not in c_cols:
            print("[banco] Adicionando coluna 'vezes_usado' na tabela 'clipes'...")
            conn.execute("ALTER TABLE clipes ADD COLUMN vezes_usado INTEGER NOT NULL DEFAULT 0")
            conn.execute("UPDATE clipes SET vezes_usado = 1 WHERE projeto_usado IS NOT NULL OR usado_em IS NOT NULL")
            conn.commit()


migrar()


# ─────────────────────────────────────────────────────────────────────────────
# Rotas API
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(ADMIN), "index.html")


@app.route("/thumbs/<path:filename>")
def serve_thumb(filename):
    return send_from_directory(str(ROOT / "thumbs"), filename)


@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(str(ROOT / "images"), filename)


@app.route("/api/projects")
def api_projects():
    return jsonify(PROJETOS)


@app.route("/api/projects/<projeto>/export-csv")
def api_export_csv(projeto: str):
    if projeto not in PROJETOS:
        return jsonify({"error": f"Projeto '{projeto}' não encontrado"}), 404
        
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM videos WHERE projeto = ? ORDER BY numero", (projeto,)
    ).fetchall()
    conn.close()
    
    import io
    output = io.StringIO()
    # UTF-8 BOM so Excel handles accents correctly
    output.write('\ufeff')
    
    writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_MINIMAL)
    
    # Headers
    writer.writerow([
        "ID",
        "Arquivo de vídeo",
        "Arquivo de vídeo limpo",
        "Título",
        "Descrição",
        "Miniatura",
        "Nome do projeto",
        "Tags",
        "Data de publicação",
        "Hora de publicação"
    ])
    
    projeto_cfg = PROJETOS.get(projeto, {})
    nome_exibicao = projeto_cfg.get("nome_exibicao", projeto)
    hinos_projeto = HINOS_PROJETOS.get(projeto, {})
    
    for row in rows:
        numero = row["numero"]
        output_path = row["output"] or ""
        video_file = Path(output_path).name if output_path else ""
        
        video_file_clean = ""
        if video_file:
            stem = Path(video_file).stem
            video_file_clean = stem.replace("-", " ").replace("_", " ")
            
        nome_hino = hinos_projeto.get(numero, f"Hino {numero}")
        meta = gerar_metadados(numero, nome_hino, projeto, projeto_cfg)
        
        thumb_file = f"hino-{projeto}-{formatar_numero_completo(numero)}.png"
        
        data_postagem = row["data_postagem"] or ""
        date_part, time_part = "", ""
        if data_postagem:
            parts = data_postagem.replace("T", " ").split(" ")
            date_part = parts[0]
            if len(parts) > 1:
                time_part = parts[1][:5]
                
        tags = meta["tags"]
        if len(tags) > 400:
            parts = [t.strip() for t in tags.split(",") if t.strip()]
            valid_parts = []
            current_len = 0
            for part in parts:
                added_len = len(part) + (2 if valid_parts else 0)
                if current_len + added_len <= 400:
                    valid_parts.append(part)
                    current_len += added_len
                else:
                    break
            tags = ", ".join(valid_parts)

        writer.writerow([
            numero,
            video_file,
            video_file_clean,
            meta["titulo"],
            meta["descricao"],
            thumb_file,
            nome_exibicao,
            tags,
            date_part,
            time_part
        ])
        
    response = app.response_class(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8"
    )
    filename = f"videos_{projeto}.csv"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response



@app.route("/api/stats")
def api_stats():
    projeto = request.args.get("projeto", list(PROJETOS.keys())[0])
    conn = _db()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM videos WHERE projeto = ? GROUP BY status", (projeto,)
    ).fetchall()
    stats = {r["status"]: r["n"] for r in rows}
    total = conn.execute("SELECT COUNT(*) AS n FROM videos WHERE projeto = ?", (projeto,)).fetchone()["n"]
    conn.close()
    return jsonify({"total": total, **stats})


@app.route("/api/videos")
def api_videos():
    projeto  = request.args.get("projeto", list(PROJETOS.keys())[0])
    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    status   = request.args.get("status", "concluido")
    offset   = (page - 1) * per_page

    conn  = _db()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM videos WHERE status = ? AND projeto = ?", (status, projeto)
    ).fetchone()["n"]
    rows  = conn.execute(
        "SELECT * FROM videos WHERE status = ? AND projeto = ? ORDER BY numero LIMIT ? OFFSET ?",
        (status, projeto, per_page, offset),
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
    projeto = request.args.get("projeto", list(PROJETOS.keys())[0])
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"videos": []})

    conn = _db()
    rows = conn.execute(
        "SELECT * FROM videos WHERE projeto = ? AND (LOWER(output) LIKE ? OR LOWER(mp3_file) LIKE ?) ORDER BY numero",
        (projeto, f"%{q}%", f"%{q}%"),
    ).fetchall()
    conn.close()

    return jsonify({"videos": [video_para_dict(r) for r in rows]})


@app.route("/api/videos/<numero>")
def api_video_detail(numero):
    # Try converting numeric strings to int to match SQLite integer column type
    query_num = numero
    try:
        query_num = int(numero)
    except ValueError:
        pass
    projeto = request.args.get("projeto", list(PROJETOS.keys())[0])
    conn = _db()
    row  = conn.execute("SELECT * FROM videos WHERE projeto = ? AND numero = ?", (projeto, query_num)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "Não encontrado"}), 404
    return jsonify(video_para_dict(row))


@app.route("/api/schedule", methods=["POST"])
def api_schedule():
    body          = request.get_json(force=True)
    projeto       = body.get("projeto", list(PROJETOS.keys())[0])
    data_base_str = body.get("data_base", "")
    intervalo     = int(body.get("intervalo_dias", 1))
    hora          = body.get("hora", "15:00")

    try:
        base = date.fromisoformat(data_base_str)
    except (ValueError, TypeError):
        return jsonify({"error": "data_base inválida. Use formato YYYY-MM-DD."}), 400

    conn  = _db()
    rows  = conn.execute(
        "SELECT numero FROM videos WHERE status = 'concluido' AND projeto = ? ORDER BY numero", (projeto,)
    ).fetchall()

    atualizados = []
    for i, row in enumerate(rows):
        numero      = row["numero"]
        data_post   = base + timedelta(days=i * intervalo)
        data_str    = f"{data_post.isoformat()}T{hora}:00"
        conn.execute(
            "UPDATE videos SET data_postagem = ? WHERE projeto = ? AND numero = ?",
            (data_str, projeto, numero),
        )
        atualizados.append({"numero": numero, "data_postagem": data_str})

    conn.commit()
    conn.close()
    return jsonify({"atualizados": len(atualizados), "videos": atualizados})


@app.route("/api/videos/<numero>/postagem", methods=["PATCH"])
def api_update_postagem(numero):
    query_num = numero
    try:
        query_num = int(numero)
    except ValueError:
        pass
    body = request.get_json(force=True)
    projeto = body.get("projeto", list(PROJETOS.keys())[0])
    data = body.get("data_postagem", "")
    conn = _db()
    conn.execute(
        "UPDATE videos SET data_postagem = ? WHERE projeto = ? AND numero = ?", (data, projeto, query_num)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM videos WHERE projeto = ? AND numero = ?", (projeto, query_num)).fetchone()
    conn.close()
    return jsonify(video_para_dict(row))


@app.route("/api/projects/create", methods=["POST"])
def criar_projeto():
    # 1. Obter os dados do request
    projeto_id = request.form.get("id", "").strip().lower()
    projeto_nome = request.form.get("nome", "").strip()
    hinario_versao = request.form.get("hinario", "").strip()
    imagem_file = request.files.get("imagem")

    # 2. Validações
    if not projeto_id or not re.match(r"^[a-z0-9_]+$", projeto_id):
        return jsonify({"error": "ID do projeto inválido. Use apenas letras, números e underlines."}), 400
        
    if not projeto_nome:
        return jsonify({"error": "Nome do projeto é obrigatório."}), 400
        
    if hinario_versao not in ("4", "5"):
        return jsonify({"error": "Hinário deve ser 4 ou 5."}), 400
        
    if not imagem_file:
        return jsonify({"error": "Imagem de fundo é obrigatória."}), 400

    # Carregar projetos existentes
    projetos = carregar_projetos()
    if projeto_id in projetos:
        return jsonify({"error": f"Projeto com ID '{projeto_id}' já existe."}), 400

    # 3. Salvar a imagem de fundo
    images_dir = ROOT / "images"
    images_dir.mkdir(exist_ok=True)
    
    filename = imagem_file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        ext = ".png"
        
    imagem_nome = f"{projeto_id}{ext}"
    imagem_path = images_dir / imagem_nome
    imagem_file.save(str(imagem_path))

    # 4. Criar a configuração do novo projeto
    base_hinario = "hinario4" if hinario_versao == "4" else "hinario5"
    if base_hinario not in projetos:
        # Fallback de segurança
        base_cfg = {
            "nome_exibicao": projeto_nome,
            "csv_path": f"fontes/hinario{hinario_versao}.csv",
            "mp3_dir": "mp3",
            "imagem_base": f"images/{imagem_nome}",
            "desenho": {
                "numero": {"x": 139, "y_top": 169, "y_bottom": 767, "cor": [26, 45, 90, 255]},
                "nome": {"x": 139, "y_top": 780, "y_bottom": 880, "cor": [26, 45, 90, 255], "max_font_size": 42, "align": "left"}
            }
        }
    else:
        # Clonar
        base_cfg = json.loads(json.dumps(projetos[base_hinario]))
        base_cfg["nome_exibicao"] = projeto_nome
        base_cfg["csv_path"] = "fontes/hinario4_sequential.csv" if hinario_versao == "4" else "fontes/hinario5.csv"
        base_cfg["imagem_base"] = f"images/{imagem_nome}"

    # Inserir no projetos.json
    projetos[projeto_id] = base_cfg
    with open(ROOT / "projetos.json", "w", encoding="utf-8") as f:
        json.dump(projetos, f, indent=2, ensure_ascii=False)

    # Recarregar PROJETOS em memória
    global PROJETOS, HINOS_PROJETOS
    PROJETOS = carregar_projetos()

    # 5. Inicializar os vídeos do projeto no banco de dados
    conn = _db()
    try:
        csv_path = ROOT / base_cfg["csv_path"]
        mp3_dir = ROOT / base_cfg.get("mp3_dir", "mp3")
        
        # Load CSV
        hinos_validos = carregar_csv_projeto(csv_path)
        
        # Scan MP3s
        if mp3_dir.exists():
            for mp3 in sorted(mp3_dir.glob("*.mp3")):
                m = re.match(r"^(\d+)", mp3.name)
                if m:
                    numero = int(m.group(1))
                else:
                    m_coro = re.match(r"^Coro\s+(\d+)", mp3.name, re.IGNORECASE)
                    if m_coro:
                        numero = int(m_coro.group(1))
                    else:
                        continue
                if numero in hinos_validos:
                    conn.execute(
                        "INSERT OR IGNORE INTO videos (projeto, numero, mp3_file, hinario, status, criado_em, atualizado_em) "
                        "VALUES (?, ?, ?, ?, 'pendente', ?, ?)",
                        (projeto_id, numero, str(mp3.relative_to(ROOT)), projeto_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
                    )
            conn.commit()
    except Exception as db_err:
        print(f"[aviso] Erro ao sincronizar hinos do novo projeto no banco: {db_err}")
    finally:
        conn.close()

    # Recarregar o cache de hinos
    HINOS_PROJETOS[projeto_id] = carregar_csv_projeto(ROOT / base_cfg["csv_path"])

    return jsonify({"success": True, "projeto_key": projeto_id})


@app.route("/api/videos/<projeto>/<numero>/gerar-thumb", methods=["POST"])
def api_gerar_thumb(projeto: str, numero):
    query_num = numero
    try:
        query_num = int(numero)
    except ValueError:
        pass
    if projeto not in PROJETOS:
        return jsonify({"error": f"Projeto '{projeto}' não encontrado"}), 404
        
    hinos_projeto = HINOS_PROJETOS.get(projeto, {})
    nome = hinos_projeto.get(query_num, f"Hino {query_num}")
    projeto_cfg = PROJETOS[projeto]
    
    try:
        import sys
        if str(ROOT) not in sys.path:
            sys.path.append(str(ROOT))
        from gerar_videos import gerar_thumbnail_hino
        
        gerar_thumbnail_hino(query_num, nome, projeto, projeto_cfg)
        
        thumb_file = f"hino-{projeto}-{formatar_numero_completo(query_num)}.png"
        return jsonify({
            "success": True,
            "thumb_url": f"/thumbs/{thumb_file}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("🎹 Painel Hinário CCB — http://localhost:5000")
    app.run(debug=True, port=5000)
