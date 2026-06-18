#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_thumb_v01.py — Gerador de Thumbnails (Pipeline v01)
Canal: Hinário 5 - Congregação Cristã no Brasil

═══════════════════════════════════════════════════════════════════════
PILHA DE COMPOSIÇÃO (1920 × 1080 px, 16:9)
═══════════════════════════════════════════════════════════════════════
  Layer 1 ─ Frame de vídeo
            Um frame aleatório extraído de um clipe MP4 (videos_flores/
            ou Photos-1-001/), redimensionado para 1920×1080. Sem blur.

  Layer 2 ─ Overlay de cor (color grading)
            Camada de cor sólida semitransparente aplicada sobre o frame
            no modo "multiply" ou "overlay", seguida de vinheta radial
            que escurece as bordas. Define a atmosfera do preset.

  Layer 3 ─ Arte de linhas decorativa
            Imagem P&B de assets/texturas/arte-linhas/ usada como clarão
            artístico (branco = aparece, preto = transparente, 12% opac).

  Layer 4 ─ Máscara do canal (identidade visual)
            assets/mascaras/mascara-do-canal.png composta por alpha
            composite. Traz: moldura dourada, bloco verde escuro lateral
            esquerdo, faixa bege inclinada no topo esquerdo e logo CCB.

  Layer 5 ─ Número do hino
            Renderizado em canvas RGBA, rotacionado +3.5°, centralizado
            na faixa bege da máscara. Sombra creme #FBF4D9. Cor #6B8F4F.
            Offset lateral extra para números de 3 dígitos.

  Layer 6 ─ Nome do hino
            Texto em caixa alta, multi-linha, com fonte adaptativa.
            Rotacionado +3.5° (mesmo sentido do número). Sombra difusa
            verde-escuro #3A4A2D (GaussianBlur r=10) + sombra sharp.
            Cores alternadas entre título_cor e título_acento do preset.

  Layer 7 ─ Instrumento
            PNG sem fundo do instrumento (piano, órgão, teclado ou
            caixinha de música), escalado para 100% da altura da imagem,
            alinhado à direita e à base. Sombra em 2 passes de blur.

═══════════════════════════════════════════════════════════════════════
USO
═══════════════════════════════════════════════════════════════════════
  # Gera 10 thumbs aleatórias:
  python gerar_thumb_v01.py

  # Gera hinos específicos:
  python gerar_thumb_v01.py --numero 53 328 5

  # Usa preset de cor fixo (0 a 7):
  python gerar_thumb_v01.py --numero 53 --preset 2

  # Lista presets disponíveis:
  python gerar_thumb_v01.py --listar-presets

  # Seed determinístico (mesmo resultado a cada execução):
  python gerar_thumb_v01.py --numero 53 --seed 42

═══════════════════════════════════════════════════════════════════════
DEPENDÊNCIAS
═══════════════════════════════════════════════════════════════════════
  pip install Pillow
  brew install ffmpeg   (para extração de frames)
"""

import os
import csv
import random
import subprocess
import tempfile
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ─── CAMINHOS ─────────────────────────────────────────────────────────────────
# Todos os caminhos são relativos à localização deste script.
BASE_DIR         = Path(__file__).parent
VIDEOS_DIR_1     = BASE_DIR / "videos_flores"        # Clipes de flores/natureza (Pexels)
VIDEOS_DIR_2     = BASE_DIR / "Photos-1-001"         # Clipes adicionais (biblioteca local)
INSTRUMENTOS_DIR = BASE_DIR / "assets" / "instrumentos"  # PNGs dos instrumentos (sem fundo)
FONTES_DIR       = BASE_DIR / "fontes"               # Fontes TrueType e arquivos CSV
OUTPUT_DIR       = BASE_DIR / "thumbs" / "v01"       # Pasta de saída das thumbnails
CSV_FILE         = FONTES_DIR / "hinario5.csv"       # Lista de hinos: Número, Nome
FONT_PATH        = FONTES_DIR / "Montserrat.ttf"     # Fonte principal (variável, weight 400-900)
MASCARA_PATH     = BASE_DIR / "assets" / "mascaras" / "mascara-do-canal.png"  # Overlay identidade visual

# ─── IDENTIDADE VISUAL ────────────────────────────────────────────────────────
# Paleta de cores base do canal CCB.
VERDE_OLIVA  = (72,  91,  70)   # Verde característico da moldura do canal
VERDE_ESCURO = (38,  52,  36)   # Fundo de fallback quando não há clipe de vídeo
CREME        = (242, 238, 227)  # Cor da faixa bege na máscara e texto padrão
DOURADO      = (210, 180, 100)  # Acento dourado para linhas pares do título

# ─── GEOMETRIA DA FAIXA BEGE (retângulo inclinado na máscara) ─────────────────
# A máscara original tem resolução 1672×941. Este script gera 1920×1080.
# As coordenadas do retângulo inclinado foram mapeadas manualmente por análise
# de pixels na máscara original e depois escaladas para a resolução de saída.
MASK_W_ORIG, MASK_H_ORIG = 1672, 941
SCALE_X = 1920 / MASK_W_ORIG   # ≈ 1.148x
SCALE_Y = 1080 / MASK_H_ORIG   # ≈ 1.147x

# Vértices do paralelogramo (na resolução original da máscara):
# Ordem: topo-esq, topo-dir, base-dir, base-esq
RECT_ORIG = [
    (22,  28),   # topo esquerdo
    (598, 28),   # topo direito
    (502, 210),  # base direita
    (10,  210),  # base esquerda
]
# Vértices escalados para 1920×1080 (usados em todas as funções de tipografia)
RECT_SCALED = [(int(x * SCALE_X), int(y * SCALE_Y)) for x, y in RECT_ORIG]

# ─── PRESETS DE COR ───────────────────────────────────────────────────────────
# Cada preset define a atmosfera visual de uma thumbnail:
#   "cor"              : cor RGB do overlay de color grading
#   "opacidade"        : 0.0 = só o frame, 1.0 = cor pura
#   "modo"             : "multiply" (escurece/satura) ou "overlay" (contraste)
#   "vignette"         : True para aplicar vinheta radial escura nas bordas
#   "vignette_intensidade": 0.0–1.0 (força da vinheta)
#   "num_cor"          : cor RGB do número do hino
#   "titulo_cor"       : cor RGB das linhas pares do título
#   "titulo_acento"    : cor RGB das linhas ímpares do título (acento/destaque)
COLOR_PRESETS = [
    {
        "nome": "Verde Oliva CCB",
        "cor": (72, 91, 70),        "opacidade": 0.40,  "modo": "multiply",
        "vignette": True,           "vignette_intensidade": 0.40,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": DOURADO,
    },
    {
        "nome": "Sépia Quente",
        "cor": (160, 120, 60),      "opacidade": 0.30,  "modo": "overlay",
        "vignette": True,           "vignette_intensidade": 0.35,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": (220, 190, 120),
    },
    {
        "nome": "Verde Musgo",
        "cor": (40, 70, 55),        "opacidade": 0.38,  "modo": "multiply",
        "vignette": True,           "vignette_intensidade": 0.42,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": (160, 220, 180),
    },
    {
        "nome": "Cobre Outonal",
        "cor": (130, 80, 40),       "opacidade": 0.35,  "modo": "overlay",
        "vignette": True,           "vignette_intensidade": 0.38,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": (240, 200, 140),
    },
    {
        "nome": "Verde Floresta",
        "cor": (30, 80, 50),        "opacidade": 0.38,  "modo": "multiply",
        "vignette": True,           "vignette_intensidade": 0.40,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": (170, 230, 190),
    },
    {
        "nome": "Terracota Sagrado",
        "cor": (140, 70, 55),       "opacidade": 0.32,  "modo": "overlay",
        "vignette": True,           "vignette_intensidade": 0.38,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": (230, 180, 150),
    },
    {
        "nome": "Âmbar Dourado",
        "cor": (170, 130, 50),      "opacidade": 0.30,  "modo": "overlay",
        "vignette": True,           "vignette_intensidade": 0.35,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": (240, 210, 130),
    },
    {
        "nome": "Verde Sálvia",
        "cor": (90, 110, 80),       "opacidade": 0.38,  "modo": "multiply",
        "vignette": True,           "vignette_intensidade": 0.40,
        "num_cor": CREME,           "titulo_cor": CREME,
        "titulo_acento": DOURADO,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS GERAIS
# ═══════════════════════════════════════════════════════════════════════════════

def get_font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """
    Carrega a fonte Montserrat no tamanho e peso solicitados.

    Args:
        size:   Tamanho em pontos (px equivalente em PIL).
        weight: Peso da fonte (400=regular, 700=bold, 800=extrabold, 900=black).
                Usa variação de eixo se a fonte for variável; caso contrário ignora.

    Returns:
        FreeTypeFont carregada, ou fonte padrão PIL se Montserrat não for encontrada.
    """
    try:
        f = ImageFont.truetype(str(FONT_PATH), size)
        try:
            f.set_variation_by_axes([weight])  # Montserrat Variable
        except Exception:
            pass  # Fonte não suporta variação — usa o arquivo como está
        return f
    except Exception:
        return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """
    Quebra um texto em múltiplas linhas respeitando a largura máxima.

    Algoritmo guloso: adiciona palavras à linha atual enquanto couberem;
    ao estourar a largura, começa nova linha.

    Args:
        text:      Texto a quebrar (já em CAIXA ALTA normalmente).
        font:      Fonte usada para medir o texto.
        max_width: Largura máxima em pixels.
        draw:      Objeto ImageDraw temporário para medir os textos.

    Returns:
        Lista de strings, uma por linha.
    """
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — FRAME DE VÍDEO
# ═══════════════════════════════════════════════════════════════════════════════

def get_video_frame(video_dirs: list[Path], width: int = 1920, height: int = 1080) -> Image.Image | None:
    """
    Extrai um frame aleatório de um clipe de vídeo usando ffmpeg.

    Escolhe aleatoriamente um vídeo entre todas as pastas fornecidas,
    sorteia um timestamp entre 5% e 95% da duração (evitando início/fim),
    e extrai um único frame redimensionado para width×height.

    Args:
        video_dirs: Lista de Path para as pastas que contêm os vídeos.
        width:      Largura desejada do frame (padrão 1920).
        height:     Altura desejada do frame (padrão 1080).

    Returns:
        Imagem PIL em modo RGB, ou None se não houver vídeos disponíveis
        ou se a extração falhar.
    """
    # Coleta todos os vídeos válidos nas pastas fornecidas
    all_videos = []
    for vdir in video_dirs:
        if vdir.exists():
            exts = {".mp4", ".mov", ".MP4", ".MOV"}
            all_videos.extend(
                str(v) for v in vdir.iterdir()
                if v.suffix in exts and not v.name.startswith("._")
            )
    if not all_videos:
        return None

    video = random.choice(all_videos)
    print(f"  Vídeo: {Path(video).name}")

    # Obtém a duração do vídeo via ffprobe
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video],
            capture_output=True, text=True, timeout=10
        )
        duration = float(probe.stdout.strip())
    except Exception:
        duration = 30.0  # fallback conservador

    # Sorteia timestamp evitando os primeiros/últimos 5% do clipe
    margin = max(2.0, duration * 0.05)
    t = random.uniform(margin, duration - margin)

    # Extrai o frame com ffmpeg para um arquivo temporário
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-ss", str(t), "-i", video,
             "-vframes", "1", "-vf",
             f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
             "-q:v", "2", "-y", tmp_path],
            capture_output=True, timeout=30
        )
        frame = Image.open(tmp_path).convert("RGB").resize((width, height), Image.LANCZOS)
        return frame
    except Exception as e:
        print(f"  Erro frame: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — OVERLAY DE COR E VINHETA
# ═══════════════════════════════════════════════════════════════════════════════

def apply_blur(img: Image.Image, radius: int = 4) -> Image.Image:
    """Aplica desfoque gaussiano à imagem (não usado no pipeline atual, mantido para testes)."""
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def blend_color_overlay(base: Image.Image, color: tuple, opacity: float, mode: str = "multiply") -> Image.Image:
    """
    Aplica um overlay de cor sólida sobre a imagem base.

    Simula os modos "multiply" e "overlay" do Photoshop através de um
    blend linear simples entre a imagem original e uma camada de cor pura.

    Args:
        base:    Imagem PIL RGB de entrada.
        color:   Cor RGB do overlay (ex: (72, 91, 70)).
        opacity: Fração da cor aplicada — 0.0 = sem efeito, 1.0 = cor pura.
        mode:    "multiply" ou "overlay" (semanticamente idênticos aqui;
                 a diferença visual vem da própria cor escolhida no preset).

    Returns:
        Nova imagem PIL RGB com o overlay aplicado.
    """
    w, h = base.size
    overlay = Image.new("RGB", (w, h), color)
    return Image.blend(base, overlay, opacity)


def apply_fast_vignette(img: Image.Image, intensidade: float = 0.5) -> Image.Image:
    """
    Aplica uma vinheta radial que escurece as bordas da imagem.

    Desenha elipses concêntricas com alpha crescente do centro para as bordas,
    criando um efeito de escurecimento suave e gradual nas extremidades.

    Args:
        img:        Imagem PIL RGB de entrada.
        intensidade: Força da vinheta — 0.0 = nenhuma, 1.0 = bordas pretas.

    Returns:
        Imagem PIL RGB com a vinheta aplicada.
    """
    w, h = img.size
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)
    steps = 40  # Número de elipses concêntricas para suavidade
    for i in range(steps, 0, -1):
        ratio = i / steps
        alpha = int(255 * intensidade * (1 - ratio))
        # Cada elipse ocupa uma fração da área total, criando o gradiente
        mx = int(w * (1 - ratio) / 2 * 1.5)
        my = int(h * (1 - ratio) / 2 * 1.5)
        x0, y0, x1, y1 = mx, my, w - mx, h - my
        if x1 > x0 and y1 > y0:
            draw.ellipse([x0, y0, x1, y1], fill=(0, 0, 0, alpha))
    result = img.convert("RGBA")
    result = Image.alpha_composite(result, mask)
    return result.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 7 — INSTRUMENTO (canto inferior direito, altura total)
# ═══════════════════════════════════════════════════════════════════════════════

def get_instrumento(exclude: str | None = None, path: str | None = None) -> tuple[Image.Image | None, str | None]:
    """
    Carrega um PNG de instrumento da pasta assets/instrumentos/.

    Modo fixo (path fornecido):
      Carrega diretamente o arquivo apontado por path. Usado quando o projeto
      define um instrumento fixo em projetos.json (campo "instrumento").

    Modo aleatório (path=None):
      Escolhe aleatoriamente entre os PNGs disponíveis, excluindo opcionalmente
      um arquivo já usado (para evitar repetir o mesmo instrumento em duas posições).

    Args:
        exclude: Nome de arquivo a excluir da seleção aleatória.
        path:    Caminho fixo para um instrumento específico (relativo a BASE_DIR
                 ou absoluto). Quando fornecido, ignora INSTRUMENTOS_DIR e exclude.

    Returns:
        Tupla (imagem_RGBA, nome_do_arquivo) ou (None, None) se não encontrado.
    """
    if path:
        # Modo fixo: carrega o instrumento definido pelo projeto
        instr_path = Path(path) if Path(path).is_absolute() else BASE_DIR / path
        if instr_path.exists():
            print(f"  Instrumento: {instr_path.name} (fixo)")
            return Image.open(instr_path).convert("RGBA"), instr_path.name
        else:
            print(f"  AVISO: instrumento não encontrado: {instr_path}")
            return None, None

    # Modo aleatório
    instrumentos = [
        f for f in INSTRUMENTOS_DIR.iterdir()
        if f.suffix.lower() == ".png" and not f.name.startswith("._")
    ]
    if not instrumentos:
        return None, None
    if exclude is not None and len(instrumentos) > 1:
        instrumentos = [f for f in instrumentos if f.name != exclude]
    escolha = random.choice(instrumentos)
    print(f"  Instrumento: {escolha.name} (aleatório)")
    return Image.open(escolha).convert("RGBA"), escolha.name


def composite_instrumento_direita(base_img: Image.Image, instrumento_img: Image.Image) -> Image.Image:
    """
    Cola o instrumento no canto direito da imagem, ocupando 100% da altura.

    O instrumento é escalado de modo que sua altura bata exatamente com a
    altura total da imagem (1080px). A largura escala proporcionalmente.
    Alinhado à borda direita e ao topo (y=0).

    Aplica duas camadas de sombra projetada com GaussianBlur para profundidade:
      - Sombra difusa: raio 40, offset 32px, alpha 28%
      - Sombra nítida: raio 12, offset 14px, alpha 48%

    Args:
        base_img:       Imagem PIL RGB de fundo.
        instrumento_img: Imagem PIL RGBA do instrumento (fundo transparente).

    Returns:
        Nova imagem PIL RGB com o instrumento composto.
    """
    w, h = base_img.size

    # Escala para preencher 100% da altura; a largura segue o aspect ratio
    orig_w, orig_h = instrumento_img.size
    th = h                          # altura total da imagem
    tw = int(orig_w * th / orig_h)  # largura proporcional
    instr = instrumento_img.resize((tw, th), Image.LANCZOS)

    # Alinhado pela direita e pela base
    x = w - tw
    y = 0   # topo = 0 para preencher até a base

    # Sombra em duas camadas
    r, g, b, a = instr.split()
    base_rgba = base_img.convert("RGBA")
    for blur_r, offset, alpha_mult in [(40, 32, 0.28), (12, 14, 0.48)]:
        sh_a = a.point(lambda p: int(p * alpha_mult))
        sh = Image.new("RGBA", instr.size, (0, 0, 0, 0))
        sh.putalpha(sh_a)
        sh = sh.filter(ImageFilter.GaussianBlur(radius=blur_r))
        sx = min(x + offset, w - 1)
        sy = min(y + offset, h - 1)
        base_rgba.paste(sh, (sx, sy), sh)
    base_rgba.paste(instr, (x, y), instr)
    return base_rgba.convert("RGB")


def composite_instrumento_esquerda(base_img: Image.Image, instrumento_img: Image.Image) -> Image.Image:
    """
    Cola instrumento no canto inferior ESQUERDO (versão menor, não usada no pipeline atual).

    Mantida como alternativa para layouts que precisam do instrumento à esquerda.
    Usa tamanho mais contido (28% largura, 55% altura) para não sobrepor o título.
    """
    w, h = base_img.size
    # Máximo 28% da largura e 55% da altura – instrumento menor na esquerda
    max_w = int(w * 0.28)
    max_h = int(h * 0.55)
    orig_w, orig_h = instrumento_img.size
    ratio = min(max_w / orig_w, max_h / orig_h)
    tw, th = int(orig_w * ratio), int(orig_h * ratio)
    instr = instrumento_img.resize((tw, th), Image.LANCZOS)
    x = 20            # pequena margem da borda esquerda
    y = h - th - 20  # margem da base

    # Sombra suave
    r, g, b, a = instr.split()
    base_rgba = base_img.convert("RGBA")
    for blur_r, offset, alpha_mult in [(18, 12, 0.30), (5, 5, 0.45)]:
        sh_a = a.point(lambda p: int(p * alpha_mult))
        sh = Image.new("RGBA", instr.size, (0, 0, 0, 0))
        sh.putalpha(sh_a)
        sh = sh.filter(ImageFilter.GaussianBlur(radius=blur_r))
        sx = min(x + offset, w - 1)
        sy = min(y + offset, h - 1)
        base_rgba.paste(sh, (sx, sy), sh)
    base_rgba.paste(instr, (x, y), instr)
    return base_rgba.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — ARTE DE LINHAS (textura artística decorativa)
# ═══════════════════════════════════════════════════════════════════════════════

ARTE_LINHAS_DIR = BASE_DIR / "assets" / "texturas" / "arte-linhas"

def composite_arte_linhas(base_img: Image.Image) -> Image.Image:
    """
    Sobrepõe uma textura artística P&B sobre a imagem como clarão suave.

    As imagens em assets/texturas/arte-linhas/ são em preto e branco:
      - Pixels brancos → aparecem como clarão (branco semitransparente)
      - Pixels pretos  → totalmente transparentes (não afetam a imagem)

    A opacidade máxima é 12% (alpha máx 30/255), criando um padrão
    decorativo muito sutil que não compete com o conteúdo principal.

    Args:
        base_img: Imagem PIL RGB de entrada.

    Returns:
        Imagem PIL RGB com a textura aplicada, ou a imagem original se
        não houver imagens na pasta.
    """
    artes = sorted(ARTE_LINHAS_DIR.glob("arte*.png"))
    if not artes:
        return base_img
    arte_path = random.choice(artes)

    w, h = base_img.size
    # Converte para escala de cinza: brilho = intensidade do clarão
    arte = Image.open(arte_path).convert("L").resize((w, h), Image.LANCZOS)

    # Cria camada branca com alpha proporcional ao brilho do pixel original
    # Fórmula: alpha = brilho × 0.12, máximo 30/255 ≈ 12%
    white_layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    alpha = arte.point(lambda p: min(int(p * 0.12), 30))  # 12% max
    white_layer.putalpha(alpha)

    base_rgba = base_img.convert("RGBA")
    base_rgba = Image.alpha_composite(base_rgba, white_layer)
    return base_rgba.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — MÁSCARA DO CANAL (identidade visual)
# ═══════════════════════════════════════════════════════════════════════════════

def composite_mascara(base_img: Image.Image) -> Image.Image:
    """
    Compõe a máscara do canal sobre a imagem base usando alpha composite.

    A máscara (assets/mascaras/mascara-do-canal.png) é um PNG RGBA que traz:
      - Moldura dourada nas bordas
      - Bloco verde escuro no canto inferior esquerdo (logotipo CCB)
      - Faixa bege inclinada no topo esquerdo (área do número do hino)
      - Elementos decorativos (folhas, notas musicais, arabescos)

    Args:
        base_img: Imagem PIL RGB de entrada.

    Returns:
        Imagem PIL RGB com a máscara aplicada.
    """
    w, h = base_img.size
    mask = Image.open(MASCARA_PATH).convert("RGBA").resize((w, h), Image.LANCZOS)
    base_rgba = base_img.convert("RGBA")
    base_rgba = Image.alpha_composite(base_rgba, mask)
    return base_rgba.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 5 — NÚMERO DO HINO (tipografia na faixa bege)
# ═══════════════════════════════════════════════════════════════════════════════

def fit_text_in_parallelogram(
    img: Image.Image,
    text: str,
    rect_pts: list[tuple[int, int]],
    font_max: int = 240,
    color: tuple = (107, 143, 79)
):
    """
    Renderiza o número do hino centralizado na faixa bege inclinada da máscara.

    Técnica de rotação em canvas RGBA:
      1. Mede o texto em tamanho máximo que caiba na área disponível.
      2. Desenha o texto em um canvas RGBA transparente (com sombra creme).
      3. Rotaciona o canvas em +3.5° (counter-clockwise no PIL).
      4. Cola o canvas na imagem principal, centrado no ponto (STRIP_CX, STRIP_CY).

    ÂNGULOS:
      - CSS rotate(-3.5deg) = inclinação "para baixo à direita"
      - Em PIL: rotate(+3.5) produz o mesmo efeito visual (sistema invertido)
      - O título usa o mesmo ângulo +3.5° para consistência

    CENTRALIZAÇÃO:
      - O centro visual real da faixa creme foi determinado por amostragem
        de pixels na máscara: (416, 158) para 1 e 2 dígitos.
      - Números de 3 dígitos recebem +25px à direita para compensar a largura.
      - Todos recebem +25px abaixo do topo para margem superior.

    Args:
        img:      Imagem PIL RGB de destino (modificada in-place via paste).
        text:     String do número do hino (ex: "53", "328").
        rect_pts: Lista de 4 vértices do paralelogramo (RECT_SCALED).
        font_max: Tamanho máximo de fonte a tentar (padrão 240).
        color:    Cor RGB do número (padrão verde médio #6B8F4F).
    """
    ANGLE_DEG = 3.5  # +3.5° = counter-clockwise no PIL

    # Centro visual da faixa creme (medido por amostragem de pixels na máscara)
    # O centróide geométrico seria (324, 136) mas a área visível está mais à direita
    STRIP_CX = 416
    STRIP_CY = 158 + 25   # margem superior aplicada a todos os tamanhos
    if len(text) == 3:
        # Números de 3 dígitos são mais largos: desloca o centro para a direita
        STRIP_CX += 25

    # Calcula a área disponível com base nos vértices do paralelogramo
    top_w = abs(rect_pts[1][0] - rect_pts[0][0])
    bot_w = abs(rect_pts[2][0] - rect_pts[3][0])
    avail_w = (top_w + bot_w) / 2 * 0.70   # 70% da largura média (margens)
    avail_h = abs(rect_pts[2][1] - rect_pts[0][1]) * 0.68  # 68% da altura

    # Busca o maior tamanho de fonte que caiba na área disponível
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    font_size = font_max
    font = get_font(font_size, weight=900)  # Montserrat Black
    while font_size > 40:
        tb = dummy.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        if tw <= avail_w and th <= avail_h:
            break
        font_size -= 8
        font = get_font(font_size, weight=900)

    tb = dummy.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]

    # Canvas RGBA transparente com padding para absorver a rotação sem cortar
    pad = 60
    canvas = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(canvas)

    # Sombra creme #FBF4D9 em dois passes (offset 5px e 3px) para profundidade
    for off in [5, 3]:
        cdraw.text(
            (pad - tb[0] + off, pad - tb[1] + off),
            text, font=font, fill=(251, 244, 217, 220)
        )
    # Número principal na cor definida (verde #6B8F4F por padrão)
    cdraw.text((pad - tb[0], pad - tb[1]), text, font=font, fill=(*color, 255))

    # Rotaciona o canvas e compõe na imagem principal
    rotated = canvas.rotate(ANGLE_DEG, expand=True, resample=Image.BICUBIC)
    rx, ry = rotated.size
    paste_x = int(STRIP_CX - rx / 2)
    paste_y = int(STRIP_CY - ry / 2)

    base = img.convert("RGBA")
    base.paste(rotated, (paste_x, paste_y), rotated)
    img.paste(base.convert("RGB"))


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 6 — NOME DO HINO (tipografia abaixo da faixa)
# ═══════════════════════════════════════════════════════════════════════════════

def draw_titulo(img: Image.Image, titulo_hino: str, preset: dict):
    """
    Renderiza o nome do hino abaixo da faixa bege, em caixa alta e rotacionado.

    Técnica de rotação em canvas RGBA (igual ao número):
      1. Calcula a posição vertical: abaixo do ponto mais baixo de RECT_SCALED + 120px.
      2. Determina a fonte adaptativa (tenta 108px, reduz até 64 se > 3 linhas).
      3. Renderiza a sombra difusa em canvas separado → GaussianBlur(r=10).
      4. Compõe sombra + texto principal no canvas final.
      5. Rotaciona +3.5° e cola na imagem.

    SOMBRAS:
      - Difusa: creme claro #FBF4D9, offset 10px, alpha 200/255, blur raio 10
        → clarão suave que realça o texto escuro
      - Sharp: branco, offset 3px, alpha 130/255
        → nítidez e definição das bordas dos caracteres

    CORES:
      - Linhas pares  (0, 2, ...): verde floresta escuro #3A4A2D
      - Linhas ímpares (1, 3, ...): verde oliva médio #485B46

    Args:
        img:         Imagem PIL RGB de destino (modificada in-place).
        titulo_hino: Nome do hino (ex: "Nós somos luz do mundo").
        preset:      Dicionário de preset com "titulo_cor" e "titulo_acento".
    """
    w, h = img.size

    # Posição: abaixo do retângulo inclinado + margem de 120px
    ys = [p[1] for p in RECT_SCALED]
    xs = [p[0] for p in RECT_SCALED]
    rect_bottom = max(ys) + 120
    rect_left   = min(xs) + 80
    max_text_w  = 680   # largura máxima da coluna de texto

    titulo_upper = titulo_hino.upper()
    test_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # Fonte adaptativa: começa em 108px, reduz se ultrapassar 3 linhas
    font_size = 108
    font = get_font(font_size, weight=800)
    linhas = wrap_text(titulo_upper, font, max_text_w, test_draw)
    for fallback in [90, 76, 64]:
        if len(linhas) > 3:
            font_size = fallback
            font = get_font(font_size, weight=800)
            linhas = wrap_text(titulo_upper, font, max_text_w, test_draw)
        else:
            break

    linhas = linhas[:4]             # Limite absoluto de 4 linhas
    linha_h = font_size + 14        # Altura de linha com espaçamento

    # Dimensões do canvas: texto + padding para acomodar sombra e rotação
    total_h = linha_h * len(linhas)
    total_w = max_text_w + 40
    pad = 40
    canvas_w = total_w + pad * 2
    canvas_h = total_h + pad * 2

    # ── Sombra halo amplo creme (muito suave, grande, translúcida) ───────────
    SOMBRA_COR = (251, 244, 217)  # #FBF4D9 — creme claro
    halo_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(halo_canvas)
    cy_off = pad
    for linha in linhas:
        hdraw.text((pad + 18, cy_off + 18), linha, font=font, fill=(*SOMBRA_COR, 90))
        cy_off += linha_h
    halo_canvas = halo_canvas.filter(ImageFilter.GaussianBlur(radius=28))

    # ── Sombra difusa creme claro #FBF4D9 (render separado + blur) ──────────
    sombra_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(sombra_canvas)
    cy_off = pad
    for linha in linhas:
        sdraw.text((pad + 10, cy_off + 10), linha, font=font, fill=(*SOMBRA_COR, 200))
        cy_off += linha_h
    sombra_canvas = sombra_canvas.filter(ImageFilter.GaussianBlur(radius=10))

    # ── Canvas principal: halo + sombra difusa + sombra sharp + texto ────────
    canvas = Image.alpha_composite(Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0)), halo_canvas)
    canvas = Image.alpha_composite(canvas, sombra_canvas)
    cdraw = ImageDraw.Draw(canvas)

    # Cores escuras do texto: verde floresta (par) e verde oliva (ímpar)
    COR_PAR    = (58,  74,  45)   # #3A4A2D — verde floresta escuro
    COR_IMPAR  = (72,  91,  70)   # #485B46  — verde oliva médio

    cy_off = pad
    for i, linha in enumerate(linhas):
        # Alterna entre as duas cores escuras
        cor = COR_PAR if i % 2 == 0 else COR_IMPAR
        # Sombra sharp pequena clara (branco, definição das bordas)
        cdraw.text((pad + 3, cy_off + 3), linha, font=font, fill=(255, 255, 255, 130))
        # Texto principal escuro
        cdraw.text((pad, cy_off), linha, font=font, fill=(*cor, 255))
        cy_off += linha_h

    # Rotação +3.5° (mesmo ângulo do número, sistema consistente)
    rotated = canvas.rotate(3.5, expand=True, resample=Image.BICUBIC)

    # Cola ancorado no canto superior esquerdo da área do título
    paste_x = rect_left - pad
    paste_y = rect_bottom - pad

    base = img.convert("RGBA")
    base.paste(rotated, (paste_x, paste_y), rotated)
    img.paste(base.convert("RGB"))

    # Rodapé discreto (texto sem rotação, canto inferior esquerdo)
    draw = ImageDraw.Draw(img)
    rodape_font = get_font(24, weight=400)
    draw.text((rect_left, h - 52), "♪ HINARIO 5 - CCB", font=rodape_font, fill=(*CREME, 130))


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def gerar_thumb(
    numero_hino: int,
    titulo_hino: str,
    output_path: str | Path,
    seed: int | None = None,
    preset_idx: int | None = None,
    instrumento_path: str | None = None,
) -> Image.Image:
    """
    Executa o pipeline completo de geração de thumbnail para um hino.

    Monta os 7 layers em sequência e salva o resultado como JPEG qualidade 95.
    Pode ser chamado tanto pelo CLI deste módulo quanto importado por outros
    scripts (ex: gerar_thumbs_batch.py, gerar_videos.py).

    Args:
        numero_hino:     Número do hino (inteiro, ex: 53).
        titulo_hino:     Nome completo do hino (ex: "Nós somos luz do mundo").
        output_path:     Caminho de saída para o arquivo JPEG.
        seed:            Semente aleatória para resultados determinísticos.
                         None = aleatório a cada execução.
        preset_idx:      Índice fixo do preset de cor (0–7).
                         None = preset aleatório.
        instrumento_path: Caminho para o PNG do instrumento a usar (relativo
                         a BASE_DIR ou absoluto). Quando None, escolhe
                         aleatoriamente de assets/instrumentos/.

    Returns:
        Objeto Image PIL com a thumbnail final (também salva em output_path).
    """
    if seed is not None:
        random.seed(seed)

    W, H = 1920, 1080

    # Seleciona o preset de cor (aleatório ou fixo)
    if preset_idx is not None:
        preset = COLOR_PRESETS[preset_idx % len(COLOR_PRESETS)]
    else:
        preset = random.choice(COLOR_PRESETS)

    print(f"\n[Hino {numero_hino}] {titulo_hino}")
    print(f"  Preset: {preset['nome']}")

    # ── LAYER 1: Frame de vídeo ───────────────────────────────────────────────
    frame = get_video_frame([VIDEOS_DIR_1, VIDEOS_DIR_2], W, H)
    if frame is None:
        # Fallback: fundo de cor sólida quando não há vídeos disponíveis
        frame = Image.new("RGB", (W, H), VERDE_ESCURO)

    # ── LAYER 2: Overlay de cor + vinheta ────────────────────────────────────
    resultado = blend_color_overlay(frame, preset["cor"], preset["opacidade"], preset["modo"])
    if preset.get("vignette"):
        resultado = apply_fast_vignette(resultado, preset["vignette_intensidade"])

    # ── LAYER 3: Arte de linhas decorativa (12% opacidade) ───────────────────
    resultado = composite_arte_linhas(resultado)

    # ── LAYER 4: Máscara do canal (identidade visual) ────────────────────────
    if MASCARA_PATH.exists():
        resultado = composite_mascara(resultado)
    else:
        print("  AVISO: mascara-do-canal.png não encontrada em assets/mascaras/")

    # ── LAYER 5: Número do hino na faixa bege ────────────────────────────────
    fit_text_in_parallelogram(resultado, str(numero_hino), RECT_SCALED)

    # ── LAYER 6: Nome do hino abaixo da faixa ────────────────────────────────
    draw_titulo(resultado, titulo_hino, preset)

    # ── LAYER 7: Instrumento (altura total, canto direito) ────────────────
    # Se instrumento_path foi fornecido, usa o instrumento fixo do projeto;
    # caso contrário escolhe aleatoriamente de assets/instrumentos/.
    instrumento, _ = get_instrumento(path=instrumento_path)
    if instrumento:
        resultado = composite_instrumento_direita(resultado, instrumento)

    # ── SALVAR ────────────────────────────────────────────────────────────────
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resultado.save(str(output_path), "JPEG", quality=95)
    print(f"  ✓ Salvo: {output_path.name}")
    return resultado


# ═══════════════════════════════════════════════════════════════════════════════
# CARREGAMENTO DO CSV
# ═══════════════════════════════════════════════════════════════════════════════

def carregar_hinos(csv_path: Path) -> list[tuple[int, str]]:
    """
    Carrega a lista de hinos do arquivo CSV do Hinário 5.

    O CSV usa os cabeçalhos "Número do Hino" e "Nome do Hino".
    Duplicatas de número são ignoradas (mantém o primeiro encontrado).

    Args:
        csv_path: Caminho para o arquivo CSV.

    Returns:
        Lista de tuplas (numero_int, nome_str) ordenadas pela posição no CSV.
    """
    hinos = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                num = int(row["Número do Hino"])
                titulo = row["Nome do Hino"]
                if num not in hinos:
                    hinos[num] = titulo
            except (ValueError, KeyError):
                continue
    return list(hinos.items())


# ═══════════════════════════════════════════════════════════════════════════════
# INTERFACE DE LINHA DE COMANDO
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Gerador de Thumbnails v01 — Hinário CCB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python gerar_thumb_v01.py --numero 53 328 5
  python gerar_thumb_v01.py --quantidade 20 --seed 42
  python gerar_thumb_v01.py --numero 53 --preset 2
  python gerar_thumb_v01.py --listar-presets
        """
    )
    parser.add_argument("--quantidade", "-q", type=int, default=10,
                        help="Quantidade de hinos aleatórios a gerar (padrão: 10)")
    parser.add_argument("--numero", "-n", type=int, nargs="+",
                        help="Números específicos de hinos a gerar")
    parser.add_argument("--seed", type=int, default=None,
                        help="Semente aleatória para resultados reproduzíveis")
    parser.add_argument("--preset", type=int, default=None,
                        help=f"Índice do preset de cor (0–{len(COLOR_PRESETS)-1})")
    parser.add_argument("--listar-presets", action="store_true",
                        help="Lista os presets de cor disponíveis e sai")
    args = parser.parse_args()

    if args.listar_presets:
        print("Presets disponíveis:")
        for i, p in enumerate(COLOR_PRESETS):
            print(f"  [{i}] {p['nome']}")
        return

    hinos = carregar_hinos(CSV_FILE)
    print(f"Total de hinos: {len(hinos)}")

    if args.numero:
        hinos_dict = dict(hinos)
        selecionados = [(n, hinos_dict.get(n, f"Hino {n}")) for n in args.numero]
    else:
        if args.seed is not None:
            random.seed(args.seed)
        selecionados = random.sample(hinos, min(args.quantidade, len(hinos)))

    print(f"\nGerando {len(selecionados)} thumbnails...\nSaída: {OUTPUT_DIR}/\n")

    geradas = 0
    for i, (numero, titulo) in enumerate(selecionados):
        try:
            preset_idx = args.preset if args.preset is not None else i % len(COLOR_PRESETS)
            seed = (args.seed + i) if args.seed is not None else None
            output_file = OUTPUT_DIR / f"thumb_v01_{numero:03d}.jpg"
            gerar_thumb(numero_hino=numero, titulo_hino=titulo,
                       output_path=output_file, seed=seed, preset_idx=preset_idx)
            geradas += 1
        except Exception as e:
            print(f"  ✗ Erro hino {numero}: {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"✓ {geradas}/{len(selecionados)} thumbnails geradas!")
    print(f"📁 {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
