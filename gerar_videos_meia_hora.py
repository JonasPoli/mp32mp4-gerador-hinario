#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_videos_meia_hora.py — Gerador de vídeos COM LEGENDAS para o projeto "Meia Hora"

Lê os MP3s lentos do órgão eletrônico drawbar em:
  mp3/orgao_eletronico_drawbar/

Fluxo por hino:
  1. Gera vídeo base (thumbnail + clipes de fundo + MP3)
  2. Lê timestamps de letra do JSON companion
  3. Gera arquivo .ass com legendas sincronizadas
  4. Embute as legendas no vídeo final → hino-meia_hora-NNN.mp4
  5. Ao final, concatena tudo em coletanea_meia_hora.mp4

Uso:
  python gerar_videos_meia_hora.py                   # todos os hinos + coletânea
  python gerar_videos_meia_hora.py --apenas 1        # somente o hino 001
  python gerar_videos_meia_hora.py --sem-coletanea   # hinos sem coletânea
  python gerar_videos_meia_hora.py --so-coletanea    # só a coletânea
  python gerar_videos_meia_hora.py --resetar 1       # marca hino 001 como pendente
  python gerar_videos_meia_hora.py --resetar-todos   # marca todos como pendente
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from gerar_videos import ajustar_metadados_coro

try:
    import psutil
    _PSUTIL_DISPONIVEL = True
except ImportError:
    _PSUTIL_DISPONIVEL = False
    print("[aviso] psutil não encontrado — monitoramento de memória desabilitado.")

from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    from gerar_thumb import gerar_thumb as _gerar_thumb
    _THUMB_DISPONIVEL = True
except ImportError:
    _THUMB_DISPONIVEL = False
    print("[aviso] gerar_thumb.py não encontrado — usando layout legado")

# =============================================================================
# Configuração do projeto
# =============================================================================

ROOT          = Path(__file__).parent
PROJETO_NOME  = "meia_hora"
PROJETO_DIR   = ROOT / "projects" / PROJETO_NOME
MP3_DIR       = ROOT / "mp3" / "orgao_eletronico_drawbar"
BG_CLIPS_DIR  = ROOT / "shared_assets" / "background_clips"
FLORES_DIR    = BG_CLIPS_DIR / "videos_flores"
PHOTOS_DIR    = BG_CLIPS_DIR / "Photos-1-001"
MOVIEA_DIR    = BG_CLIPS_DIR / "Temp-moviea"
OUTPUT_DIR    = ROOT / "output" / PROJETO_NOME
THUMBS_DIR    = OUTPUT_DIR / "thumbs"
DB_PATH       = ROOT / "progresso.db"
NOME_EXIBICAO = "Hinos de Meia Hora | Meditação CCB"

FRAME_DURATION = 5
FFMPEG_PRESET  = "fast"
RAM_LIMITE_PCT = 85
RAM_PAUSA_S    = 30
CPU_LIMITE_PCT = 90

# =============================================================================
# Utilitários
# =============================================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def remover_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")

def formatar_numero_completo(numero):
    num_str = str(numero).strip()
    return f"{int(num_str):03d}" if num_str.isdigit() else num_str

def verificar_recursos(pausa_extra_s=0.0):
    if pausa_extra_s > 0:
        time.sleep(pausa_extra_s)
    if not _PSUTIL_DISPONIVEL:
        return
    while True:
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=2)
        motivos = []
        if RAM_LIMITE_PCT > 0 and ram.percent >= RAM_LIMITE_PCT:
            motivos.append(f"RAM {ram.percent:.1f}%")
        if CPU_LIMITE_PCT > 0 and cpu >= CPU_LIMITE_PCT:
            motivos.append(f"CPU {cpu:.1f}%")
        if motivos:
            print(f"  [recursos] ⚠️  {', '.join(motivos)} — pausando {RAM_PAUSA_S}s...")
            time.sleep(RAM_PAUSA_S)
        else:
            break

def duracao_mp3(caminho):
    try:
        audio = MP3(str(caminho))
        if audio.info.length > 0.0:
            return audio.info.length
    except Exception:
        pass
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(caminho)],
        capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0

def duracao_video(caminho):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(caminho)],
        capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0

# =============================================================================
# Leitura dos MP3s do drawbar
# =============================================================================

def extrair_numero_e_nome_mp3(mp3_path):
    """
    Extrai número e nome do hino a partir do MP3 e JSON companion.
    Ex: 001- Cristo meu Mestre_lento.mp3 -> (1, "Cristo, Meu Mestre")
    """
    stem = mp3_path.stem
    m = re.match(r"^(\d+)", stem)
    if not m:
        return None, stem
    numero = int(m.group(1))
    json_path = mp3_path.with_suffix(".json")
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
            titulo = dados.get("titulo", "").strip()
            if titulo:
                return numero, titulo
        except Exception:
            pass
    nome = re.sub(r"^\d+[-\s]+", "", stem)
    nome = re.sub(r"_lento$", "", nome, flags=re.IGNORECASE).strip()
    return numero, nome

def listar_mp3s():
    resultado = []
    for mp3 in sorted(MP3_DIR.glob("*.mp3")):
        numero, nome = extrair_numero_e_nome_mp3(mp3)
        if numero is not None:
            resultado.append((numero, nome, mp3))
    resultado.sort(key=lambda x: x[0])
    return resultado

# =============================================================================
# Banco de dados
# =============================================================================

def abrir_banco():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _criar_tabelas(conn)
    return conn

def _criar_tabelas(conn):
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
            vezes_usado    INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        );
        CREATE TABLE IF NOT EXISTS historico_clipes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            projeto       TEXT NOT NULL,
            numero        TEXT NOT NULL,
            clipe_caminho TEXT NOT NULL,
            duracao_s     REAL,
            usado_em_ts   TEXT NOT NULL
        );
    """)
    c_cursor = conn.execute("PRAGMA table_info(clipes)")
    c_cols = [r[1] for r in c_cursor.fetchall()]
    if c_cols and "vezes_usado" not in c_cols:
        conn.execute("ALTER TABLE clipes ADD COLUMN vezes_usado INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE clipes SET vezes_usado = 1 WHERE projeto_usado IS NOT NULL OR usado_em IS NOT NULL")
    conn.commit()

def sincronizar_mp3s(conn, mp3s):
    existentes = {row["numero"] for row in
                  conn.execute("SELECT numero FROM videos WHERE projeto = ?", (PROJETO_NOME,))}
    inseridos = 0
    for numero, nome, mp3_path in mp3s:
        if numero in existentes:
            continue
        rel = str(mp3_path.relative_to(ROOT))
        conn.execute(
            "INSERT OR IGNORE INTO videos "
            "(projeto, numero, mp3_file, hinario, status, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, 'hinario5', 'pendente', ?, ?)",
            (PROJETO_NOME, numero, rel, now_iso(), now_iso()),
        )
        inseridos += 1
    conn.execute(
        "UPDATE videos SET status = 'pendente', atualizado_em = ? "
        "WHERE status = 'processando' AND projeto = ?",
        (now_iso(), PROJETO_NOME),
    )
    conn.commit()
    if inseridos:
        print(f"[banco] {inseridos} novo(s) MP3(s) registrado(s) para '{PROJETO_NOME}'.")

def sincronizar_clipes(conn):
    inseridos = 0
    extensoes = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    def escanear(pasta, fonte):
        nonlocal inseridos
        if not pasta.exists():
            return
        for f in pasta.iterdir():
            if f.name.startswith(".") or f.suffix.lower() not in extensoes:
                continue
            rel = str(f.relative_to(ROOT))
            if conn.execute("SELECT 1 FROM clipes WHERE caminho = ?", (rel,)).fetchone():
                continue
            dur = duracao_video(f)
            if dur <= 0.0:
                continue
            conn.execute("INSERT OR IGNORE INTO clipes (caminho, fonte, duracao_s) VALUES (?, ?, ?)",
                         (rel, fonte, dur))
            inseridos += 1

    if BG_CLIPS_DIR.exists():
        for subpasta in BG_CLIPS_DIR.iterdir():
            if subpasta.is_dir() and not subpasta.name.startswith("."):
                escanear(subpasta, subpasta.name)
    else:
        escanear(FLORES_DIR, "videos_flores")
        escanear(PHOTOS_DIR, "photos")
        escanear(MOVIEA_DIR, "moviea")

    conn.commit()
    if inseridos:
        print(f"[banco] {inseridos} novo(s) clipe(s) de fundo registrado(s).")

def carregar_config_projeto():
    cfg_path = PROJETO_DIR / "config.json"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# =============================================================================
# Legendas — leitura do JSON companion e geração do .ass
# =============================================================================

def formatar_tempo_ass(segundos):
    """Converte segundos para formato ASS: H:MM:SS.CC"""
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int(round((segundos - int(segundos)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def carregar_legendas_do_json(mp3_path):
    """
    Lê o JSON companion do MP3 e retorna lista de {texto, inicio, fim}.
    Os timestamps no JSON são relativos ao início do áudio.
    Retorna [] se não houver JSON ou campo 'letra'.
    """
    json_path = mp3_path.with_suffix(".json")
    if not json_path.exists():
        print(f"  [legenda] JSON companion não encontrado: {json_path.name}")
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            dados = json.load(f)
        letra = dados.get("letra", [])
        if not letra:
            print(f"  [legenda] Campo 'letra' vazio ou ausente em {json_path.name}")
            return []
        mapa = []
        for item in letra:
            mapa.append({
                "texto": item["texto"],
                "inicio": float(item["inicio"]),
                "fim": float(item["fim"]),
            })
        print(f"  [legenda] {len(mapa)} linha(s) carregada(s) de {json_path.name}")
        return mapa
    except Exception as e:
        print(f"  [legenda] Erro ao ler {json_path.name}: {e}")
        return []

def gerar_arquivo_ass(mapa_legendas, output_ass, titulo, offset_s):
    """
    Escreve arquivo .ass com as legendas.
    offset_s = dur_vinheta + FRAME_DURATION (deslocamento no vídeo final).
    """
    linhas = []
    linhas.append("[Script Info]")
    linhas.append(f"; Legenda gerada para {titulo}")
    linhas.append(f"Title: {titulo}")
    linhas.append("ScriptType: v4.00+")
    linhas.append("WrapStyle: 0")
    linhas.append("PlayResX: 1920")
    linhas.append("PlayResY: 1080")
    linhas.append("ScaledBorderAndShadow: yes")
    linhas.append("")
    linhas.append("[V4+ Styles]")
    linhas.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    # Branco, contorno verde escuro CCB, sombra preta semi-transparente
    linhas.append("Style: Default,Montserrat,87,&H00FFFFFF,&H000000FF,&H000F3C21,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,10,10,120,1")
    linhas.append("")
    linhas.append("[Events]")
    linhas.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    for item in mapa_legendas:
        inicio = formatar_tempo_ass(item["inicio"] + offset_s)
        fim    = formatar_tempo_ass(item["fim"] + offset_s)
        texto  = item["texto"]
        linhas.append(f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{{\\fad(250,250)}}{texto}")

    output_ass.write_text("\n".join(linhas), encoding="utf-8")

def embutir_legendas(video_base, ass_path, video_saida):
    """Usa ffmpeg para embutir o .ass no vídeo."""
    abs_video  = str(video_base.resolve())
    abs_ass    = str(ass_path.resolve())
    abs_saida  = str(video_saida.resolve())
    ass_escaped = abs_ass.replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", abs_video,
        "-vf", f"subtitles=filename='{ass_escaped}'",
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-pix_fmt", "yuv420p",
        "-threads", "2",
        "-c:a", "copy",
        abs_saida,
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  [ffmpeg stderr]:\n{result.stderr[-1500:]}")
        raise RuntimeError(f"FFmpeg falhou ao embutir legendas (código {result.returncode})")

# =============================================================================
# Badge "MEIA HORA"
# =============================================================================

# Fontes compatíveis com macOS/Linux/Windows (bold para o badge)
_FONTES_BADGE = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

def _carregar_fonte_badge(tamanho):
    for path in _FONTES_BADGE:
        try:
            return ImageFont.truetype(path, tamanho)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def desenhar_badge_meia_hora(img: Image.Image) -> Image.Image:
    """
    Adiciona um badge/ribbon elegante "✦ MEIA HORA ✦" na thumbnail.

    Posicionado no canto inferior esquerdo da imagem (1920×1080),
    acima da faixa "HINÁRIO 5" da máscara — numa pílula dourada inclinada
    em -2.5°, consistente com o estilo visual do canal.

    Returns:
        Imagem PIL RGBA com o badge aplicado (in-place, mas retorna para segurança).
    """
    W, H = img.size   # 1920 × 1080

    TEXTO   = "✦  MEIA HORA  ✦"
    FONTE_S = 62      # tamanho da fonte no badge
    PAD_X   = 48      # padding horizontal interno
    PAD_Y   = 20      # padding vertical interno
    RADIUS  = 28      # arredondamento dos cantos
    ANGULO  = -2.5    # inclinação (graus)

    # Cores do badge — dourado CCB
    COR_FUNDO_TOPO = (255, 225, 100, 245)   # amarelo dourado
    COR_FUNDO_BASE = (204, 148, 18, 245)    # dourado escuro
    COR_BORDA      = (255, 245, 180, 255)   # borda clara
    COR_BORDA_INT  = (92,  62,  12, 255)    # borda interna escura
    COR_TEXTO      = (5,   40,  22, 255)    # verde escuro CCB
    COR_SOMBRA_TX  = (255, 240, 150, 200)   # brilho dourado claro no texto

    fonte = _carregar_fonte_badge(FONTE_S)

    # Medir o texto
    tmp_img  = Image.new("RGBA", (800, 200), (0, 0, 0, 0))
    tmp_draw = ImageDraw.Draw(tmp_img)
    bbox     = tmp_draw.textbbox((0, 0), TEXTO, font=fonte)
    tw, th   = bbox[2] - bbox[0], bbox[3] - bbox[1]

    BW = tw + PAD_X * 2
    BH = th + PAD_Y * 2

    # Canvas para o badge (com margem extra para blur de sombra)
    MARG = 20
    canvas = Image.new("RGBA", (BW + MARG * 2, BH + MARG * 2), (0, 0, 0, 0))
    dc     = ImageDraw.Draw(canvas)

    # 1) Sombra projetada (offset + blur)
    sombra = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(sombra)
    ds.rounded_rectangle(
        (MARG + 6, MARG + 9, MARG + BW + 6, MARG + BH + 9),
        radius=RADIUS, fill=(0, 0, 0, 150)
    )
    sombra = sombra.filter(ImageFilter.GaussianBlur(8))
    canvas.alpha_composite(sombra)

    # 2) Gradiente vertical (fundo do badge)
    grad = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    gd   = grad.load()
    for y_px in range(BH):
        t  = y_px / max(1, BH - 1)
        r  = int(COR_FUNDO_TOPO[0] * (1 - t) + COR_FUNDO_BASE[0] * t)
        g  = int(COR_FUNDO_TOPO[1] * (1 - t) + COR_FUNDO_BASE[1] * t)
        b  = int(COR_FUNDO_TOPO[2] * (1 - t) + COR_FUNDO_BASE[2] * t)
        a  = int(COR_FUNDO_TOPO[3] * (1 - t) + COR_FUNDO_BASE[3] * t)
        for x_px in range(BW):
            gd[x_px, y_px] = (r, g, b, a)
    # Aplicar máscara arredondada no gradiente
    mask_round = Image.new("L", (BW, BH), 0)
    ImageDraw.Draw(mask_round).rounded_rectangle(
        (0, 0, BW - 1, BH - 1), radius=RADIUS, fill=255
    )
    grad.putalpha(mask_round)
    canvas.alpha_composite(grad, (MARG, MARG))

    # 3) Bordas
    dc.rounded_rectangle(
        (MARG, MARG, MARG + BW, MARG + BH),
        radius=RADIUS, outline=COR_BORDA, width=4
    )
    dc.rounded_rectangle(
        (MARG + 6, MARG + 6, MARG + BW - 6, MARG + BH - 6),
        radius=RADIUS - 4, outline=COR_BORDA_INT, width=2
    )

    # 4) Brilho dourado no texto (halo)
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    dg   = ImageDraw.Draw(glow)
    dg.text(
        (MARG + PAD_X - bbox[0], MARG + PAD_Y - bbox[1]),
        TEXTO, font=fonte,
        fill=(255, 240, 120, 120),
        stroke_width=4, stroke_fill=(255, 230, 80, 100)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(3))
    canvas.alpha_composite(glow)

    # 5) Texto principal
    dc.text(
        (MARG + PAD_X - bbox[0], MARG + PAD_Y - bbox[1]),
        TEXTO, font=fonte, fill=COR_TEXTO,
        stroke_width=2, stroke_fill=COR_SOMBRA_TX
    )

    # Inclinar o badge
    badge_rot = canvas.rotate(ANGULO, expand=True, resample=Image.Resampling.BICUBIC)

    # Posição: canto inferior esquerdo, ~11% do height acima do bottom
    # (respeitando a faixa da máscara em baixo)
    bw_rot, bh_rot = badge_rot.size
    pos_x = int(W * 0.028)                       # margem esquerda leve
    pos_y = int(H * 0.775) - bh_rot // 2         # zona acima da faixa inferior

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    img.alpha_composite(badge_rot, (pos_x, pos_y))
    return img


# =============================================================================
# Geração de Thumbnail e Frame
# =============================================================================

def gerar_thumbnail(numero, nome, projeto_cfg):
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    num_formatted = formatar_numero_completo(numero)
    thumb_path = THUMBS_DIR / f"hino-{PROJETO_NOME}-{num_formatted}.png"

    if _THUMB_DISPONIVEL:
        try:
            mascara_path = projeto_cfg.get("mascara")
            _gerar_thumb(
                numero_hino=numero, titulo_hino=nome, output_path=thumb_path,
                seed=projeto_cfg.get("thumb_seed"), mascara_path=mascara_path,
            )
            # Aplica o badge "MEIA HORA" sobre a thumb já gerada
            img = Image.open(str(thumb_path)).convert("RGBA")
            img = desenhar_badge_meia_hora(img)
            img.convert("RGB").save(str(thumb_path), "JPEG", quality=95)
            print(f"  [badge] ✦ MEIA HORA ✦ adicionado à thumbnail")
            return thumb_path
        except Exception as e:
            print(f"  [aviso] Erro no pipeline v02: {e} — usando pipeline legado...")

    imagem_base = ROOT / projeto_cfg.get("imagem_base", "assets/imagens-base/hinos_de_orgao.png")
    if not imagem_base.exists():
        raise FileNotFoundError(f"Imagem base não encontrada: {imagem_base}")

    img = Image.open(imagem_base).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size
    font_paths = [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/Library/Fonts/Georgia.ttf",
        "/System/Library/Fonts/Times.ttc",
    ]

    def desenhar(texto, x, y_top, y_bottom, max_w, cor, max_size=None):
        target_h = y_bottom - y_top
        if max_size is None:
            max_size = target_h
        for path in font_paths:
            try:
                for size in range(max_size, 12, -2):
                    font = ImageFont.truetype(path, size=size)
                    bbox = draw.textbbox((0, 0), texto, font=font)
                    if (bbox[2] - bbox[0]) <= max_w and (bbox[3] - bbox[1]) <= target_h:
                        draw.text((x, y_top), texto, font=font, fill=tuple(cor))
                        return
            except OSError:
                continue

    d  = projeto_cfg.get("desenho", {})
    cn = d.get("numero", {"x": 120, "y_top": 150, "y_bottom": 780, "max_width": 580, "cor": [26, 45, 90, 255]})
    cm = d.get("nome",   {"x": 780, "y_top": 200, "y_bottom": 800, "max_width": 550, "cor": [26, 45, 90, 255], "max_font_size": 100})
    desenhar(str(numero), cn.get("x",120), cn.get("y_top",150), cn.get("y_bottom",780),
             cn.get("max_width",580), cn.get("cor",[26,45,90,255]))
    desenhar(nome, cm.get("x",780), cm.get("y_top",200), cm.get("y_bottom",800),
             cm.get("max_width",550), cm.get("cor",[26,45,90,255]), cm.get("max_font_size",100))
    # Badge no pipeline legado também
    img = desenhar_badge_meia_hora(img)
    img.convert("RGB").save(str(thumb_path))
    return thumb_path

def gerar_frame_video(numero, nome, projeto_cfg):
    thumb_path = gerar_thumbnail(numero, nome, projeto_cfg)
    num_formatted = formatar_numero_completo(numero)
    print(f"  Thumbnail: thumbs/hino-{PROJETO_NOME}-{num_formatted}.png")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame_mp4 = OUTPUT_DIR / f"_frame_{PROJETO_NOME}_{numero}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(thumb_path),
        "-t", str(FRAME_DURATION),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fade=t=in:st=0:d=1.5",
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-pix_fmt", "yuv420p",
        "-threads", "2", "-r", "30", str(frame_mp4),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return frame_mp4

# =============================================================================
# Clipes de fundo
# =============================================================================

def selecionar_clipes(conn, duracao_necessaria, numero):
    selecionados = []
    total = 0.0
    ids_sel = []
    while total < duracao_necessaria:
        q = "SELECT id, caminho, duracao_s, vezes_usado FROM clipes"
        p = []
        if ids_sel:
            ph = ",".join("?" for _ in ids_sel)
            q += f" WHERE id NOT IN ({ph})"
            p.extend(ids_sel)
        q += " ORDER BY vezes_usado ASC, RANDOM() LIMIT 1"
        row = conn.execute(q, p).fetchone()
        if row is None:
            if ids_sel:
                print("  [aviso] Clipes únicos esgotados, permitindo repetições.")
                ids_sel = []
                continue
            else:
                raise RuntimeError(
                    "Nenhum clipe de fundo disponível. "
                    "Adicione vídeos em shared_assets/background_clips/")
        caminho = ROOT / row["caminho"]
        if not caminho.exists():
            conn.execute("DELETE FROM clipes WHERE id = ?", (row["id"],))
            conn.commit()
            continue
        dur = row["duracao_s"] or duracao_video(caminho)
        conn.execute(
            "UPDATE clipes SET vezes_usado = vezes_usado + 1, projeto_usado = ?, usado_em = ? WHERE id = ?",
            (PROJETO_NOME, numero, row["id"]))
        conn.commit()
        selecionados.append((str(caminho), dur))
        ids_sel.append(row["id"])
        total += dur
    return selecionados

def registrar_log_clipes(conn, projeto_nome, numero, clipes):
    ts = now_iso()
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "background_clips.log"

    lines_to_log = [
        f"[{ts}] [PROJETO: {projeto_nome}] Hino {numero} - {len(clipes)} clipe(s) de fundo selecionado(s):"
    ]

    for idx, (caminho_str, dur) in enumerate(clipes, 1):
        try:
            rel_caminho = str(Path(caminho_str).relative_to(ROOT))
        except ValueError:
            rel_caminho = caminho_str

        conn.execute(
            "INSERT INTO historico_clipes (projeto, numero, clipe_caminho, duracao_s, usado_em_ts) VALUES (?, ?, ?, ?, ?)",
            (projeto_nome, str(numero), rel_caminho, dur, ts)
        )
        lines_to_log.append(f"  {idx:02d}. {rel_caminho} ({dur:.1f}s)")

    conn.commit()

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines_to_log) + "\n\n")
    except Exception as e:
        print(f"  [aviso] Falha ao escrever em {log_file.name}: {e}")

def compor_video_fundo(clipes, duracao_total, saida):
    if len(clipes) == 1:
        caminho, dur = clipes[0]
        expandidos, total = [], 0.0
        while total < duracao_total + 2:
            expandidos.append((caminho, dur))
            total += dur
        clipes = expandidos

    partes = []
    out_dir = saida.parent
    for i, (caminho, _) in enumerate(clipes):
        parte = out_dir / f"_parte_{saida.stem}_{i}.mp4"
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", caminho,
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                       "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
                "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-pix_fmt", "yuv420p",
                "-threads", "2", "-an", str(parte),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            partes.append(parte)
        except subprocess.CalledProcessError:
            print(f"  [aviso] Clipe problemático: {Path(caminho).name}")
            parte.unlink(missing_ok=True)

    if not partes:
        raise RuntimeError("Todos os clipes falharam na normalização.")

    lista_txt = out_dir / f"_lista_{saida.stem}_bg.txt"
    lista_txt.write_text("\n".join(f"file '{p.name}'" for p in partes) + "\n", encoding="utf-8")
    video_concat = out_dir / f"_concat_{saida.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", lista_txt.name, "-c", "copy", video_concat.name,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(out_dir))
    lista_txt.unlink(missing_ok=True)
    for p in partes:
        p.unlink(missing_ok=True)

    video_cortado = out_dir / f"_fundo_{saida.stem}.mp4"
    fade_start = max(0.0, duracao_total - 1.5)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_concat),
        "-t", str(duracao_total),
        "-vf", f"fade=t=out:st={fade_start}:d=1.5",
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-pix_fmt", "yuv420p",
        "-threads", "2", str(video_cortado),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    video_concat.unlink(missing_ok=True)
    return video_cortado

def preparar_vinheta(vinheta_path, saida_dir):
    vinheta_v = saida_dir / f"_vinheta_v_{vinheta_path.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(vinheta_path),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-pix_fmt", "yuv420p",
        "-threads", "2", "-an", str(vinheta_v),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "default=noprint_wrappers=1:nokey=1", str(vinheta_path),
    ], capture_output=True, text=True)
    vinheta_a = None
    if probe.stdout.strip():
        vinheta_a = saida_dir / f"_vinheta_a_{vinheta_path.stem}.aac"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(vinheta_path),
            "-vn", "-c:a", "aac", "-b:a", "192k", str(vinheta_a),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return vinheta_v, vinheta_a

def montar_video_final(frame_mp4, fundo_mp4, mp3, saida, dur_mp3,
                       vinheta_mp4=None, vinheta_audio=None):
    out_dir = saida.parent
    lista = out_dir / f"_lista_{saida.stem}.txt"
    entradas = []
    if vinheta_mp4 is not None:
        entradas.append(vinheta_mp4.relative_to(out_dir))
    entradas.append(frame_mp4.relative_to(out_dir))
    entradas.append(fundo_mp4.relative_to(out_dir))
    lista.write_text("\n".join(f"file '{p}'" for p in entradas) + "\n", encoding="utf-8")

    video_concat = out_dir / f"_tmp_{saida.stem}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista.name,
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-pix_fmt", "yuv420p",
        "-threads", "2", video_concat.name,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(out_dir))
    lista.unlink(missing_ok=True)

    dur_vin = duracao_video(vinheta_mp4) if vinheta_mp4 is not None else 0.0
    delay_s = dur_vin + FRAME_DURATION
    delay_ms = int(delay_s * 1000)
    total_dur = delay_s + dur_mp3

    if vinheta_audio is not None:
        fc = (
            f"[1:a]apad=whole_dur={total_dur}[va];"
            f"[2:a]adelay={delay_ms}|{delay_ms},"
            f"afade=t=in:st={delay_s}:d=0.5,"
            f"afade=t=out:st={total_dur - 1.5}:d=1.5,"
            f"apad=whole_dur={total_dur}[ma];"
            f"[va][ma]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_concat), "-i", str(vinheta_audio), "-i", str(mp3),
            "-map", "0:v:0", "-filter_complex", fc, "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_dur:.3f}", str(saida),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_concat), "-i", str(mp3),
            "-map", "0:v:0", "-map", "1:a:0",
            "-af", f"adelay={delay_ms}|{delay_ms},"
                   f"afade=t=in:st={delay_s}:d=0.5,"
                   f"afade=t=out:st={total_dur - 1.5}:d=1.5,"
                   f"apad=whole_dur={total_dur}",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_dur:.3f}", str(saida),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    video_concat.unlink(missing_ok=True)

    # Retorna o offset total do áudio (vinheta + frame) para cálculo das legendas
    return dur_vin

# =============================================================================
# Metadados para YouTube
# =============================================================================

def gerar_metadados(numero, nome, projeto_cfg):
    sem_acento = remover_acentos(nome).lower()
    num_str = str(numero)

    def sub(t):
        return (t.replace("<numero-do-hino>", num_str)
                 .replace("<nome-do-hino>", nome)
                 .replace("<nome-do-projeto>", NOME_EXIBICAO)
                 .replace("<nome-sem-acento>", sem_acento)
                 .replace("<numero-do-hinario>", "5"))

    titulo    = sub(projeto_cfg.get("titulo_template",
                    f"Hino {num_str} - {nome} | Hinário 5 CCB | {NOME_EXIBICAO}"))
    descricao = sub(projeto_cfg.get("descricao", ""))
    tags      = sub(projeto_cfg.get("palavras_chaves", ""))

    if len(tags) > 500:
        parts = [t.strip() for t in tags.split(",") if t.strip()]
        valid, cur = [], 0
        for p in parts:
            added = len(p) + (2 if valid else 0)
            if cur + added <= 500:
                valid.append(p)
                cur += added
            else:
                break
        tags = ", ".join(valid)

    titulo, descricao, tags = ajustar_metadados_coro(titulo, descricao, tags, numero)

    return (f"# {numero}\n\n## Título para o vídeo\n{titulo}\n\n\n"
            f"## Descrição para o YouTube\n\n{descricao}\n\n\n"
            f"## Tags para YouTube\n\n{tags}\n\n---\n")

def acrescentar_metadados(numero, nome, projeto_cfg):
    metadata_out = ROOT / f"videos_gerados_{PROJETO_NOME}.md"
    with open(metadata_out, "a", encoding="utf-8") as f:
        f.write(gerar_metadados(numero, nome, projeto_cfg) + "\n")

# =============================================================================
# Geração da Coletânea
# =============================================================================

def gerar_coletanea(conn):
    print(f"\n{'='*60}")
    print("🎬  Gerando coletânea Meia Hora...")
    print(f"{'='*60}")

    rows = conn.execute(
        "SELECT numero, output FROM videos WHERE projeto = ? AND status = 'concluido' ORDER BY numero",
        (PROJETO_NOME,)
    ).fetchall()

    if not rows:
        print("[coletânea] Nenhum vídeo concluído encontrado.")
        return

    videos_validos = []
    for row in rows:
        out_path = (ROOT / row["output"]) if row["output"] else None
        if out_path and out_path.exists():
            videos_validos.append((row["numero"], out_path))
        else:
            num_fmt = formatar_numero_completo(row["numero"])
            saida = OUTPUT_DIR / f"hino-{PROJETO_NOME}-{num_fmt}.mp4"
            if saida.exists():
                videos_validos.append((row["numero"], saida))

    if not videos_validos:
        print("[coletânea] Nenhum arquivo de vídeo encontrado no disco.")
        return

    print(f"[coletânea] {len(videos_validos)} vídeos encontrados.")
    dur_total = sum(duracao_video(vp) for _, vp in videos_validos)
    print(f"[coletânea] Duração total estimada: {dur_total/60:.1f} minutos")

    lista_path = OUTPUT_DIR / "_lista_coletanea.txt"
    lista_path.write_text(
        "\n".join(f"file '{vp.name}'" for _, vp in videos_validos) + "\n",
        encoding="utf-8")

    coletanea_path = OUTPUT_DIR / "coletanea_meia_hora.mp4"
    print(f"[coletânea] Concatenando → {coletanea_path.relative_to(ROOT)}")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", lista_path.name, "-c", "copy", coletanea_path.name,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(OUTPUT_DIR))
    lista_path.unlink(missing_ok=True)

    dur_real = duracao_video(coletanea_path)
    print(f"\n✅  Coletânea gerada!")
    print(f"   Arquivo : {coletanea_path.relative_to(ROOT)}")
    print(f"   Duração : {int(dur_real//3600)}h {int((dur_real%3600)//60)}m {int(dur_real%60)}s")

    nomes = [f"Hino {n}" for n, _ in videos_validos]
    meta_out = ROOT / f"videos_gerados_{PROJETO_NOME}.md"
    with open(meta_out, "a", encoding="utf-8") as f:
        f.write(f"""
---
# COLETÂNEA — Hinos de Meia Hora

## Título para o vídeo
Hinos de Meia Hora | Coletânea Completa | Órgão Eletrônico Drawbar | CCB

## Descrição para o YouTube

Coletânea completa dos Hinos de Meia Hora — {len(videos_validos)} hinos do Hinário 5 tocados em órgão eletrônico drawbar, em andamento lento e contemplativo, para momentos de meditação, oração e adoração.

⏱️ Duração total: {int(dur_real//60)} minutos
🎹 Instrumento: Órgão Eletrônico Drawbar
📖 Hinário: Hinário 5 — Congregação Cristã no Brasil

Hinos incluídos: {', '.join(nomes[:10])}{'...' if len(nomes) > 10 else ''}

#HinosDeMeiaHora #HinosLentos #Hinario5 #CCB #MeditacaoCrista #OrgaoDrawbar

## Tags para YouTube

hinos de meia hora, hinos lentos ccb, hinário 5, coletânea hinos ccb, órgão drawbar,
hinos contemplativos, meditação cristã, adoração ccb, hinos instrumentais, ccb instrumental,
congregação cristã no brasil, hinos para oração, hinos para dormir, música cristã instrumental

---
""")
    print(f"   Metadados: videos_gerados_{PROJETO_NOME}.md")

# =============================================================================
# Processamento de um hino (com legendas)
# =============================================================================

def processar_hino(numero, mp3_path, nome, conn, projeto_cfg, pausa_entre_hinos=5.0):
    num_formatted = formatar_numero_completo(numero)
    print(f"\n[hino {num_formatted}] {nome}")
    print(f"  Projeto: {NOME_EXIBICAO}")

    # Resolver vinheta
    vinheta_efetiva = None
    vinheta_cfg = projeto_cfg.get("vinheta", "")
    if vinheta_cfg:
        candidata = Path(vinheta_cfg)
        if not candidata.is_absolute():
            candidata = ROOT / candidata
        if candidata.exists():
            vinheta_efetiva = candidata
            print(f"  Vinheta: {vinheta_efetiva.name}")
        else:
            print(f"  [aviso] Vinheta não encontrada: {vinheta_cfg}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Nomes de arquivo:
    # _base_NNN.mp4  = vídeo sem legenda (intermediário)
    # hino-meia_hora-NNN.mp4 = vídeo final com legenda
    saida_base     = OUTPUT_DIR / f"_base_{PROJETO_NOME}_{num_formatted}.mp4"
    saida_final    = OUTPUT_DIR / f"hino-{PROJETO_NOME}-{num_formatted}.mp4"
    saida_final.unlink(missing_ok=True)
    saida_base.unlink(missing_ok=True)

    for tmp in OUTPUT_DIR.glob(f"_*_{PROJETO_NOME}_{numero}*.mp4"):
        tmp.unlink(missing_ok=True)
    for tmp in OUTPUT_DIR.glob(f"_*hino-{PROJETO_NOME}-{num_formatted}*.mp4"):
        tmp.unlink(missing_ok=True)

    conn.execute(
        "UPDATE videos SET status = 'processando', atualizado_em = ? WHERE projeto = ? AND numero = ?",
        (now_iso(), PROJETO_NOME, numero))
    conn.commit()
    verificar_recursos(pausa_extra_s=pausa_entre_hinos)

    vinheta_norm = vinheta_audio_norm = None
    _temporarios = []
    try:
        dur_mp3_val = duracao_mp3(mp3_path)
        print(f"  Duração: {dur_mp3_val:.1f}s ({dur_mp3_val/60:.1f} min)")

        if vinheta_efetiva:
            print("  Normalizando vinheta...")
            vinheta_norm, vinheta_audio_norm = preparar_vinheta(vinheta_efetiva, OUTPUT_DIR)

        print("  Gerando frame inicial...")
        verificar_recursos()
        frame_mp4 = gerar_frame_video(numero, nome, projeto_cfg)
        _temporarios.append(frame_mp4)

        print("  Selecionando clipes de fundo...")
        clipes = selecionar_clipes(conn, dur_mp3_val, numero)
        print(f"  {len(clipes)} clipe(s) selecionado(s):")
        for idx, (caminho_str, dur) in enumerate(clipes, 1):
            print(f"    {idx:02d}. {Path(caminho_str).name} ({dur:.1f}s)")
        registrar_log_clipes(conn, PROJETO_NOME, numero, clipes)

        print("  Compondo vídeo de fundo...")
        verificar_recursos()
        fundo_mp4 = compor_video_fundo(clipes, dur_mp3_val, saida_base)
        _temporarios.append(fundo_mp4)

        print("  Montando vídeo base (sem legenda)...")
        verificar_recursos()
        dur_vin = montar_video_final(
            frame_mp4, fundo_mp4, mp3_path, saida_base, dur_mp3_val,
            vinheta_mp4=vinheta_norm, vinheta_audio=vinheta_audio_norm)

        for tmp in _temporarios:
            tmp.unlink(missing_ok=True)
        if vinheta_norm:
            vinheta_norm.unlink(missing_ok=True)
        if vinheta_audio_norm:
            vinheta_audio_norm.unlink(missing_ok=True)

        # ── Legenda ──────────────────────────────────────────────────────────
        mapa_legendas = carregar_legendas_do_json(mp3_path)

        if mapa_legendas:
            # offset = dur_vinheta + FRAME_DURATION
            offset_s = dur_vin + FRAME_DURATION
            print(f"  [legenda] Offset aplicado: {offset_s:.2f}s (vinheta={dur_vin:.2f}s + frame={FRAME_DURATION}s)")

            ass_path = OUTPUT_DIR / f"_legenda_{PROJETO_NOME}_{num_formatted}.ass"
            gerar_arquivo_ass(mapa_legendas, ass_path, f"Hino {numero} - {nome}", offset_s)
            print(f"  [legenda] Arquivo .ass gerado: {ass_path.name}")

            print("  [legenda] Embutindo legendas no vídeo...")
            embutir_legendas(saida_base, ass_path, saida_final)
            ass_path.unlink(missing_ok=True)
            saida_base.unlink(missing_ok=True)
            print(f"  ✓ Vídeo legendado: {saida_final.relative_to(ROOT)}")
        else:
            # Sem JSON de legendas: usar o vídeo base como saída final
            print("  [legenda] Sem dados de letra — usando vídeo base como saída.")
            saida_base.rename(saida_final)

        conn.execute(
            "UPDATE videos SET status = 'concluido', output = ?, atualizado_em = ? "
            "WHERE projeto = ? AND numero = ?",
            (str(saida_final.relative_to(ROOT)), now_iso(), PROJETO_NOME, numero))
        conn.commit()
        acrescentar_metadados(numero, nome, projeto_cfg)
        print(f"  ✓ Concluído: {saida_final.relative_to(ROOT)}")

    except Exception as e:
        for tmp in _temporarios:
            tmp.unlink(missing_ok=True)
        for tmp in OUTPUT_DIR.glob(f"_*hino-{PROJETO_NOME}-{num_formatted}*.mp4"):
            tmp.unlink(missing_ok=True)
        saida_base.unlink(missing_ok=True)
        if vinheta_norm:
            vinheta_norm.unlink(missing_ok=True)
        if vinheta_audio_norm:
            vinheta_audio_norm.unlink(missing_ok=True)
        conn.execute(
            "UPDATE videos SET status = 'erro', erro_msg = ?, atualizado_em = ? "
            "WHERE projeto = ? AND numero = ?",
            (str(e), now_iso(), PROJETO_NOME, numero))
        conn.commit()
        print(f"  ✗ ERRO: {e}")
        raise

# =============================================================================
# Programa principal
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=f"Gerador de vídeos COM LEGENDAS — Projeto '{PROJETO_NOME}' ({NOME_EXIBICAO})",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apenas", type=str, metavar="NUM",
                        help="Processa somente o hino com este número.")
    parser.add_argument("--resetar", type=str, nargs="?", const="ALL", metavar="NUM",
                        help="Reseta hino(s): '--resetar' (todos) ou '--resetar 1' (só o hino 1). Não apaga MP4s.")
    parser.add_argument("--resetar-todos", action="store_true",
                        help="Alias de --resetar (compat).")
    parser.add_argument("--forcar", type=str, nargs="?", const="ALL", metavar="NUM",
                        help="Apaga MP4/thumb e regera: '--forcar' (todos) ou '--forcar 1' (só o hino 1).")
    parser.add_argument("--forcar-todos", action="store_true",
                        help="Alias de --forcar (compat).")
    parser.add_argument("--sem-coletanea", action="store_true",
                        help="Pula a geração da coletânea ao final.")
    parser.add_argument("--so-coletanea", action="store_true",
                        help="Gera apenas a coletânea com os vídeos já prontos.")
    parser.add_argument("--pausa-entre-hinos", type=float, default=5.0, metavar="S",
                        help="Pausa em segundos entre hinos (padrão: 5).")
    parser.add_argument("--preset-ffmpeg", type=str, default=None,
                        help="Preset libx264: ultrafast/superfast/veryfast/faster/fast/medium.")
    parser.add_argument("--ram-limite", type=int, default=None, metavar="PCT",
                        help="Pausa automática se RAM ultrapassar este %% (padrão: 85).")
    args = parser.parse_args()

    global FFMPEG_PRESET, RAM_LIMITE_PCT
    if args.preset_ffmpeg:
        FFMPEG_PRESET = args.preset_ffmpeg
        print(f"[config] ffmpeg preset: {FFMPEG_PRESET}")
    if args.ram_limite is not None:
        RAM_LIMITE_PCT = args.ram_limite
        print(f"[config] RAM limite: {RAM_LIMITE_PCT}%")

    print(f"\n{'='*60}")
    print(f"  Projeto : {NOME_EXIBICAO}")
    print(f"  MP3s    : {MP3_DIR.relative_to(ROOT)}")
    print(f"  Saída   : {OUTPUT_DIR.relative_to(ROOT)}")
    print(f"  Legendas: automáticas (JSON companion)")
    print(f"{'='*60}\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    projeto_cfg = carregar_config_projeto()
    if not projeto_cfg:
        print(f"[aviso] config.json não encontrado em {PROJETO_DIR} — usando padrões.")

    mp3s = listar_mp3s()
    if not mp3s:
        print(f"ERRO: Nenhum MP3 encontrado em {MP3_DIR}")
        sys.exit(1)
    print(f"[mp3] {len(mp3s)} arquivo(s) encontrado(s) em {MP3_DIR.relative_to(ROOT)}")

    conn = abrir_banco()
    sincronizar_mp3s(conn, mp3s)
    sincronizar_clipes(conn)
    mp3_map = {num: (nome, path) for num, nome, path in mp3s}

    def _apagar_arquivos_hino(numero):
        """Remove MP4, thumb e temporários de um hino específico."""
        num_fmt = formatar_numero_completo(numero)
        removidos = []
        # MP4 final
        for p in [
            OUTPUT_DIR / f"hino-{PROJETO_NOME}-{num_fmt}.mp4",
            OUTPUT_DIR / f"_base_{PROJETO_NOME}_{num_fmt}.mp4",
        ]:
            if p.exists():
                p.unlink()
                removidos.append(p.name)
        # Thumb
        for p in THUMBS_DIR.glob(f"hino-{PROJETO_NOME}-{num_fmt}.*"):
            p.unlink()
            removidos.append(p.name)
        # Temporários
        for p in OUTPUT_DIR.glob(f"_*{PROJETO_NOME}*{numero}*.mp4"):
            p.unlink()
            removidos.append(p.name)
        if removidos:
            print(f"  [apagado] {', '.join(removidos)}")

    def _resetar_hino_db(conn, numero):
        conn.execute(
            "UPDATE clipes SET vezes_usado = MAX(0, vezes_usado - 1), "
            "projeto_usado = NULL, usado_em = NULL WHERE projeto_usado = ? AND usado_em = ?",
            (PROJETO_NOME, numero))
        conn.execute(
            "UPDATE videos SET status = 'pendente', output = NULL, erro_msg = NULL, "
            "atualizado_em = ? WHERE projeto = ? AND numero = ?",
            (now_iso(), PROJETO_NOME, numero))
        conn.commit()

    # ── --resetar[-todos] (só banco, não apaga MP4s) ───────────────────
    _resetar_req = args.resetar or ("ALL" if args.resetar_todos else None)
    if _resetar_req:
        if _resetar_req == "ALL":
            conn.execute("UPDATE videos SET status = 'pendente', atualizado_em = ? WHERE projeto = ?",
                         (now_iso(), PROJETO_NOME))
            conn.execute(
                "UPDATE clipes SET vezes_usado = MAX(0, vezes_usado - 1), "
                "projeto_usado = NULL, usado_em = NULL WHERE projeto_usado = ?",
                (PROJETO_NOME,))
            conn.commit()
            print(f"[reset] Todos os hinos de '{PROJETO_NOME}' marcados como pendente (MP4s mantidos).")
        else:
            try:
                num_reset = int(_resetar_req)
            except ValueError:
                num_reset = _resetar_req
            _resetar_hino_db(conn, num_reset)
            print(f"[reset] Hino {num_reset} marcado como pendente (MP4 mantido).")
        conn.close()
        return

    # ── --forcar[-todos] (apaga MP4s + banco + regera) ──────────────────
    _forcar_req = args.forcar or ("ALL" if args.forcar_todos else None)
    if _forcar_req:
        if _forcar_req == "ALL":
            print(f"[forcar] Apagando todos os vídeos de '{PROJETO_NOME}'...")
            todos = conn.execute(
                "SELECT numero FROM videos WHERE projeto = ? ORDER BY numero",
                (PROJETO_NOME,)).fetchall()
            for row in todos:
                _apagar_arquivos_hino(row["numero"])
            conn.execute(
                "UPDATE videos SET status = 'pendente', output = NULL, erro_msg = NULL, "
                "atualizado_em = ? WHERE projeto = ?", (now_iso(), PROJETO_NOME))
            conn.execute(
                "UPDATE clipes SET vezes_usado = MAX(0, vezes_usado - 1), "
                "projeto_usado = NULL, usado_em = NULL WHERE projeto_usado = ?",
                (PROJETO_NOME,))
            conn.commit()
            print(f"[forcar] {len(todos)} hino(s) reiniciados. Continuando geração...\n")
        else:
            try:
                num_forcar = int(_forcar_req)
            except ValueError:
                num_forcar = _forcar_req
            print(f"[forcar] Reiniciando hino {num_forcar}...")
            _apagar_arquivos_hino(num_forcar)
            _resetar_hino_db(conn, num_forcar)
            print(f"[forcar] Hino {num_forcar} pronto para reprocessamento. Continuando...\n")
        # Não retorna — continua para gerar

    if args.so_coletanea:
        gerar_coletanea(conn)
        conn.close()
        return

    if args.apenas:
        try:
            apenas_num = int(args.apenas)
        except ValueError:
            apenas_num = args.apenas
        pendentes = conn.execute(
            "SELECT numero, mp3_file FROM videos WHERE projeto = ? AND numero = ?",
            (PROJETO_NOME, apenas_num)).fetchall()
    else:
        pendentes = conn.execute(
            "SELECT numero, mp3_file FROM videos "
            "WHERE status = 'pendente' AND projeto = ? ORDER BY numero",
            (PROJETO_NOME,)).fetchall()

    if not pendentes:
        print(f"Nada a processar para '{PROJETO_NOME}'. Todos os hinos já foram gerados.")
        if not args.sem_coletanea and not args.apenas:
            gerar_coletanea(conn)
        conn.close()
        return

    print(f"{len(pendentes)} hino(s) a processar.\n")

    for row in pendentes:
        numero   = row["numero"]
        mp3_path = ROOT / row["mp3_file"]
        nome     = mp3_map.get(numero, (f"Hino {numero}", None))[0]
        if not mp3_path.exists():
            print(f"[aviso] MP3 não encontrado: {mp3_path} — pulando.")
            continue
        processar_hino(numero, mp3_path, nome, conn, projeto_cfg,
                       pausa_entre_hinos=args.pausa_entre_hinos)

    if not args.sem_coletanea and not args.apenas:
        gerar_coletanea(conn)

    conn.close()
    print(f"\n✓ Projeto '{NOME_EXIBICAO}' concluído.")


if __name__ == "__main__":
    main()
