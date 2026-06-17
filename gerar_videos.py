#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_videos.py — Gerador de vídeos para o Hinário CCB

Uso:
  python gerar_videos.py                              # gera tudo / continua de onde parou
  python gerar_videos.py --apenas 290                 # gera somente o hino 290
  python gerar_videos.py --forcar-inicio 100          # processa a partir do hino 100
  python gerar_videos.py --resetar 290                # marca o hino 290 como pendente
  python gerar_videos.py --resetar-todos              # marca tudo como pendente
  python gerar_videos.py --hinario hinario5           # processa somente um hinário específico
  python gerar_videos.py --forcar-download            # baixa novos clipes antes de começar
  python gerar_videos.py --sem-download               # nunca acessa a internet
  python gerar_videos.py --vinheta /caminho/vinheta.mp4  # usa vinheta de abertura

Vinheta de abertura:
  A vinheta é inserida antes do frame inicial (número/nome do hino).
  Pode ser definida via argumento --vinheta ou pelo campo "vinheta" em projetos.json.
  O argumento --vinheta tem precedência sobre projetos.json.
  O delay do áudio é ajustado automaticamente: dur_vinheta + FRAME_DURATION.

Dependências:
  pip install Pillow mutagen requests tqdm
  ffmpeg instalado no sistema (brew install ffmpeg)
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont

# =============================================================================
# Caminhos do projeto
# =============================================================================

ROOT         = Path(__file__).parent
FLORES_DIR   = ROOT / "videos_flores"
PHOTOS_DIR   = ROOT / "Photos-1-001"
OUTPUT_DIR   = ROOT / "output"
THUMBS_DIR   = ROOT / "thumbs"   # miniaturas PNG para upload no YouTube
FONTES_DIR   = ROOT / "fontes"
DB_PATH      = ROOT / "progresso.db"
DOWNLOAD_SCRIPT = ROOT / "baixar_videos_flores.py"
LETRAS_DIR   = ROOT / "hinos_txt" / "letras_separadas"  # letras individuais dos hinos

FRAME_DURATION   = 5      # segundos do frame inicial com o número
TRANSITION_SECS  = 1      # duração da transição blur entre clipes

# Sequência de queries de fallback para download automático
DOWNLOAD_QUERIES = ["flores", "flowers", "natureza", "nature", "campo", "jardim", "primavera"]


def carregar_projetos() -> dict:
    caminho = ROOT / "projetos.json"
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo projetos.json não encontrado em {caminho}")
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


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


def carregar_letra_hino(numero, projeto_nome: str = "") -> str:
    """
    Busca a letra do hino/coro no diretório letras_separadas via _indice.csv.
    Retorna o conteúdo do .txt (sem a primeira linha de título) ou string vazia se não encontrado.
    """
    indice_path = LETRAS_DIR / "_indice.csv"
    if not indice_path.exists():
        return ""

    try:
        # Determinar tipo: coro ou hino
        num_str = str(numero).strip()
        is_coro = num_str.upper().startswith("C") and num_str[1:].isdigit()
        if not is_coro:
            is_coro = "coro" in projeto_nome.lower()

        if is_coro:
            if num_str.upper().startswith("C"):
                num_int = int(num_str[1:])
            else:
                try:
                    num_int = int(num_str)
                except ValueError:
                    num_int = 0
            tipo_busca = "coro"
        else:
            try:
                num_int = int(num_str)
            except ValueError:
                return ""
            tipo_busca = "hino"

        with open(indice_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tipo_csv = row.get("tipo", "").strip().lower()
                try:
                    num_csv = int(row.get("numero", "").strip())
                except (ValueError, AttributeError):
                    continue
                if tipo_csv == tipo_busca and num_csv == num_int:
                    arquivo = row.get("arquivo", "").strip()
                    letra_path = LETRAS_DIR / arquivo
                    if letra_path.exists():
                        linhas = letra_path.read_text(encoding="utf-8").splitlines()
                        # Pular a primeira linha (título) e linhas em branco iniciais
                        corpo = linhas[1:] if linhas else []
                        while corpo and not corpo[0].strip():
                            corpo = corpo[1:]
                        return "\n".join(corpo).rstrip()
                    return ""
    except Exception as e:
        print(f"[aviso] Erro ao carregar letra do hino {numero}: {e}")
    return ""


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


# =============================================================================
# Utilitários
# =============================================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def remover_acentos(texto: str) -> str:
    """Remove acentos e caracteres especiais, mantendo letras e números."""
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def camel_case(texto: str) -> str:
    """Converte 'Cristo Jesus Sua mão me dá' → 'CristoJesusSuaMaoMeDa'."""
    sem_acento = remover_acentos(texto)
    palavras = re.findall(r"[A-Za-z0-9]+", sem_acento)
    return "".join(p.capitalize() for p in palavras)


def extrair_numero_mp3(nome: str) -> str | int | None:
    """Extrai o número do hino do nome do arquivo MP3 (ex.: '290.mp3' → 290, 'Coro 001.mp3' → 'C1')."""
    m_coro = re.match(r"^Coro\s+(\d+)", nome, re.IGNORECASE)
    if m_coro:
        return f"C{int(m_coro.group(1))}"
    m = re.match(r"^(\d+)", nome)
    if m:
        return int(m.group(1))
    return None


def formatar_numero_completo(numero) -> str:
    if isinstance(numero, int):
        return f"{numero:03d}"
    num_str = str(numero).strip()
    if num_str.isdigit():
        return f"{int(num_str):03d}"
    if num_str.upper().startswith("C") and num_str[1:].isdigit():
        return f"C{int(num_str[1:]):03d}"
    return num_str


def limpar_nome_hino(nome: str) -> str:
    res = nome.strip()
    if res.lower().endswith(".mp3"):
        res = res[:-4].strip()
    # Remove prefixo tipo "Coro 001- " ou "Coro 001 -" ou "Coro 1 -"
    res = re.sub(r"^Coro\s+\d+\s*-\s*", "", res, flags=re.IGNORECASE)
    res = re.sub(r"^Coro\s+\w+\s*-\s*", "", res, flags=re.IGNORECASE)
    return res.strip()


def duracao_mp3(caminho: Path) -> float:
    """Retorna a duração em segundos de um arquivo MP3."""
    try:
        audio = MP3(str(caminho))
        if audio.info.length > 0.0:
            return audio.info.length
    except Exception:
        pass

    # Fallback para ffprobe se o mutagen falhar ou retornar 0.0
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(caminho),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def duracao_video(caminho: Path) -> float:
    """Retorna a duração em segundos de um arquivo de vídeo via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(caminho),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


# =============================================================================
# Banco de dados
# =============================================================================

def abrir_banco() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # Migra primeiro, depois habilita foreign keys e cria tabelas
    migrar_banco_para_projetos(conn)
    conn.execute("PRAGMA foreign_keys=ON")
    _criar_tabelas(conn)
    return conn


def migrar_banco_para_projetos(conn: sqlite3.Connection):
    cursor = conn.execute("PRAGMA table_info(videos)")
    cols = [r[1] for r in cursor.fetchall()]
    if not cols:
        return
        
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
                conn.execute(f"""
                    INSERT INTO videos (projeto, numero, mp3_file, hinario, status, output, erro_msg, criado_em, atualizado_em, data_postagem)
                    SELECT 'hinario4', {cols_to_copy} FROM _videos_old
                """)
            else:
                conn.execute(f"""
                    INSERT INTO videos (projeto, numero, mp3_file, hinario, status, output, erro_msg, criado_em, atualizado_em)
                    SELECT 'hinario4', {cols_to_copy} FROM _videos_old
                """)
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
                conn.execute("""
                    INSERT INTO clipes (id, caminho, fonte, duracao_s, projeto_usado, usado_em, vezes_usado)
                    SELECT id, caminho, fonte, duracao_s, 
                           CASE WHEN usado_em IS NOT NULL THEN 'hinario4' ELSE NULL END, 
                           usado_em,
                           CASE WHEN usado_em IS NOT NULL THEN 1 ELSE 0 END
                    FROM _clipes_old
                """)
                conn.execute("DROP TABLE _clipes_old")
                
            conn.commit()
            print("[banco] Migração concluída com sucesso.")
        except Exception as e:
            conn.execute("ROLLBACK")
            print(f"[banco] ERRO na migração: {e}")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")


def _criar_tabelas(conn: sqlite3.Connection):
    # Garantir que a coluna vezes_usado existe na tabela clipes (para bancos de dados já criados)
    c_cursor = conn.execute("PRAGMA table_info(clipes)")
    c_cols = [r[1] for r in c_cursor.fetchall()]
    if c_cols and "vezes_usado" not in c_cols:
        print("[banco] Adicionando coluna 'vezes_usado' na tabela 'clipes'...")
        conn.execute("ALTER TABLE clipes ADD COLUMN vezes_usado INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE clipes SET vezes_usado = 1 WHERE projeto_usado IS NOT NULL OR usado_em IS NOT NULL")
        conn.commit()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
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
        );

        CREATE TABLE IF NOT EXISTS clipes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            caminho        TEXT UNIQUE NOT NULL,
            fonte          TEXT,
            duracao_s      REAL,
            projeto_usado  TEXT,
            usado_em       INTEGER,
            vezes_usado    INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (projeto_usado, usado_em) REFERENCES videos(projeto, numero)
        );

        CREATE TABLE IF NOT EXISTS downloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            provider    TEXT,
            provider_id TEXT,
            query       TEXT,
            caminho     TEXT UNIQUE,
            baixado_em  TEXT
        );

        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        );
    """)
    conn.commit()


def config_get(conn: sqlite3.Connection, chave: str, default: str = "") -> str:
    row = conn.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    return row["valor"] if row else default


def config_set(conn: sqlite3.Connection, chave: str, valor: str):
    conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (chave, valor))
    conn.commit()


# =============================================================================
# Sincronização de dados
# =============================================================================

def sincronizar_mp3s(conn: sqlite3.Connection, projeto_nome: str, projeto_cfg: dict):
    """Insere na tabela videos os MP3s que ainda não estão registrados para o projeto."""
    existentes = {
        row["numero"]
        for row in conn.execute("SELECT numero FROM videos WHERE projeto = ?", (projeto_nome,))
    }
    inseridos = 0
    mp3_dir = ROOT / projeto_cfg.get("mp3_dir", "mp3")
    if not mp3_dir.exists():
        print(f"[banco] Diretório de MP3 não existe: {mp3_dir}")
        return
    for mp3 in sorted(mp3_dir.glob("*.mp3")):
        numero = extrair_numero_mp3(mp3.name)
        if numero is None or numero in existentes:
            continue
        # Filtro específico para o projeto 'coros'
        if projeto_nome == "coros" and not str(numero).upper().startswith("C"):
            continue
        conn.execute(
            "INSERT OR IGNORE INTO videos (projeto, numero, mp3_file, hinario, status, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, ?, 'pendente', ?, ?)",
            (projeto_nome, numero, str(mp3.relative_to(ROOT)), projeto_nome, now_iso(), now_iso()),
        )
        inseridos += 1
    # Hinos presos em 'processando' (interrupção abrupta) voltam para pendente para este projeto
    conn.execute(
        "UPDATE videos SET status = 'pendente', atualizado_em = ? WHERE status = 'processando' AND projeto = ?",
        (now_iso(), projeto_nome),
    )
    conn.commit()
    if inseridos:
        print(f"[banco] {inseridos} novo(s) MP3(s) registrado(s) para o projeto '{projeto_nome}'.")


def sincronizar_clipes(conn: sqlite3.Connection):
    """Insere na tabela clipes os vídeos novos de videos_flores/ e Photos-1-001/."""
    inseridos = 0
    extensoes = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    def escanear(pasta: Path, fonte: str):
        nonlocal inseridos
        if not pasta.exists():
            return
        for f in pasta.iterdir():
            if f.suffix.lower() not in extensoes:
                continue
            rel = str(f.relative_to(ROOT))
            existe = conn.execute(
                "SELECT 1 FROM clipes WHERE caminho = ?", (rel,)
            ).fetchone()
            if existe:
                continue
            dur = duracao_video(f)
            conn.execute(
                "INSERT OR IGNORE INTO clipes (caminho, fonte, duracao_s) VALUES (?, ?, ?)",
                (rel, fonte, dur),
            )
            inseridos += 1

    escanear(FLORES_DIR, "videos_flores")
    escanear(PHOTOS_DIR, "photos")
    conn.commit()
    if inseridos:
        print(f"[banco] {inseridos} novo(s) clipe(s) registrado(s).")


# =============================================================================
# Download automático de clipes
# =============================================================================

def clipes_disponiveis(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM clipes WHERE projeto_usado IS NULL AND usado_em IS NULL").fetchone()
    return row["n"]


def baixar_mais_clipes(conn: sqlite3.Connection):
    """Chama baixar_videos_flores.py com a próxima query disponível."""
    ultima = config_get(conn, "ultima_query_download", "")
    if ultima in DOWNLOAD_QUERIES:
        idx = DOWNLOAD_QUERIES.index(ultima) + 1
    else:
        idx = 0

    if idx >= len(DOWNLOAD_QUERIES):
        print("[download] Todas as queries já foram tentadas. Adicione novas chaves ou queries.")
        return

    query = DOWNLOAD_QUERIES[idx]
    config_set(conn, "ultima_query_download", query)
    print(f"[download] Pool esgotado. Baixando novos vídeos com query: '{query}' ...")

    env = os.environ.copy()
    cmd = [
        sys.executable, str(DOWNLOAD_SCRIPT),
        "--query", query,
        "--out", str(FLORES_DIR),
        "--providers", "pexels,pixabay",
        "--per-page", "40",
        "--max-pages", "5",
        "--orientation", "landscape",
    ]
    subprocess.run(cmd, env=env, check=False)
    sincronizar_clipes(conn)


# =============================================================================
# Carregamento do CSV
# =============================================================================

def carregar_csv(caminho: Path) -> dict:
    """Retorna dicionário {numero: nome} a partir do CSV do hinário com suporte a colunas dinâmicas."""
    hinos = {}
    with open(caminho, newline="", encoding="utf-8-sig") as f:
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
    return hinos


# =============================================================================
# Geração do frame inicial (número sobre a imagem)
# =============================================================================

def draw_text_effects(draw, pos, text, font, fill_color, config_desenho, is_multiline=False):
    x, y = pos
    sombra = config_desenho.get("sombra")
    brilho = config_desenho.get("brilho")
    
    # 1. Desenhar brilho (glow) se configurado
    if brilho:
        raio = brilho.get("raio", 2)
        cor_brilho = tuple(brilho.get("cor", [255, 255, 255, 255]))
        for dx in range(-raio, raio + 1):
            for dy in range(-raio, raio + 1):
                if dx*dx + dy*dy <= raio*raio and (dx != 0 or dy != 0):
                    if is_multiline:
                        draw.multiline_text((x + dx, y + dy), text, font=font, fill=cor_brilho)
                    else:
                        draw.text((x + dx, y + dy), text, font=font, fill=cor_brilho)
                        
    # 2. Desenhar sombra (drop shadow) se configurada
    elif sombra:
        dx, dy = sombra.get("deslocamento", [3, 3])
        cor_sombra = tuple(sombra.get("cor", [0, 0, 0, 128]))
        if is_multiline:
            draw.multiline_text((x + dx, y + dy), text, font=font, fill=cor_sombra)
        else:
            draw.text((x + dx, y + dy), text, font=font, fill=cor_sombra)
            
    # 3. Desenhar o texto principal
    if is_multiline:
        draw.multiline_text((x, y), text, font=font, fill=fill_color)
    else:
        draw.text((x, y), text, font=font, fill=fill_color)


def desenhar_texto_campo(draw, texto, config_desenho, W, H, is_num=False):
    x = config_desenho.get("x", 139)
    y_top = config_desenho.get("y_top", 169)
    y_bottom = config_desenho.get("y_bottom", 767)
    cor = tuple(config_desenho.get("cor", [26, 45, 90, 255]))
    align = config_desenho.get("align", "left")
    
    target_h = y_bottom - y_top
    max_w = config_desenho.get("max_width", W - x - 50)
    
    font = None
    wrapped_text = texto
    
    font_paths = [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/Library/Fonts/Georgia.ttf",
        "/System/Library/Fonts/Times.ttc",
    ]
    
    # Determine max font size
    default_max_size = target_h if is_num else 42
    max_size = config_desenho.get("max_font_size", default_max_size)
    
    for path in font_paths:
        try:
            # We decrease size until it fits
            for size in range(max_size, 12, -2):
                candidate = ImageFont.truetype(path, size=size)
                
                # If it's a number, we don't wrap it
                if is_num:
                    lines = [texto]
                else:
                    # Wrap the text
                    lines = []
                    current_line = []
                    for word in texto.split(' '):
                        test_line = ' '.join(current_line + [word])
                        bbox = draw.textbbox((0, 0), test_line, font=candidate)
                        w = bbox[2] - bbox[0]
                        if w <= max_w:
                            current_line.append(word)
                        else:
                            if current_line:
                                lines.append(' '.join(current_line))
                                current_line = [word]
                            else:
                                lines.append(word)
                                current_line = []
                    if current_line:
                        lines.append(' '.join(current_line))
                
                wrapped_candidate = '\n'.join(lines)
                bbox = draw.multiline_textbbox((0, 0), wrapped_candidate, font=candidate)
                h = bbox[3] - bbox[1]
                w = bbox[2] - bbox[0]
                
                # Check height and width
                if h <= target_h and w <= max_w:
                    font = candidate
                    wrapped_text = wrapped_candidate
                    break
            if font:
                break
        except OSError:
            continue
            
    if font is None:
        font = ImageFont.load_default()
        wrapped_text = texto
        
    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
    ascent_offset = bbox[1]
    y = y_top - ascent_offset
    
    if align == "center":
        for line in wrapped_text.split('\n'):
            line_bbox = draw.textbbox((0, 0), line, font=font)
            line_w = line_bbox[2] - line_bbox[0]
            draw_text_effects(draw, (x + (max_w - line_w) // 2, y), line, font, cor, config_desenho, is_multiline=False)
            y += (line_bbox[3] - line_bbox[1]) + 5
    elif align == "right":
        for line in wrapped_text.split('\n'):
            line_bbox = draw.textbbox((0, 0), line, font=font)
            line_w = line_bbox[2] - line_bbox[0]
            draw_text_effects(draw, (x + max_w - line_w, y), line, font, cor, config_desenho, is_multiline=False)
            y += (line_bbox[3] - line_bbox[1]) + 5
    else:
        draw_text_effects(draw, (x, y), wrapped_text, font, cor, config_desenho, is_multiline=True)


def gerar_thumbnail_hino(numero: int, nome: str, projeto_nome: str, projeto_cfg: dict) -> Path:
    """
    Renderiza o número e o nome do hino sobre a imagem base e salva como PNG.
    """
    imagem_base_path = ROOT / projeto_cfg.get("imagem_base", "images/sem-numero.png")
    if not imagem_base_path.exists():
        raise FileNotFoundError(f"Imagem base não encontrada: {imagem_base_path}")
        
    img = Image.open(imagem_base_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size
    
    desenho_num = projeto_cfg.get("desenho", {}).get("numero", {})
    num_str = str(numero).strip()
    if num_str.upper().startswith("C") and num_str[1:].isdigit():
        texto_numero = f"Coro {int(num_str[1:])}"
    elif "coro" in projeto_nome.lower():
        texto_numero = f"Coro {numero}"
    else:
        texto_numero = str(numero)
    desenhar_texto_campo(draw, texto_numero, desenho_num, W, H, is_num=True)
    
    # 2. Desenhar o nome do hino
    desenho_nome = projeto_cfg.get("desenho", {}).get("nome", {})
    desenhar_texto_campo(draw, nome, desenho_nome, W, H, is_num=False)
    
    # --- Salvar thumbnail para o YouTube em thumbs/ --------------------------
    THUMBS_DIR.mkdir(exist_ok=True)
    num_formatted = formatar_numero_completo(numero)
    thumb_path = THUMBS_DIR / f"hino-{projeto_nome}-{num_formatted}.png"
    img.convert("RGB").save(str(thumb_path))
    return thumb_path


def gerar_frame_video(numero: int, nome: str, projeto_nome: str, projeto_cfg: dict, duracao: int = FRAME_DURATION) -> Path:
    """
    Renderiza a imagem base e cria um arquivo MP4 temporário estático.
    """
    thumb_path = gerar_thumbnail_hino(numero, nome, projeto_nome, projeto_cfg)
    num_formatted = formatar_numero_completo(numero)
    print(f"  Thumbnail salva em: thumbs/hino-{projeto_nome}-{num_formatted}.png")
    
    # --- Gerar vídeo estático temporário -------------------------------------
    OUTPUT_DIR.mkdir(exist_ok=True)
    frame_mp4 = OUTPUT_DIR / f"_frame_{projeto_nome}_{numero}.mp4"
    
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1",
        "-i", str(thumb_path),
        "-t", str(duracao),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-threads", "4",
        "-r", "30",
        str(frame_mp4),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    return frame_mp4


# =============================================================================
# Composição do vídeo de fundo
# =============================================================================

def selecionar_clipes(conn: sqlite3.Connection, duracao_necessaria: float,
                      sem_download: bool, projeto_nome: str, numero: int) -> list[tuple[str, float]]:
    """
    Seleciona clipes locais (videos_flores/ e Photos-1-001/) ordenados por vezes_usado ASC, RANDOM().
    Retorna lista de (caminho_absoluto, duracao_s).
    Não realiza downloads da internet.
    Garante que não repete o mesmo clipe dentro do mesmo vídeo, a não ser que não existam outros clipes.
    """
    selecionados: list[tuple[str, float]] = []
    total = 0.0
    ids_selecionados: list[int] = []

    while total < duracao_necessaria:
        # Procurar clipes excluindo os já selecionados para esta composição atual
        query = "SELECT id, caminho, duracao_s, vezes_usado FROM clipes"
        params = []
        if ids_selecionados:
            placeholders = ",".join("?" for _ in ids_selecionados)
            query += f" WHERE id NOT IN ({placeholders})"
            params.extend(ids_selecionados)
            
        query += " ORDER BY vezes_usado ASC, RANDOM() LIMIT 1"
        
        row = conn.execute(query, params).fetchone()
        
        if row is None:
            # Se não há mais clipes excluindo os já selecionados (por ex. a duração exigida
            # é muito longa ou há pouquíssimos clipes no total), limpamos ids_selecionados
            # para permitir repetir clipes no mesmo vídeo se necessário.
            if ids_selecionados:
                print("  [aviso] Clipes únicos esgotados para este vídeo, permitindo repetições.")
                ids_selecionados = []
                continue
            else:
                raise RuntimeError("Nenhum clipe disponível no banco de dados. Certifique-se de que os arquivos locais existem e foram sincronizados.")

        caminho = ROOT / row["caminho"]
        if not caminho.exists():
            print(f"  [aviso] Clipe não encontrado, pulando e removendo do banco: {caminho.name}")
            conn.execute("DELETE FROM clipes WHERE id = ?", (row["id"],))
            conn.commit()
            continue

        dur = row["duracao_s"] or duracao_video(caminho)
        
        # Incrementar a contagem vezes_usado e atualizar o projeto_usado/usado_em para rastreamento
        conn.execute(
            "UPDATE clipes SET vezes_usado = vezes_usado + 1, projeto_usado = ?, usado_em = ? WHERE id = ?",
            (projeto_nome, numero, row["id"])
        )
        conn.commit()

        selecionados.append((str(caminho), dur))
        ids_selecionados.append(row["id"])
        total += dur

    return selecionados


def compor_video_fundo(clipes: list[tuple[str, float]], duracao_total: float,
                       saida: Path) -> Path:
    """
    Monta o vídeo de fundo concatenando os clipes.
    Usa o concat demuxer do ffmpeg (via arquivo de lista) — robusto para
    qualquer quantidade de clipes, sem SIGSEGV causado por filter_complex longo.
    Corta no final para exatamente duracao_total segundos.
    """
    if len(clipes) == 1:
        caminho, dur = clipes[0]
        clipes_expandidos = []
        total = 0.0
        while total < duracao_total + 2:
            clipes_expandidos.append((caminho, dur))
            total += dur
        clipes = clipes_expandidos

    # --- Normalizar cada clipe; pular corrompidos ---
    partes: list[Path] = []
    out_dir = saida.parent
    for i, (caminho, _) in enumerate(clipes):
        parte = out_dir / f"_parte_{saida.stem}_{i}.mp4"
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", caminho,
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                       "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-threads", "4",
                "-an",
                str(parte),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            partes.append(parte)
        except subprocess.CalledProcessError:
            print(f"  [aviso] Clipe problemático ignorado: {Path(caminho).name}")
            parte.unlink(missing_ok=True)

    if not partes:
        raise RuntimeError("Todos os clipes selecionados falharam na normalização.")

    # --- Concatenar via concat demuxer (sem limite de clipes, sem SIGSEGV) ---
    lista_txt = out_dir / f"_lista_{saida.stem}_bg.txt"
    lista_txt.write_text(
        "\n".join(f"file '{p.name}'" for p in partes) + "\n",
        encoding="utf-8",
    )

    video_concat = out_dir / f"_concat_{saida.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", lista_txt.name,
        "-c", "copy",
        video_concat.name,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(out_dir))

    lista_txt.unlink(missing_ok=True)
    for p in partes:
        p.unlink(missing_ok=True)

    # --- Cortar exatamente na duração necessária ---
    video_cortado = out_dir / f"_fundo_{saida.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_concat),
        "-t", str(duracao_total),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-threads", "4",
        str(video_cortado),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    video_concat.unlink(missing_ok=True)

    return video_cortado


# =============================================================================
# Vinheta de abertura
# =============================================================================

def preparar_vinheta(vinheta_path: Path, saida_dir: Path) -> tuple[Path, Path | None]:
    """
    Normaliza o arquivo de vinheta para 1920×1080, libx264, 30fps.
    O vídeo normalizado é gerado SEM áudio (para que o concat demuxer funcione
    uniformemente junto ao frame e ao fundo, que também não têm áudio).
    Se a vinheta contiver uma faixa de áudio, ela é extraída e codificada
    separadamente em AAC — será misturada no passo de montagem final.

    Retorna:
        (vinheta_video_norm, vinheta_audio_norm)  — audio_norm é None se não houver áudio.
    """
    if not vinheta_path.exists():
        raise FileNotFoundError(f"Arquivo de vinheta não encontrado: {vinheta_path}")

    # 1. Normalizar vídeo (sem áudio)
    vinheta_v = saida_dir / f"_vinheta_v_{vinheta_path.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(vinheta_path),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-threads", "4",
        "-an",
        str(vinheta_v),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. Verificar se a vinheta possui faixa de áudio
    probe = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(vinheta_path),
    ], capture_output=True, text=True)

    vinheta_a: Path | None = None
    if probe.stdout.strip():
        # Extrair e re-codificar o áudio da vinheta em AAC
        vinheta_a = saida_dir / f"_vinheta_a_{vinheta_path.stem}.aac"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(vinheta_path),
            "-vn", "-c:a", "aac", "-b:a", "192k",
            str(vinheta_a),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return vinheta_v, vinheta_a


# =============================================================================
# Montagem final: [vinheta +] frame + vídeo de fundo + áudio
# =============================================================================

def montar_video_final(frame_mp4: Path, fundo_mp4: Path,
                       mp3: Path, saida: Path, dur_mp3: float,
                       vinheta_mp4: Path | None = None,
                       vinheta_audio: Path | None = None):
    """
    Concatena [vinheta +] frame inicial + vídeo de fundo, adiciona áudio e salva.

    Faixas de áudio no vídeo final:
      - Se vinheta_audio for fornecida: o áudio original da vinheta é preservado
        e misturado (amix) com o MP3 do hino (que começa após dur_vinheta + FRAME_DURATION).
        As duas faixas não se sobrepõem: a vinheta ocupa 0→dur_vinheta e o MP3
        começa em dur_vinheta + FRAME_DURATION.
      - Se não houver áudio na vinheta: comportamento original — apenas o MP3
        com adelay.

    O vídeo da vinheta (vinheta_mp4) deve ser passado SEM áudio (normalizado por
    preparar_vinheta) para que o concat demuxer funcione uniformemente com o
    frame e o fundo, que também não possuem faixa de áudio.

    Usa nomes relativos no arquivo de lista do ffmpeg concat para evitar
    erros com caminhos contendo caracteres especiais (acentos, ç etc.).
    """
    out_dir = saida.parent
    lista = out_dir / f"_lista_{saida.stem}.txt"

    # Monta a lista de partes (todas sem áudio): [vinheta_v], frame, fundo
    entradas = []
    if vinheta_mp4 is not None:
        entradas.append(vinheta_mp4.relative_to(out_dir))
    entradas.append(frame_mp4.relative_to(out_dir))
    entradas.append(fundo_mp4.relative_to(out_dir))

    lista.write_text(
        "\n".join(f"file '{p}'" for p in entradas) + "\n",
        encoding="utf-8",
    )

    video_concat = out_dir / f"_tmp_{saida.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", lista.name,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-threads", "4",
        video_concat.name,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(out_dir))
    lista.unlink(missing_ok=True)

    # Calcular o delay do MP3: começa após vinheta + frame inicial
    dur_vinheta = duracao_video(vinheta_mp4) if vinheta_mp4 is not None else 0.0
    audio_delay_s = dur_vinheta + FRAME_DURATION
    audio_delay_ms = int(audio_delay_s * 1000)
    total_dur = audio_delay_s + dur_mp3

    if vinheta_audio is not None:
        # Misturar: áudio da vinheta (natural) + MP3 com delay via amix.
        # As faixas não se sobrepõem: vinheta 0→dur_vinheta, MP3 começa em audio_delay_s.
        # [va] — áudio da vinheta preenchido com silêncio até total_dur
        # [ma] — MP3 atrasado, com fade-in e preenchido até total_dur
        # amix com normalize=0 garante que os volumes não sejam reduzidos.
        filter_complex = (
            f"[1:a]apad=whole_dur={total_dur}[va];"
            f"[2:a]adelay={audio_delay_ms}|{audio_delay_ms},"
            f"afade=t=in:st={audio_delay_s}:d=0.5,"
            f"apad=whole_dur={total_dur}[ma];"
            f"[va][ma]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_concat),   # 0: vídeo
            "-i", str(vinheta_audio),  # 1: áudio da vinheta
            "-i", str(mp3),            # 2: MP3 do hino
            "-map", "0:v:0",
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_dur:.3f}",
            str(saida),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Sem áudio de vinheta — apenas o MP3 com delay (comportamento original)
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_concat),
            "-i", str(mp3),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-af", f"adelay={audio_delay_ms}|{audio_delay_ms},"
                   f"afade=t=in:st={audio_delay_s}:d=0.5,"
                   f"apad=whole_dur={total_dur}",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_dur:.3f}",
            str(saida),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    video_concat.unlink(missing_ok=True)


# =============================================================================
# Geração dos metadados para YouTube
# =============================================================================

def gerar_metadados(numero: int, nome: str, projeto_nome: str, projeto_cfg: dict) -> str:
    tag_hino = f"Hino{numero}"
    tag_nome = camel_case(nome)
    nome_sem_acento = remover_acentos(nome).lower()

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
        "nome_sem_acento": nome_sem_acento,
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

    # Carregar letra do hino e inserir na descrição
    letra = carregar_letra_hino(numero, projeto_nome)
    if letra:
        # Inserir a letra após a apresentação, antes das hashtags (#Hino...)
        # Estratégia: separar a descrição na primeira linha que começa com "#"
        linhas_desc = descricao.splitlines()
        idx_hashtag = next(
            (i for i, ln in enumerate(linhas_desc) if ln.strip().startswith("#")),
            None
        )
        if idx_hashtag is not None:
            parte_apresentacao = "\n".join(linhas_desc[:idx_hashtag]).rstrip()
            parte_hashtags = "\n".join(linhas_desc[idx_hashtag:])
            descricao = (
                parte_apresentacao
                + "\n\n📜 Letra:\n\n"
                + letra
                + "\n\n"
                + parte_hashtags
            )
        else:
            descricao = descricao.rstrip() + "\n\n📜 Letra:\n\n" + letra

    return f"""# {numero}

## Título para o vídeo
{titulo}


## Descrição para o YouTube

{descricao}


## Tags para YouTube

{tags}

---
"""


def acrescentar_metadados(numero: int, nome: str, projeto_nome: str, projeto_cfg: dict):
    """Acrescenta (não sobrescreve) a entrada do hino no arquivo de metadados do projeto."""
    conteudo = gerar_metadados(numero, nome, projeto_nome, projeto_cfg)
    metadata_out = ROOT / f"videos_gerados_{projeto_nome}.md"
    with open(metadata_out, "a", encoding="utf-8") as f:
        f.write(conteudo + "\n")


# =============================================================================
# Loop principal
# =============================================================================

def processar_hino(numero: int, mp3_path: Path, nome: str,
                   conn: sqlite3.Connection, sem_download: bool,
                   projeto_nome: str, projeto_cfg: dict,
                   vinheta_path: Path | None = None):
    """Gera o vídeo completo para um único hino do projeto.

    Se vinheta_path for fornecida, ela será inserida antes do frame inicial.
    Caso contrário, verifica o campo 'vinheta' em projeto_cfg.
    """
    num_formatted = formatar_numero_completo(numero)
    print(f"\n[hino {num_formatted}] {nome} (Projeto: {projeto_nome})")

    # Resolver vinheta: argumento CLI > projetos.json > nenhuma
    vinheta_efetiva: Path | None = vinheta_path
    if vinheta_efetiva is None:
        vinheta_cfg = projeto_cfg.get("vinheta", "")
        if vinheta_cfg:
            candidata = Path(vinheta_cfg)
            if not candidata.is_absolute():
                candidata = ROOT / candidata
            vinheta_efetiva = candidata if candidata.exists() else None
            if vinheta_efetiva is None:
                print(f"  [aviso] Vinheta configurada não encontrada: {vinheta_cfg}")

    if vinheta_efetiva:
        print(f"  Vinheta de abertura: {vinheta_efetiva.name}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    saida = OUTPUT_DIR / f"hino-{projeto_nome}-{num_formatted}.mp4"

    # Apagar o vídeo final existente e quaisquer temporários de uma run anterior
    saida.unlink(missing_ok=True)
    for tmp in OUTPUT_DIR.glob(f"_*_{projeto_nome}_{numero}*.mp4"):
        tmp.unlink(missing_ok=True)
    for tmp in OUTPUT_DIR.glob(f"_*hino-{projeto_nome}-{num_formatted}*.mp4"):
        tmp.unlink(missing_ok=True)
    for tmp in OUTPUT_DIR.glob(f"_lista_hino-{projeto_nome}-{num_formatted}.txt"):
        tmp.unlink(missing_ok=True)

    conn.execute(
        "UPDATE videos SET status = 'processando', atualizado_em = ? WHERE projeto = ? AND numero = ?",
        (now_iso(), projeto_nome, numero),
    )
    conn.commit()

    vinheta_norm: Path | None = None
    vinheta_audio_norm: Path | None = None
    try:
        dur_mp3 = duracao_mp3(mp3_path)
        print(f"  Duração do MP3: {dur_mp3:.1f}s")

        # 1. Normalizar vinheta (se houver)
        if vinheta_efetiva:
            print("  Normalizando vinheta de abertura...")
            vinheta_norm, vinheta_audio_norm = preparar_vinheta(vinheta_efetiva, OUTPUT_DIR)
            dur_vin = duracao_video(vinheta_norm)
            tem_audio = "com áudio" if vinheta_audio_norm else "sem áudio"
            print(f"  Duração da vinheta: {dur_vin:.1f}s ({tem_audio})")

        # 2. Frame inicial
        print("  Gerando frame inicial...")
        frame_mp4 = gerar_frame_video(numero, nome, projeto_nome, projeto_cfg)

        # 3. Selecionar e compor vídeo de fundo
        print("  Selecionando clipes de fundo...")
        clipes = selecionar_clipes(conn, dur_mp3, sem_download, projeto_nome, numero)
        print(f"  {len(clipes)} clipe(s) selecionado(s).")

        print("  Compondo vídeo de fundo...")
        fundo_mp4 = compor_video_fundo(clipes, dur_mp3, saida)

        # 4. Montagem final
        print("  Montando vídeo final...")
        montar_video_final(frame_mp4, fundo_mp4, mp3_path, saida, dur_mp3,
                           vinheta_mp4=vinheta_norm,
                           vinheta_audio=vinheta_audio_norm)

        # 5. Limpeza de temporários
        frame_mp4.unlink(missing_ok=True)
        fundo_mp4.unlink(missing_ok=True)
        if vinheta_norm:
            vinheta_norm.unlink(missing_ok=True)
        if vinheta_audio_norm:
            vinheta_audio_norm.unlink(missing_ok=True)

        # 6. Registrar sucesso
        conn.execute(
            "UPDATE videos SET status = 'concluido', output = ?, atualizado_em = ? WHERE projeto = ? AND numero = ?",
            (str(saida.relative_to(ROOT)), now_iso(), projeto_nome, numero),
        )
        conn.commit()

        # 7. Metadados YouTube
        acrescentar_metadados(numero, nome, projeto_nome, projeto_cfg)
        print(f"  ✓ Salvo em: {saida.relative_to(ROOT)}")

    except Exception as e:
        if vinheta_norm:
            vinheta_norm.unlink(missing_ok=True)
        if vinheta_audio_norm:
            vinheta_audio_norm.unlink(missing_ok=True)
        conn.execute(
            "UPDATE videos SET status = 'erro', erro_msg = ?, atualizado_em = ? WHERE projeto = ? AND numero = ?",
            (str(e), now_iso(), projeto_nome, numero),
        )
        conn.commit()
        print(f"  ✗ ERRO: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Gerador de vídeos para o Hinário CCB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apenas", type=str, metavar="NUMERO",
                        help="Processa somente este hino.")
    parser.add_argument("--forcar-inicio", type=int, metavar="NUMERO",
                        help="Começa a partir deste número.")
    parser.add_argument("--resetar", type=str, metavar="NUMERO",
                        help="Marca um hino como pendente e libera seus clipes.")
    parser.add_argument("--resetar-todos", action="store_true",
                        help="Marca todos os hinos como pendente.")
    parser.add_argument("--projeto", default=None,
                        help="Nome do projeto a ser executado (ex.: hinario4).")
    parser.add_argument("--hinario", default=None,
                        help="Depreciado (use --projeto). Filtra por hinário.")
    parser.add_argument("--forcar-download", action="store_true",
                        help="Baixa novos clipes antes de começar.")
    parser.add_argument("--sem-download", action="store_true",
                        help="Nunca acessa a internet para baixar clipes.")
    parser.add_argument("--apenas-imagem", action="store_true",
                        help="Gera somente a imagem de miniatura (thumbnail) do hino, sem renderizar o vídeo.")
    parser.add_argument("--vinheta", type=str, default=None, metavar="ARQUIVO",
                        help="Caminho para o vídeo de vinheta de abertura (MP4). "
                             "Tem precedência sobre o campo 'vinheta' em projetos.json.")
    args = parser.parse_args()

    projetos = carregar_projetos()
    projeto_nome = args.projeto or args.hinario
    if not projeto_nome:
        projeto_nome = list(projetos.keys())[0]

    if projeto_nome not in projetos:
        print(f"ERRO: Projeto '{projeto_nome}' não está configurado em projetos.json.")
        sys.exit(1)

    projeto_cfg = projetos[projeto_nome]
    conn = abrir_banco()

    apenas_val = args.apenas
    if apenas_val is not None:
        try:
            apenas_val = int(apenas_val)
        except ValueError:
            pass

    resetar_val = args.resetar
    if resetar_val is not None:
        try:
            resetar_val = int(resetar_val)
        except ValueError:
            pass

    # ---- Operações de reset ------------------------------------------------
    if args.resetar_todos:
        conn.execute(
            "UPDATE videos SET status = 'pendente', atualizado_em = ? WHERE projeto = ?",
            (now_iso(), projeto_nome),
        )
        conn.execute(
            "UPDATE clipes SET vezes_usado = MAX(0, vezes_usado - 1), projeto_usado = NULL, usado_em = NULL WHERE projeto_usado = ?",
            (projeto_nome,),
        )
        conn.commit()
        print(f"[reset] Todos os hinos do projeto '{projeto_nome}' marcados como pendente.")
        return

    if resetar_val is not None:
        conn.execute(
            "UPDATE clipes SET vezes_usado = MAX(0, vezes_usado - 1), projeto_usado = NULL, usado_em = NULL WHERE projeto_usado = ? AND usado_em = ?",
            (projeto_nome, resetar_val),
        )
        conn.execute(
            "UPDATE videos SET status = 'pendente', output = NULL, erro_msg = NULL, atualizado_em = ? "
            "WHERE projeto = ? AND numero = ?",
            (now_iso(), projeto_nome, resetar_val),
        )
        conn.commit()
        print(f"[reset] Hino {resetar_val} do projeto '{projeto_nome}' marcado como pendente.")
        return

    # ---- Inicialização -----------------------------------------------------
    sincronizar_mp3s(conn, projeto_nome, projeto_cfg)
    sincronizar_clipes(conn)

    if args.forcar_download:
        baixar_mais_clipes(conn)

    # ---- Resolver vinheta (argumento CLI) ----------------------------------
    vinheta_arg: Path | None = None
    if args.vinheta:
        candidata = Path(args.vinheta)
        if not candidata.is_absolute():
            candidata = Path.cwd() / candidata
        if not candidata.exists():
            print(f"[erro] Vinheta não encontrada: {candidata}")
            sys.exit(1)
        vinheta_arg = candidata
        print(f"[vinheta] Usando vinheta de abertura: {vinheta_arg}")

    csv_path = ROOT / projeto_cfg.get("csv_path", "fontes/hinario4_sequential.csv")
    hinos = carregar_csv(csv_path)

    # ---- Seleção de hinos a processar --------------------------------------
    if apenas_val is not None:
        query = "SELECT numero, mp3_file FROM videos WHERE projeto = ? AND numero = ?"
        params = [projeto_nome, apenas_val]
    else:
        query = "SELECT numero, mp3_file FROM videos WHERE status = 'pendente' AND projeto = ?"
        params = [projeto_nome]
        
        if args.forcar_inicio:
            query += " AND numero >= ?"
            params.append(args.forcar_inicio)

    query += " ORDER BY numero"
    pendentes = conn.execute(query, params).fetchall()

    if not pendentes:
        print(f"Nada a processar para o projeto '{projeto_nome}'.")
        return

    if args.apenas_imagem:
        print(f"\nGerando apenas {len(pendentes)} imagem(ns) de miniatura (thumbnail) para o projeto '{projeto_nome}'...\n")
    else:
        print(f"\n{len(pendentes)} hino(s) a processar no projeto '{projeto_nome}'.\n")

    mp3s_nao_encontrados: list[tuple] = []

    for row in pendentes:
        numero = row["numero"]
        mp3_path = ROOT / row["mp3_file"]
        num_key = numero
        if isinstance(numero, str) and numero.upper().startswith("C") and numero[1:].isdigit():
            try:
                num_key = int(numero[1:])
            except ValueError:
                pass
        raw_nome = hinos.get(numero) or hinos.get(num_key) or f"Hino {numero}"
        nome = limpar_nome_hino(raw_nome)

        if not mp3_path.exists():
            print(f"[aviso] MP3 não encontrado: {mp3_path} — pulando.")
            mp3s_nao_encontrados.append((numero, nome, str(mp3_path.relative_to(ROOT))))
            continue

        if args.apenas_imagem:
            print(f"[imagem] Gerando thumbnail do hino {formatar_numero_completo(numero)} - {nome}")
            gerar_thumbnail_hino(numero, nome, projeto_nome, projeto_cfg)
            continue

        processar_hino(numero, mp3_path, nome, conn, args.sem_download, projeto_nome, projeto_cfg,
                       vinheta_path=vinheta_arg)

    conn.close()

    # ---- Relatório final de MP3s não encontrados ----------------------------
    if mp3s_nao_encontrados:
        print(f"\n{'='*60}")
        print(f"⚠️  RELATÓRIO: {len(mp3s_nao_encontrados)} MP3(s) não encontrado(s) no projeto '{projeto_nome}'")
        print(f"{'='*60}")
        for num, nome, caminho in mp3s_nao_encontrados:
            num_fmt = formatar_numero_completo(num)
            print(f"  [{num_fmt}] {nome}")
            print(f"        Esperado em: {caminho}")
        print(f"{'='*60}")
        print("  Esses hinos foram pulados e permanecem como 'pendente' no banco.")
        print("  Adicione os arquivos MP3 e rode novamente para gerá-los.")
    else:
        print("\n✅  Nenhum MP3 faltante — todos os hinos foram processados.")

    if args.apenas_imagem:
        print(f"\n✓ Geração de miniaturas do projeto '{projeto_nome}' concluída.")
    else:
        print(f"\n✓ Processamento do projeto '{projeto_nome}' concluído.")


if __name__ == "__main__":
    main()
