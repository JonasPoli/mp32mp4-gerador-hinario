#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_videos.py — Gerador de vídeos para o Hinário CCB

Uso:
  python gerar_videos.py                     # gera tudo / continua de onde parou
  python gerar_videos.py --apenas 290        # gera somente o hino 290
  python gerar_videos.py --forcar-inicio 100 # processa a partir do hino 100
  python gerar_videos.py --resetar 290       # marca o hino 290 como pendente
  python gerar_videos.py --resetar-todos     # marca tudo como pendente
  python gerar_videos.py --hinario hinario5  # processa somente um hinário específico
  python gerar_videos.py --forcar-download   # baixa novos clipes antes de começar
  python gerar_videos.py --sem-download      # nunca acessa a internet

Dependências:
  pip install Pillow mutagen requests tqdm
  ffmpeg instalado no sistema (brew install ffmpeg)
"""

import argparse
import csv
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
MP3_DIR      = ROOT / "mp3"
FLORES_DIR   = ROOT / "videos_flores"
PHOTOS_DIR   = ROOT / "Photos-1-001"
OUTPUT_DIR   = ROOT / "output"
THUMBS_DIR   = ROOT / "thumbs"   # miniaturas PNG para upload no YouTube
IMAGES_DIR   = ROOT / "images"
FONTES_DIR   = ROOT / "fontes"
DB_PATH      = ROOT / "progresso.db"
METADATA_OUT = ROOT / "videos_gerados.md"
DOWNLOAD_SCRIPT = ROOT / "baixar_videos_flores.py"

CSV_HINARIO4 = FONTES_DIR / "hinario4_sequential.csv"
FRAME_BASE   = IMAGES_DIR / "sem-numero.png"

FRAME_DURATION   = 5      # segundos do frame inicial com o número
TRANSITION_SECS  = 1      # duração da transição blur entre clipes

# Sequência de queries de fallback para download automático
DOWNLOAD_QUERIES = ["flores", "flowers", "natureza", "nature", "campo", "jardim", "primavera"]


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


def extrair_numero_mp3(nome: str) -> int | None:
    """Extrai o número do hino do nome do arquivo MP3 (ex.: '290.mp3' → 290)."""
    m = re.match(r"^(\d+)", nome)
    return int(m.group(1)) if m else None


def duracao_mp3(caminho: Path) -> float:
    """Retorna a duração em segundos de um arquivo MP3."""
    audio = MP3(str(caminho))
    return audio.info.length


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
    conn.execute("PRAGMA foreign_keys=ON")
    _criar_tabelas(conn)
    return conn


def _criar_tabelas(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            numero        INTEGER PRIMARY KEY,
            mp3_file      TEXT NOT NULL,
            hinario       TEXT NOT NULL DEFAULT 'hinario4',
            status        TEXT NOT NULL DEFAULT 'pendente',
            output        TEXT,
            erro_msg      TEXT,
            criado_em     TEXT,
            atualizado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS clipes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            caminho    TEXT UNIQUE NOT NULL,
            fonte      TEXT,
            duracao_s  REAL,
            usado_em   INTEGER REFERENCES videos(numero)
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

def sincronizar_mp3s(conn: sqlite3.Connection, hinario: str = "hinario4"):
    """Insere na tabela videos os MP3s que ainda não estão registrados."""
    existentes = {
        row["numero"]
        for row in conn.execute("SELECT numero FROM videos")
    }
    inseridos = 0
    for mp3 in sorted(MP3_DIR.glob("*.mp3")):
        numero = extrair_numero_mp3(mp3.name)
        if numero is None or numero in existentes:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO videos (numero, mp3_file, hinario, status, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, 'pendente', ?, ?)",
            (numero, str(mp3.relative_to(ROOT)), hinario, now_iso(), now_iso()),
        )
        inseridos += 1
    # Hinos presos em 'processando' (interrupção abrupta) voltam para pendente
    conn.execute(
        "UPDATE videos SET status = 'pendente', atualizado_em = ? WHERE status = 'processando'",
        (now_iso(),),
    )
    conn.commit()
    if inseridos:
        print(f"[banco] {inseridos} novo(s) MP3(s) registrado(s).")


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
    row = conn.execute("SELECT COUNT(*) AS n FROM clipes WHERE usado_em IS NULL").fetchone()
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

def carregar_csv(caminho: Path) -> dict[int, str]:
    """Retorna dicionário {numero: nome} a partir do CSV do hinário."""
    hinos = {}
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                num = int(row["Número"])
                hinos[num] = row["Nome"].strip()
            except (KeyError, ValueError):
                continue
    return hinos


# =============================================================================
# Geração do frame inicial (número sobre a imagem)
# =============================================================================

def gerar_frame_video(numero: int, duracao: int = FRAME_DURATION) -> Path:
    """
    Renderiza o número do hino sobre images/sem-numero.png seguindo o modelo
    de images/com-numero.png:
      - Número em cor azul-marinho (#1a2d5a), fonte serifada grande
      - Posicionado no lado esquerdo da imagem, abaixo do cabeçalho "Hinário 4"
    Salva o PNG em thumbs/hino_NNN.png (thumbnail para YouTube).
    Gera e retorna o vídeo estático temporário em output/_frame_NNN.mp4.
    """
    img = Image.open(FRAME_BASE).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size  # 1672 x 941

    # --- Posição medida a partir de images/com-numero.png --------------------
    # Número ocupa Y: 169–767px (18% a 81.5%) e X a partir de 139px (8.3%)
    # A fonte é dimensionada para que o texto caiba nessa altura.
    Y_TOP        = int(H * 0.180)   # 169px — top do número
    Y_BOT        = int(H * 0.815)   # 767px — bottom do número
    MARGIN_LEFT  = int(W * 0.083)   # 139px — margem esquerda
    target_h     = Y_BOT - Y_TOP    # altura alvo: ~598px

    # --- Fonte serifada (Georgia, igual ao modelo) ---------------------------
    font = None
    for path in [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/Library/Fonts/Georgia.ttf",
        "/System/Library/Fonts/Times.ttc",
    ]:
        try:
            # Ajusta o tamanho para que a altura do texto bata com target_h
            for size in range(target_h, target_h // 2, -10):
                candidate = ImageFont.truetype(path, size=size)
                bbox = draw.textbbox((0, 0), str(numero), font=candidate)
                if (bbox[3] - bbox[1]) <= target_h:
                    font = candidate
                    break
            if font:
                break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    texto = str(numero)
    COR_NUMERO = (26, 45, 90, 255)   # #1a2d5a — azul-marinho do modelo

    # Posiciona com y_top alinhado à borda superior do número no modelo
    bbox = draw.textbbox((0, 0), texto, font=font)
    ascent_offset = bbox[1]  # Pillow inclui espaço acima do glifo no bbox
    y = Y_TOP - ascent_offset

    draw.text((MARGIN_LEFT, y), texto, font=font, fill=COR_NUMERO)

    # --- Salvar thumbnail para o YouTube em thumbs/ --------------------------
    THUMBS_DIR.mkdir(exist_ok=True)
    thumb_path = THUMBS_DIR / f"hino_{numero:03d}.png"
    img.convert("RGB").save(str(thumb_path))
    print(f"  Thumbnail salva em: thumbs/hino_{numero:03d}.png")

    # --- Gerar vídeo estático temporário -------------------------------------
    OUTPUT_DIR.mkdir(exist_ok=True)
    frame_mp4 = OUTPUT_DIR / f"_frame_{numero}.mp4"

    subprocess.run([
        "ffmpeg", "-y", "-loop", "1",
        "-i", str(thumb_path),
        "-t", str(duracao),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", "30",
        str(frame_mp4),
    ], check=True, capture_output=True)

    return frame_mp4


# =============================================================================
# Composição do vídeo de fundo
# =============================================================================

def selecionar_clipes(conn: sqlite3.Connection, duracao_necessaria: float,
                      sem_download: bool, numero: int) -> list[tuple[str, float]]:
    """
    Seleciona clipes disponíveis para cobrir duracao_necessaria segundos.
    Retorna lista de (caminho_absoluto, duracao_s).
    Faz download automático se o pool se esgotar.
    Se mesmo após download não houver clipes livres, reutiliza clipes já usados
    em outros hinos (preferência para os menos recentes), em vez de travar.
    """
    selecionados: list[tuple[str, float]] = []
    total = 0.0

    while total < duracao_necessaria:
        row = conn.execute(
            "SELECT id, caminho, duracao_s FROM clipes WHERE usado_em IS NULL ORDER BY RANDOM() LIMIT 1"
        ).fetchone()

        if row is None:
            if not sem_download:
                baixar_mais_clipes(conn)
                row = conn.execute(
                    "SELECT id, caminho, duracao_s FROM clipes WHERE usado_em IS NULL ORDER BY RANDOM() LIMIT 1"
                ).fetchone()

            if row is None:
                # Fallback: reutilizar clipes já usados em outros hinos
                print("  [aviso] Pool esgotado — reutilizando clipes de outros hinos.")
                row = conn.execute(
                    "SELECT id, caminho, duracao_s FROM clipes "
                    "WHERE usado_em != ? ORDER BY RANDOM() LIMIT 1",
                    (numero,)
                ).fetchone()
                if row is None:
                    raise RuntimeError("Nenhum clipe disponível em nenhuma fonte. Adicione vídeos.")

        caminho = ROOT / row["caminho"]
        if not caminho.exists():
            print(f"  [aviso] Clipe não encontrado, pulando: {caminho.name}")
            conn.execute("DELETE FROM clipes WHERE id = ?", (row["id"],))
            conn.commit()
            continue

        dur = row["duracao_s"] or duracao_video(caminho)
        conn.execute(
            "UPDATE clipes SET usado_em = ? WHERE id = ?", (numero, row["id"])
        )
        conn.commit()

        selecionados.append((str(caminho), dur))
        total += dur

    return selecionados


def compor_video_fundo(clipes: list[tuple[str, float]], duracao_total: float,
                       saida: Path) -> Path:
    """
    Monta o vídeo de fundo concatenando os clipes com transição blur.
    Usa loop espelhado (original→reverso→original) se houver apenas 1 clipe.
    Corta no final para exatamente duracao_total segundos.
    """
    if len(clipes) == 1:
        caminho, dur = clipes[0]
        # loop espelhado para preencher a duração
        clipes_expandidos = []
        total = 0.0
        sentido = 1
        while total < duracao_total + 2:  # margem para corte final
            clipes_expandidos.append((caminho, dur, sentido == -1))
            total += dur
            sentido *= -1
        clipes = [(c, d) for c, d, _ in clipes_expandidos]

    # Normalizar cada clipe individualmente; pular os corrompidos
    partes: list[Path] = []
    for i, (caminho, _) in enumerate(clipes):
        parte = saida.parent / f"_parte_{saida.stem}_{i}.mp4"
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", caminho,
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                       "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-an",
                str(parte),
            ], check=True, capture_output=True)
            partes.append(parte)
        except subprocess.CalledProcessError:
            print(f"  [aviso] Clipe problemático ignorado: {Path(caminho).name}")
            parte.unlink(missing_ok=True)

    if not partes:
        raise RuntimeError("Todos os clipes selecionados falharam na normalização.")

    if len(partes) == 1:
        video_concat = partes[0]
    else:
        # Concatenar com transição xfade entre cada par
        # Construir filtergraph encadeado
        inputs = []
        for p in partes:
            inputs += ["-i", str(p)]

        filter_parts = []
        offset = 0.0
        prev = "[0:v]"
        for i, (_, dur) in enumerate(clipes[:-1]):
            offset += dur - TRANSITION_SECS
            label = f"[v{i+1}]"
            filter_parts.append(
                f"{prev}[{i+1}:v]xfade=transition=fade:duration={TRANSITION_SECS}:offset={offset:.2f}{label}"
            )
            prev = label
            offset -= TRANSITION_SECS  # xfade encurta o tempo total

        filtergraph = ";".join(filter_parts)
        video_concat = saida.parent / f"_concat_{saida.stem}.mp4"

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filtergraph,
            "-map", prev,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(video_concat),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        for p in partes:
            p.unlink(missing_ok=True)

    # Cortar exatamente na duração necessária
    video_cortado = saida.parent / f"_fundo_{saida.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_concat),
        "-t", str(duracao_total),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_cortado),
    ], check=True, capture_output=True)
    if video_concat != partes[0]:
        video_concat.unlink(missing_ok=True)

    return video_cortado


# =============================================================================
# Montagem final: frame + vídeo de fundo + áudio
# =============================================================================

def montar_video_final(frame_mp4: Path, fundo_mp4: Path,
                       mp3: Path, saida: Path, dur_mp3: float):
    """
    Concatena frame inicial (sem áudio) + vídeo de fundo,
    adiciona o MP3 como trilha de áudio e salva o vídeo final.

    O áudio nunca é cortado: usa -t com a duração total exata e apad para
    preencher com silêncio caso o vídeo seja ligeiramente mais longo.

    Usa nomes relativos no arquivo de lista do ffmpeg concat para evitar
    erros com caminhos contendo caracteres especiais (acentos, ç etc.).
    """
    out_dir = saida.parent
    lista = out_dir / f"_lista_{saida.stem}.txt"

    # Caminhos relativos ao diretório de saída — evita problemas com acentos
    frame_rel = frame_mp4.relative_to(out_dir)
    fundo_rel = fundo_mp4.relative_to(out_dir)
    lista.write_text(
        f"file '{frame_rel}'\nfile '{fundo_rel}'\n",
        encoding="utf-8",
    )

    video_concat = out_dir / f"_tmp_{saida.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", lista.name,          # nome relativo; cwd = out_dir
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        video_concat.name,         # idem
    ], check=True, capture_output=True, cwd=str(out_dir))
    lista.unlink(missing_ok=True)

    # Duração total exata: frame inicial + áudio completo
    # Nunca usar -shortest pois o adelay faz o ffmpeg subestimar a duração do áudio.
    # Em vez disso: -t define o limite superior e apad preenche silêncio se necessário.
    total_dur = FRAME_DURATION + dur_mp3

    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_concat),
        "-i", str(mp3),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-af", f"adelay={FRAME_DURATION * 1000}|{FRAME_DURATION * 1000},"
               f"afade=t=in:st={FRAME_DURATION}:d=0.5,"
               f"apad=whole_dur={total_dur}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_dur:.3f}",
        str(saida),
    ], check=True, capture_output=True)
    video_concat.unlink(missing_ok=True)


# =============================================================================
# Geração dos metadados para YouTube
# =============================================================================

def gerar_metadados(numero: int, nome: str) -> str:
    tag_hino = f"Hino{numero}"
    tag_nome = camel_case(nome)
    nome_sem_acento = remover_acentos(nome).lower()
    n = numero

    return f"""# {n}

## Título para o vídeo
Hino {n} - {nome} | Hinário 4 CCB | Teclado Yamaha PSR


## Descrição para o YouTube

Hino {n} - {nome}
Hinário 4 - Congregação Cristã no Brasil

Execução instrumental no teclado Yamaha PSR.

Este vídeo apresenta o áudio do hino {n}, "{nome}", tocado em teclado, com uma interpretação simples e reverente para momentos de meditação, estudo, louvor e acompanhamento musical.

Que esta melodia possa trazer paz, comunhão e edificação.

🎹 Instrumento: Teclado Yamaha PSR
🎵 Hino: {n}
📖 Hinário: Hinário 4
🎶 Título: {nome}

Inscreva-se no canal para acompanhar mais hinos instrumentais da CCB no teclado.

#{tag_hino} #Hinario4 #CCB


## Descrição mais completa

Hino {n} - {nome}
Hinário 4 - Congregação Cristã no Brasil

Neste vídeo, apresento o áudio instrumental do hino {n}, "{nome}", tocado em teclado Yamaha PSR.

A proposta deste conteúdo é compartilhar uma versão instrumental simples, tranquila e reverente, ideal para quem deseja ouvir, estudar, acompanhar ou meditar por meio dos hinos.

🎹 Instrumento utilizado: Teclado Yamaha PSR
🎼 Hino: {n}
📖 Hinário: Hinário 4
🎵 Nome do hino: {nome}
🎧 Tipo de conteúdo: Áudio instrumental

Se este hino falou ao seu coração, deixe seu like, compartilhe com alguém e inscreva-se no canal para acompanhar novos hinos tocados no teclado.

Que Deus abençoe a todos.

#{tag_hino} #Hinario4 #CCB #{tag_nome}


## Tags para YouTube

hino {n}, hino {n} ccb, {nome_sem_acento}, hinário 4, hinario 4, ccb hino {n}, hinos ccb, hinos da ccb, congregação cristã no brasil, congregacao crista no brasil, hinos tocados no teclado, hino no teclado, teclado yamaha psr, yamaha psr, hinos ccb teclado, hino instrumental ccb, ccb instrumental, hinário ccb, hinario ccb, hinos para meditação, hinos para meditacao, música instrumental cristã, musica instrumental crista, louvor instrumental, teclado evangélico, hinos evangélicos no teclado, hino {n} instrumental

---
"""


def acrescentar_metadados(numero: int, nome: str):
    """Acrescenta (não sobrescreve) a entrada do hino no arquivo de metadados."""
    conteudo = gerar_metadados(numero, nome)
    with open(METADATA_OUT, "a", encoding="utf-8") as f:
        f.write(conteudo + "\n")


# =============================================================================
# Loop principal
# =============================================================================

def processar_hino(numero: int, mp3_path: Path, nome: str,
                   conn: sqlite3.Connection, sem_download: bool):
    """Gera o vídeo completo para um único hino."""
    print(f"\n[hino {numero:03d}] {nome}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    saida = OUTPUT_DIR / f"hino_{numero:03d}.mp4"

    # Apagar o vídeo final existente e quaisquer temporários de uma run anterior
    # para evitar que arquivos corrompidos ou incompletos interfiram na nova geração.
    saida.unlink(missing_ok=True)
    for tmp in OUTPUT_DIR.glob(f"_*_{numero}*.mp4"):
        tmp.unlink(missing_ok=True)
    for tmp in OUTPUT_DIR.glob(f"_*hino_{numero:03d}*.mp4"):
        tmp.unlink(missing_ok=True)
    for tmp in OUTPUT_DIR.glob(f"_lista_hino_{numero:03d}.txt"):
        tmp.unlink(missing_ok=True)

    conn.execute(
        "UPDATE videos SET status = 'processando', atualizado_em = ? WHERE numero = ?",
        (now_iso(), numero),
    )
    conn.commit()

    try:
        dur_mp3 = duracao_mp3(mp3_path)
        print(f"  Duração do MP3: {dur_mp3:.1f}s")

        # 1. Frame inicial
        print("  Gerando frame inicial...")
        frame_mp4 = gerar_frame_video(numero)

        # 2. Selecionar e compor vídeo de fundo
        print("  Selecionando clipes de fundo...")
        clipes = selecionar_clipes(conn, dur_mp3, sem_download, numero)
        print(f"  {len(clipes)} clipe(s) selecionado(s).")

        print("  Compondo vídeo de fundo...")
        fundo_mp4 = compor_video_fundo(clipes, dur_mp3, saida)

        # 3. Montagem final
        print("  Montando vídeo final...")
        montar_video_final(frame_mp4, fundo_mp4, mp3_path, saida, dur_mp3)

        # 4. Limpeza de temporários
        frame_mp4.unlink(missing_ok=True)
        fundo_mp4.unlink(missing_ok=True)

        # 5. Registrar sucesso
        conn.execute(
            "UPDATE videos SET status = 'concluido', output = ?, atualizado_em = ? WHERE numero = ?",
            (str(saida.relative_to(ROOT)), now_iso(), numero),
        )
        conn.commit()

        # 6. Metadados YouTube
        acrescentar_metadados(numero, nome)
        print(f"  ✓ Salvo em: {saida.relative_to(ROOT)}")

    except Exception as e:
        conn.execute(
            "UPDATE videos SET status = 'erro', erro_msg = ?, atualizado_em = ? WHERE numero = ?",
            (str(e), now_iso(), numero),
        )
        conn.commit()
        print(f"  ✗ ERRO: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Gerador de vídeos para o Hinário CCB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apenas", type=int, metavar="NUMERO",
                        help="Processa somente este hino.")
    parser.add_argument("--forcar-inicio", type=int, metavar="NUMERO",
                        help="Começa a partir deste número.")
    parser.add_argument("--resetar", type=int, metavar="NUMERO",
                        help="Marca um hino como pendente e libera seus clipes.")
    parser.add_argument("--resetar-todos", action="store_true",
                        help="Marca todos os hinos como pendente.")
    parser.add_argument("--hinario", default=None,
                        help="Filtra por hinário (ex.: hinario4, hinario5).")
    parser.add_argument("--forcar-download", action="store_true",
                        help="Baixa novos clipes antes de começar.")
    parser.add_argument("--sem-download", action="store_true",
                        help="Nunca acessa a internet para baixar clipes.")
    args = parser.parse_args()

    conn = abrir_banco()

    # ---- Operações de reset ------------------------------------------------
    if args.resetar_todos:
        conn.execute(
            "UPDATE videos SET status = 'pendente', atualizado_em = ?", (now_iso(),)
        )
        conn.execute("UPDATE clipes SET usado_em = NULL")
        conn.commit()
        print("[reset] Todos os hinos marcados como pendente.")
        return

    if args.resetar:
        conn.execute(
            "UPDATE clipes SET usado_em = NULL WHERE usado_em = ?", (args.resetar,)
        )
        conn.execute(
            "UPDATE videos SET status = 'pendente', output = NULL, erro_msg = NULL, atualizado_em = ? "
            "WHERE numero = ?",
            (now_iso(), args.resetar),
        )
        conn.commit()
        print(f"[reset] Hino {args.resetar} marcado como pendente.")
        return

    # ---- Inicialização -----------------------------------------------------
    hinario = args.hinario or "hinario4"
    sincronizar_mp3s(conn, hinario)
    sincronizar_clipes(conn)

    if args.forcar_download:
        baixar_mais_clipes(conn)

    hinos = carregar_csv(CSV_HINARIO4)

    # ---- Seleção de hinos a processar --------------------------------------
    query = "SELECT numero, mp3_file FROM videos WHERE status = 'pendente'"
    params: list = []

    if args.hinario:
        query += " AND hinario = ?"
        params.append(args.hinario)

    if args.apenas:
        query += " AND numero = ?"
        params.append(args.apenas)
    elif args.forcar_inicio:
        query += " AND numero >= ?"
        params.append(args.forcar_inicio)

    query += " ORDER BY numero"
    pendentes = conn.execute(query, params).fetchall()

    if not pendentes:
        print("Nada a processar. Todos os hinos já estão concluídos.")
        return

    print(f"\n{len(pendentes)} hino(s) a processar.\n")

    for row in pendentes:
        numero = row["numero"]
        mp3_path = ROOT / row["mp3_file"]
        nome = hinos.get(numero, f"Hino {numero}")

        if not mp3_path.exists():
            print(f"[aviso] MP3 não encontrado: {mp3_path} — pulando.")
            continue

        processar_hino(numero, mp3_path, nome, conn, args.sem_download)

    conn.close()
    print("\n✓ Processamento concluído.")


if __name__ == "__main__":
    main()
