#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_thumb_v02.py — Gerador de Thumbnails (Pipeline v02)
Canal: Hinos de Ninar — Hinário 5 CCB

═══════════════════════════════════════════════════════════════════════
PILHA DE COMPOSIÇÃO (1920 × 1080 px, 16:9)
═══════════════════════════════════════════════════════════════════════
  Layer 1 ─ Frame de vídeo (fundo)
            Um frame aleatório extraído de um clipe MP4 (videos_flores/
            ou Photos-1-001/), redimensionado para 1920×1080 via ffmpeg.

  Layer 2 ─ Troca de fundo inteligente
            Mistura o frame com a máscara do canal usando a lógica de
            trocar_fundo_thumb.py: aplica cor escura verde para cobrir
            o fundo antigo, depois sobrepõe o frame novo com opacidade
            controlada — protegendo as regiões da caixa de música,
            logo e etiquetas da máscara.

  Layer 3 ─ Máscara do canal (identidade visual)
            assets/mascaras/mascara-do-canal-hinos-de-ninar.png
            Composta por alpha composite sobre o resultado. Traz:
              - Moldura dourada
              - Caixa de música (lado direito)
              - Logo "Hinos de Ninar" (topo direito)
              - Faixa "HINÁRIO 5" (centro inferior esquerdo)
              - Barra inferior "HINOS DE NINAR • CCB"
              - Etiqueta "CAIXA DE MÚSICA"

  Layer 4 ─ Número do hino
            Renderizado em canvas RGBA com efeito do gerar_textos_thumbs:
            selo arredondado com contorno dourado, número em verde escuro,
            inclinado -10°, posicionado no topo esquerdo da máscara.

  Layer 5 ─ Nome do hino
            Texto multi-linha em caixa alta com fonte adaptativa,
            efeitos de gradiente + sombra + brilho dourado (sistema do
            gerar_textos_thumbs), inclinado -2.2°, posicionado na área
            central esquerda (acima da faixa "HINÁRIO 5").

═══════════════════════════════════════════════════════════════════════
USO
═══════════════════════════════════════════════════════════════════════
  # Gera thumb de um hino específico:
  python gerar_thumb_v02.py --numero 53 --titulo "Nós somos luz do mundo"

  # Gera thumb usando um frame de vídeo específico:
  python gerar_thumb_v02.py --numero 53 --titulo "Nós somos luz do mundo" --frame caminho/frame.jpg

  # Gera 10 thumbs aleatórias (para teste):
  python gerar_thumb_v02.py --quantidade 10

  # Com seed para resultado determinístico:
  python gerar_thumb_v02.py --numero 53 --seed 42

═══════════════════════════════════════════════════════════════════════
DEPENDÊNCIAS
═══════════════════════════════════════════════════════════════════════
  pip install Pillow
  brew install ffmpeg   (para extração de frames de vídeo)
"""

import os
import csv
import random
import subprocess
import tempfile
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps

# Importa a função de troca de fundo do módulo existente
from trocar_fundo_thumb import aplicar_troca_de_fundo

# ─── CAMINHOS ─────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
VIDEOS_DIR_1   = BASE_DIR / "videos_flores"
VIDEOS_DIR_2   = BASE_DIR / "Photos-1-001"
FONTES_DIR     = BASE_DIR / "fontes"
OUTPUT_DIR     = BASE_DIR / "thumbs" / "v01"   # mesmo local que v01 (substitui no mesmo lugar)
CSV_FILE       = FONTES_DIR / "hinario5.csv"
FONT_PATH      = FONTES_DIR / "Montserrat.ttf"

# Máscara específica do canal Hinos de Ninar
MASCARA_PATH   = BASE_DIR / "assets" / "mascaras" / "mascara-do-canal-hinos-de-ninar.png"

# ─── FONTES para renderização de texto (mesmas do gerar_textos_thumbs.py) ────
# IMPORTANTE: usar sempre Arial Bold / Arial Black para traço grosso e legível.
# Montserrat sem peso explícito carrega como Regular (fina) — evitar para texto.
FONTES_POSSIVEIS = [
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Bold.ttf",

    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",

    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arialbi.ttf",
]


def carregar_fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    for caminho in FONTES_POSSIVEIS:
        if os.path.exists(caminho):
            return ImageFont.truetype(caminho, tamanho)
    raise FileNotFoundError(
        "Nenhuma fonte encontrada. Verifique a lista FONTES_POSSIVEIS no script."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — FRAME DE VÍDEO
# ═══════════════════════════════════════════════════════════════════════════════

def get_video_frame(
    video_dirs: list,
    width: int = 1920,
    height: int = 1080,
    frame_path: str | None = None,
) -> Image.Image | None:
    """
    Obtém um frame de vídeo para usar como fundo.

    Se frame_path for fornecido, carrega diretamente o arquivo de imagem.
    Caso contrário, extrai um frame aleatório de um clipe de vídeo via ffmpeg.

    Args:
        video_dirs:  Lista de Path para pastas com clipes de vídeo.
        width:       Largura do frame final.
        height:      Altura do frame final.
        frame_path:  Caminho direto para uma imagem a usar como frame (opcional).

    Returns:
        Imagem PIL RGB ou None se não encontrar vídeos.
    """
    # Modo direto: usa uma imagem já extraída
    if frame_path and os.path.exists(frame_path):
        print(f"  Frame: {Path(frame_path).name} (direto)")
        img = Image.open(frame_path).convert("RGB")
        return ImageOps.fit(img, (width, height), method=Image.Resampling.LANCZOS)

    # Modo automático: extrai frame aleatório de clipe de vídeo
    all_videos = []
    for vdir in video_dirs:
        vdir = Path(vdir)
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

    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video],
            capture_output=True, text=True, timeout=10
        )
        duration = float(probe.stdout.strip())
    except Exception:
        duration = 30.0

    margin = max(2.0, duration * 0.05)
    t = random.uniform(margin, duration - margin)

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
        print(f"  Erro ao extrair frame: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYERS 2+3 — TROCA DE FUNDO + MÁSCARA DO CANAL
#
# Usa diretamente aplicar_troca_de_fundo() de trocar_fundo_thumb.py.
#
# Parâmetros calibrados pelo usuário para a máscara hinos-de-ninar:
#   --opacidade 0.5   → frame aparece com 50% de opacidade
#   --blur 0          → sem desfoque no frame (mantém nitidez)
#   --escurecer 0.95  → frame quase sem escurecimento
#   --verde 0.35      → filtro verde suave para identidade do canal
#   --apagar 0.95     → camada escura forte para cobrir fundo original
#   --escala 1        → frame ocupa 100% da área
#   --x 0 --y 0       → frame alinhado ao topo-esquerda
# ═══════════════════════════════════════════════════════════════════════════════

# Parâmetros de troca de fundo (equivalentes ao comando do usuário)
TROCA_FUNDO_PARAMS = dict(
    opacidade=0.5,
    blur=0,
    escurecer=0.95,
    saturacao=0.85,
    verde=0.35,
    apagar_fundo_antigo=0.95,
    escala=1.0,
    posicao_x=0.0,
    posicao_y=0.0,
    proteger_direita=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE TEXTO (baseado em gerar_textos_thumbs.py)
# ═══════════════════════════════════════════════════════════════════════════════

def texto_bbox(draw: ImageDraw.Draw, texto: str, fonte: ImageFont.FreeTypeFont, stroke_width: int = 0) -> tuple:
    """Retorna (largura, altura) do texto."""
    box = draw.textbbox((0, 0), texto, font=fonte, stroke_width=stroke_width)
    return box[2] - box[0], box[3] - box[1]


def limpar_titulo(texto: str) -> str:
    """Normaliza o texto do título para exibição."""
    texto = str(texto).strip().upper()
    texto = texto.replace("...", "").replace("…", "")
    texto = " ".join(texto.split())
    return texto


def gerar_quebras_em_ate_3_linhas(palavras: list) -> list:
    """Gera todas as possíveis quebras de linha para o título (1, 2 ou 3 linhas)."""
    n = len(palavras)
    if n == 0:
        return [[""]]
    if n == 1:
        return [[palavras[0]]]

    possibilidades = [[" ".join(palavras)]]

    for i in range(1, n):
        possibilidades.append([" ".join(palavras[:i]), " ".join(palavras[i:])])

    for i in range(1, n):
        for j in range(i + 1, n):
            possibilidades.append([
                " ".join(palavras[:i]),
                " ".join(palavras[i:j]),
                " ".join(palavras[j:])
            ])

    return possibilidades


def escolher_melhor_quebra(
    draw: ImageDraw.Draw,
    texto: str,
    fonte: ImageFont.FreeTypeFont,
    largura_maxima: int,
    max_linhas: int = 3,
    stroke_width: int = 8,
) -> list | None:
    """Escolhe a melhor quebra de linha para o título sem cortar palavras."""
    texto = limpar_titulo(texto)
    palavras = texto.split()
    possibilidades = gerar_quebras_em_ate_3_linhas(palavras)

    melhores = []
    for linhas in possibilidades:
        if len(linhas) > max_linhas:
            continue

        larguras = [texto_bbox(draw, l, fonte, stroke_width)[0] for l in linhas]
        if max(larguras) <= largura_maxima:
            maior = max(larguras)
            menor = min(larguras)
            media = sum(larguras) / len(larguras)
            desequilibrio = maior - menor
            aproveitamento = abs(largura_maxima * 0.82 - media)
            bonus_tres = -80 if len(palavras) >= 4 and len(linhas) == 3 else 0
            score = desequilibrio + aproveitamento + bonus_tres
            melhores.append((score, linhas))

    if melhores:
        melhores.sort(key=lambda x: x[0])
        return melhores[0][1]
    return None


def escolher_fonte_que_cabe(
    draw: ImageDraw.Draw,
    texto: str,
    largura_maxima: int,
    altura_maxima: int,
    tamanho_min: int = 28,
    tamanho_max: int = 145,
    max_linhas: int = 3,
    entrelinhas: float = 0.84,
    stroke_ratio: float = 0.07,
) -> tuple:
    """Diminui a fonte até o título caber na área disponível."""
    texto = limpar_titulo(texto)

    for tamanho in range(tamanho_max, tamanho_min - 1, -2):
        fonte = carregar_fonte(tamanho)
        stroke_width = max(5, int(tamanho * stroke_ratio))

        linhas = escolher_melhor_quebra(draw, texto, fonte, largura_maxima, max_linhas, stroke_width)
        if not linhas:
            continue

        altura_linha = int(tamanho * entrelinhas)
        altura_total = altura_linha * len(linhas)

        larguras = [texto_bbox(draw, l, fonte, stroke_width)[0] for l in linhas]
        if altura_total <= altura_maxima and max(larguras) <= largura_maxima:
            return fonte, linhas, tamanho, altura_linha, stroke_width

    raise ValueError(f"Não foi possível encaixar o título: {texto}")


def criar_gradiente_vertical(
    largura: int,
    altura: int,
    cor_topo: tuple,
    cor_base: tuple,
) -> Image.Image:
    """Cria um gradiente vertical RGBA entre duas cores."""
    grad = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    px = grad.load()
    for y in range(altura):
        t = y / max(1, altura - 1)
        r = int(cor_topo[0] * (1 - t) + cor_base[0] * t)
        g = int(cor_topo[1] * (1 - t) + cor_base[1] * t)
        b = int(cor_topo[2] * (1 - t) + cor_base[2] * t)
        for x in range(largura):
            px[x, y] = (r, g, b, 255)
    return grad


def criar_texto_com_efeito(
    texto: str,
    fonte: ImageFont.FreeTypeFont,
    cor_topo: tuple,
    cor_base: tuple,
    stroke: tuple,
    stroke_width: int = 8,
) -> Image.Image:
    """
    Cria camada de texto com efeitos: sombra, contorno, brilho dourado,
    gradiente e luz branca sutil.
    """
    temp = Image.new("RGBA", (2200, 500), (0, 0, 0, 0))
    dtemp = ImageDraw.Draw(temp)

    w, h = texto_bbox(dtemp, texto, fonte, stroke_width=stroke_width)
    largura = w + 120
    altura = h + 110
    x, y = 55, 40

    final = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))

    # Sombra externa
    sombra = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sombra)
    ds.text((x + 10, y + 13), texto, font=fonte, fill=(0, 0, 0, 210),
            stroke_width=stroke_width, stroke_fill=(0, 0, 0, 210))
    sombra = sombra.filter(ImageFilter.GaussianBlur(7))
    final.alpha_composite(sombra)

    # Brilho dourado externo
    glow = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    dg.text((x, y), texto, font=fonte, fill=(255, 225, 120, 100),
            stroke_width=stroke_width + 4, stroke_fill=(255, 205, 70, 100))
    glow = glow.filter(ImageFilter.GaussianBlur(3))
    final.alpha_composite(glow)

    # Contorno
    contorno = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    dc = ImageDraw.Draw(contorno)
    dc.text((x, y), texto, font=fonte, fill=(255, 255, 255, 255),
            stroke_width=stroke_width, stroke_fill=stroke)
    final.alpha_composite(contorno)

    # Gradiente dentro das letras
    mask = Image.new("L", (largura, altura), 0)
    dm = ImageDraw.Draw(mask)
    dm.text((x, y), texto, font=fonte, fill=255)
    grad = criar_gradiente_vertical(largura, altura, cor_topo, cor_base)
    grad.putalpha(mask)
    final.alpha_composite(grad)

    # Luz branca sutil no topo
    brilho = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    db = ImageDraw.Draw(brilho)
    db.text((x - 2, y - 3), texto, font=fonte, fill=(255, 255, 255, 75),
            stroke_width=1, stroke_fill=(255, 255, 255, 50))
    final.alpha_composite(brilho)

    return final


def escolher_tema(numero: int) -> dict:
    """
    Alterna temas de cores para as thumbs.
    Usa o mesmo sistema de gerar_textos_thumbs.py.
    """
    temas = [
        {
            "stroke": (3, 47, 26, 255),
            "linha_clara_topo": (255, 255, 245),
            "linha_clara_base": (235, 219, 166),
            "linha_destaque_topo": (255, 224, 94),
            "linha_destaque_base": (220, 150, 22),
            "selo_fill": (255, 235, 170, 255),
            "selo_borda": (126, 91, 26, 255),
            "numero_fill": (5, 60, 34, 255),
            "numero_stroke": (255, 244, 190, 255),
        },
        {
            "stroke": (2, 42, 28, 255),
            "linha_clara_topo": (255, 255, 255),
            "linha_clara_base": (228, 238, 220),
            "linha_destaque_topo": (255, 182, 228),
            "linha_destaque_base": (220, 84, 178),
            "selo_fill": (255, 232, 175, 255),
            "selo_borda": (210, 160, 45, 255),
            "numero_fill": (7, 61, 38, 255),
            "numero_stroke": (255, 245, 195, 255),
        },
        {
            "stroke": (3, 41, 24, 255),
            "linha_clara_topo": (255, 255, 255),
            "linha_clara_base": (236, 228, 184),
            "linha_destaque_topo": (120, 245, 232),
            "linha_destaque_base": (20, 184, 205),
            "selo_fill": (255, 237, 185, 255),
            "selo_borda": (211, 171, 62, 255),
            "numero_fill": (8, 62, 40, 255),
            "numero_stroke": (255, 244, 195, 255),
        },
        {
            "stroke": (36, 26, 8, 255),
            "linha_clara_topo": (255, 250, 225),
            "linha_clara_base": (239, 208, 128),
            "linha_destaque_topo": (255, 255, 255),
            "linha_destaque_base": (236, 230, 204),
            "selo_fill": (246, 222, 145, 255),
            "selo_borda": (92, 64, 20, 255),
            "numero_fill": (5, 55, 31, 255),
            "numero_stroke": (255, 244, 198, 255),
        },
    ]
    try:
        n = int(str(numero).strip())
    except Exception:
        n = 0
    return temas[n % len(temas)]


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — NÚMERO DO HINO
# ═══════════════════════════════════════════════════════════════════════════════

def desenhar_numero(base: Image.Image, numero: int | str, tema: dict) -> None:
    """
    Desenha o número do hino como um selo arredondado inclinado no topo esquerdo.

    Posicionado para não sobrepor a faixa "HINÁRIO 5" da máscara.
    Inclinado -10° (igual ao sistema gerar_textos_thumbs).

    Args:
        base:   Imagem PIL RGBA de destino (modificada in-place via alpha_composite).
        numero: Número do hino.
        tema:   Dicionário de tema com cores.
    """
    W, H = base.size

    # Canvas do selo
    camada = Image.new("RGBA", (330, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    # Sombra do selo
    sombra = Image.new("RGBA", camada.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(sombra)
    ds.rounded_rectangle((15, 18, 320, 140), radius=22, fill=(0, 0, 0, 130))
    sombra = sombra.filter(ImageFilter.GaussianBlur(7))
    camada.alpha_composite(sombra)

    # Fundo do selo
    d.rounded_rectangle(
        (10, 10, 320, 138), radius=22,
        fill=tema["selo_fill"], outline=tema["selo_borda"], width=5
    )
    # Borda interna decorativa
    d.rounded_rectangle(
        (22, 22, 308, 126), radius=16,
        outline=(255, 255, 230, 130), width=2
    )

    # Texto do número (ajusta tamanho conforme dígitos)
    numero_txt = str(numero).strip()
    tamanho_num = 108
    if len(numero_txt) == 2:
        tamanho_num = 102
    elif len(numero_txt) == 3:
        tamanho_num = 90
    elif len(numero_txt) >= 4:
        tamanho_num = 76

    fonte_num = carregar_fonte(tamanho_num)
    d.text(
        (165, 74), numero_txt, font=fonte_num,
        fill=tema["numero_fill"], anchor="mm",
        stroke_width=4, stroke_fill=tema["numero_stroke"]
    )

    # Inclinação do selo
    camada = camada.rotate(-10, expand=True, resample=Image.Resampling.BICUBIC)

    # Cola o selo no topo esquerdo
    base.alpha_composite(camada, (-5, 12))


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 5 — NOME DO HINO
# ═══════════════════════════════════════════════════════════════════════════════

def desenhar_titulo(base: Image.Image, titulo: str, tema: dict) -> None:
    """
    Desenha o nome do hino na área central-esquerda da imagem.

    Área de texto calibrada para a máscara mascara-do-canal-hinos-de-ninar.png:
      - Começa abaixo do selo do número (y ≈ 14.5% da altura)
      - Vai até acima da faixa "HINÁRIO 5" (y ≈ 70% da altura)
      - Largura: da borda esquerda até ≈ 57% da largura (antes da caixa de música)

    Args:
        base:   Imagem PIL RGBA de destino (modificada in-place via alpha_composite).
        titulo: Nome do hino (será convertido para caixa alta).
        tema:   Dicionário de tema com cores.
    """
    W, H = base.size
    d = ImageDraw.Draw(base)

    # Área de texto calibrada para a máscara hinos-de-ninar
    # (não sobrepõe "HINÁRIO 5" em baixo nem a caixa de música na direita)
    x1 = int(W * 0.055)
    y1 = int(H * 0.145)
    x2 = int(W * 0.565)
    y2 = int(H * 0.710)

    largura_max = x2 - x1
    altura_max = y2 - y1

    fonte, linhas, tamanho, altura_linha, stroke_width = escolher_fonte_que_cabe(
        draw=d,
        texto=titulo,
        largura_maxima=largura_max,
        altura_maxima=altura_max,
        tamanho_min=28,
        tamanho_max=145,
        max_linhas=3,
        entrelinhas=0.84,
    )

    altura_total = altura_linha * len(linhas)

    # Centraliza verticalmente na área
    y = y1 + int((altura_max - altura_total) * 0.50)

    for idx, linha in enumerate(linhas):
        # Segunda linha recebe cor de destaque
        if idx == 1 and len(linhas) >= 2:
            cor_topo = tema["linha_destaque_topo"]
            cor_base = tema["linha_destaque_base"]
        else:
            cor_topo = tema["linha_clara_topo"]
            cor_base = tema["linha_clara_base"]

        texto_layer = criar_texto_com_efeito(
            texto=linha,
            fonte=fonte,
            cor_topo=cor_topo,
            cor_base=cor_base,
            stroke=tema["stroke"],
            stroke_width=stroke_width,
        )

        # Inclinação estilo thumbnail
        texto_layer = texto_layer.rotate(-2.2, expand=True, resample=Image.Resampling.BICUBIC)

        # Cola na posição da linha
        base.alpha_composite(texto_layer, (x1 - 42, y - 42))

        y += altura_linha


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def gerar_thumb(
    numero_hino: int,
    titulo_hino: str,
    output_path: str | Path,
    seed: int | None = None,
    frame_path: str | None = None,
    instrumento_path: str | None = None,  # ignorado no v02 (sem instrumento separado)
) -> Image.Image:
    """
    Executa o pipeline completo de geração de thumbnail v02 para um hino.

    Pipeline:
      1. Obtém frame de vídeo (aleatório ou fornecido diretamente).
      2. Mistura o frame com a máscara do canal (troca de fundo inteligente).
      3. Compõe a máscara do canal sobre o resultado.
      4. Desenha o número do hino.
      5. Desenha o nome do hino.
      6. Salva o resultado como JPEG qualidade 95.

    Args:
        numero_hino:  Número do hino (inteiro).
        titulo_hino:  Nome completo do hino.
        output_path:  Caminho do arquivo de saída (JPEG).
        seed:         Semente aleatória para resultados determinísticos.
        frame_path:   Caminho direto para uma imagem a usar como frame (opcional).

    Returns:
        Objeto Image PIL com a thumbnail final.
    """
    if seed is not None:
        random.seed(seed)

    W, H = 1920, 1080

    print(f"\n[Hino {numero_hino}] {titulo_hino}")

    # ── LAYER 1: Frame de vídeo ───────────────────────────────────────────────
    frame = get_video_frame([VIDEOS_DIR_1, VIDEOS_DIR_2], W, H, frame_path=frame_path)
    if frame is None:
        print("  AVISO: Nenhum vídeo encontrado. Usando fundo verde escuro.")
        frame = Image.new("RGB", (W, H), (3, 35, 18))

    # ── LAYERS 2+3: Troca de fundo via trocar_fundo_thumb.aplicar_troca_de_fundo ──
    # Usa arquivos temporários pois aplicar_troca_de_fundo trabalha com paths.
    if not MASCARA_PATH.exists():
        print(f"  AVISO: Máscara não encontrada: {MASCARA_PATH}")
        resultado = frame.convert("RGBA")
    else:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_frame:
            tmp_frame_path = tmp_frame.name
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_resultado:
            tmp_resultado_path = tmp_resultado.name

        try:
            # Salva o frame em arquivo temporário
            frame.save(tmp_frame_path, "JPEG", quality=95)

            # Chama trocar_fundo_thumb com os parâmetros calibrados
            aplicar_troca_de_fundo(
                template_path=str(MASCARA_PATH),
                fundo_path=tmp_frame_path,
                saida_path=tmp_resultado_path,
                **TROCA_FUNDO_PARAMS,
            )

            resultado = Image.open(tmp_resultado_path).convert("RGBA")
        finally:
            for p in [tmp_frame_path, tmp_resultado_path]:
                try:
                    os.unlink(p)
                except Exception:
                    pass

    # ── LAYER 4: Número do hino ───────────────────────────────────────────────
    tema = escolher_tema(numero_hino)
    desenhar_numero(resultado, numero_hino, tema)

    # ── LAYER 5: Nome do hino ─────────────────────────────────────────────────
    desenhar_titulo(resultado, titulo_hino, tema)

    # ── SALVAR ────────────────────────────────────────────────────────────────
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resultado_rgb = resultado.convert("RGB")
    resultado_rgb.save(str(output_path), "JPEG", quality=95)
    print(f"  ✓ Salvo: {output_path.name}")

    return resultado_rgb


# ═══════════════════════════════════════════════════════════════════════════════
# CARREGAMENTO DO CSV
# ═══════════════════════════════════════════════════════════════════════════════

def carregar_hinos(csv_path: Path) -> list:
    """
    Carrega a lista de hinos do CSV do Hinário 5.

    Returns:
        Lista de tuplas (numero_int, nome_str).
    """
    hinos = {}
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Detecta automaticamente as colunas de número e nome
            num_key = next(
                (k for k in row if "número" in k.lower() or "numero" in k.lower()), None
            )
            nome_key = next(
                (k for k in row if "nome" in k.lower() or "título" in k.lower() or "titulo" in k.lower()), None
            )
            if not num_key or not nome_key:
                continue
            try:
                num = int(row[num_key].strip())
                nome = row[nome_key].strip()
                if num not in hinos:
                    hinos[num] = nome
            except (ValueError, KeyError):
                continue
    return list(hinos.items())


# ═══════════════════════════════════════════════════════════════════════════════
# INTERFACE DE LINHA DE COMANDO
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Gerador de Thumbnails v02 — Canal Hinos de Ninar (CCB)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Hino específico:
  python gerar_thumb_v02.py --numero 53 --titulo "Nós somos luz do mundo"

  # Hino específico com frame de vídeo fornecido:
  python gerar_thumb_v02.py --numero 53 --titulo "Hino" --frame assets/mascaras/borboleta.png

  # Múltiplos hinos específicos (busca nome no CSV):
  python gerar_thumb_v02.py --numero 53 328 5

  # 10 hinos aleatórios:
  python gerar_thumb_v02.py --quantidade 10

  # Com seed determinístico:
  python gerar_thumb_v02.py --numero 53 --seed 42
        """
    )
    parser.add_argument(
        "--numero", "-n", type=int, nargs="+",
        help="Número(s) do(s) hino(s) a gerar"
    )
    parser.add_argument(
        "--titulo", "-t", type=str, default=None,
        help="Nome do hino (usado apenas quando --numero tem exatamente 1 valor)"
    )
    parser.add_argument(
        "--quantidade", "-q", type=int, default=10,
        help="Quantidade de hinos aleatórios (usado quando --numero não é fornecido)"
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Semente aleatória para resultados reproduzíveis"
    )
    parser.add_argument(
        "--frame", type=str, default=None,
        help="Caminho direto para uma imagem a usar como frame de fundo"
    )
    parser.add_argument(
        "--saida", type=str, default=None,
        help="Pasta de saída (padrão: thumbs/v02/)"
    )
    args = parser.parse_args()

    output_dir = Path(args.saida) if args.saida else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determina os hinos a gerar
    hinos = carregar_hinos(CSV_FILE)
    hinos_dict = dict(hinos)

    if args.numero:
        if len(args.numero) == 1 and args.titulo:
            selecionados = [(args.numero[0], args.titulo)]
        else:
            selecionados = [(n, hinos_dict.get(n, f"Hino {n}")) for n in args.numero]
    else:
        if args.seed is not None:
            random.seed(args.seed)
        selecionados = random.sample(hinos, min(args.quantidade, len(hinos)))

    print(f"\nPipeline v02 — Canal Hinos de Ninar")
    print(f"Máscara: {MASCARA_PATH.name}")
    print(f"Gerando {len(selecionados)} thumbnail(s)...")
    print(f"Saída: {output_dir}/\n")

    geradas = 0
    for i, (numero, titulo) in enumerate(selecionados):
        try:
            seed = (args.seed + i) if args.seed is not None else None
            output_file = output_dir / f"thumb_v01_{int(numero):03d}.jpg"  # mesmo nome do v01
            gerar_thumb(
                numero_hino=numero,
                titulo_hino=titulo,
                output_path=output_file,
                seed=seed,
                frame_path=args.frame,
            )
            geradas += 1
        except Exception as e:
            print(f"  ✗ Erro hino {numero}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 50}")
    print(f"✓ {geradas}/{len(selecionados)} thumbnails geradas!")
    print(f"📁 {output_dir}")


if __name__ == "__main__":
    main()
