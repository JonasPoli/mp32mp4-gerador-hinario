#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_coletaneas.py — Gerador de coletâneas de hinos para o YouTube

Este script junta múltiplos vídeos de hinos gerados pelo gerar_videos.py
em coletâneas de vídeo unificadas, criando também capas/thumbnails,
capítulos de timeline do YouTube e arquivos MD de metadados.

Uso:
  python gerar_coletaneas.py --projeto hinos_de_ninar
  python gerar_coletaneas.py --projeto hinos_de_ninar --forcar
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

try:
    from gerar_thumb import escolher_tema, desenhar_numero, desenhar_titulo, TROCA_FUNDO_PARAMS
    _HAS_THUMB_PIPELINE = True
except ImportError:
    _HAS_THUMB_PIPELINE = False

# =============================================================================
# Caminhos do projeto
# =============================================================================

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"
# COLETANEAS_DIR é definido por projeto dentro de main()

# Fontes padrão do sistema macOS
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/Library/Fonts/Georgia.ttf",
    "/System/Library/Fonts/Times.ttc",
]

# =============================================================================
# Definição das Coletâneas
# =============================================================================

COLETANEAS = {
    1: {
        "titulo": "Coletânea de Oração e Comunhão",
        "hinos": [395, 366, 274, 260, 141, 36, 96, 39, 61, 15, 80, 304],
        "descricao_intro": "Esta lista foca em hinos calmos. Eles ajudam a pessoa a orar e meditar."
    },
    2: {
        "titulo": "Coletânea de Esperança e Vida Eterna",
        "hinos": [31, 133, 454, 2, 24, 200, 431, 432, 300, 400, 50, 100],
        "descricao_intro": "Esta lista foca na promessa do céu. O tom começa suave e ganha força."
    },
    3: {
        "titulo": "Coletânea de Força nas Tribulações",
        "hinos": [412, 204, 232, 305, 193, 36, 37, 411, 424, 175, 22, 1],
        "descricao_intro": "Esta lista traz conforto em momentos difíceis. Os hinos têm melodias fortes e letras de apoio."
    },
    4: {
        "titulo": "Coletânea de Louvor e Gratidão",
        "hinos": [374, 247, 248, 313, 74, 151, 200, 364, 22, 454, 15, 80],
        "descricao_intro": "Esta categoria é alegre e serve para agradecer."
    },
    5: {
        "titulo": "Coletânea para Jovens e Mocidade",
        "hinos": [364, 74, 151, 305, 454, 232, 193, 300, 100, 400, 247, 1],
        "descricao_intro": "Esta lista traz hinos que os jovens costumam cantar com muito ânimo."
    },
    6: {
        "titulo": "Coletânea de Santificação e Entrega",
        "hinos": [141, 274, 260, 395, 36, 96, 424, 313, 411, 304, 61, 39],
        "descricao_intro": "Esta seleção foca na limpeza espiritual e no compromisso com Deus."
    },
    7: {
        "titulo": "Coletânea de Missões e Evangelização",
        "hinos": [151, 80, 313, 431, 22, 247, 15, 2, 24, 100, 50, 364],
        "descricao_intro": "Esta lista agrupa hinos de chamado e conversão."
    },
    8: {
        "titulo": "Coletânea de Confiança Absoluta",
        "hinos": [204, 232, 305, 412, 193, 175, 36, 37, 133, 31, 366, 1],
        "descricao_intro": "Esta categoria junta hinos para fortalecer a fé em momentos de dúvida."
    },
    9: {
        "titulo": "Coletânea de Consolo e Adoração",
        "hinos": [151, 133, 141, 31, 424, 22, 204, 274, 313, 366, 1, 374, 412, 193, 395],
        "descricao_intro": "Esta coletânea é baseada no vídeo, misturando mensagens de paz e oração."
    },
    10: {
        "titulo": "Coletânea de Fé, Caminhada e Combate",
        "hinos": [247, 15, 260, 411, 305, 74, 200, 36, 80, 364, 454, 300, 96, 232, 304],
        "descricao_intro": "Esta coletânea é baseada no canal Hinos CCB Cover, focando em hinos de marcha, batismo e firmeza espiritual."
    },
    11: {
        "titulo": "Coletânea de Batismo e Conversão",
        "hinos": [41, 60, 64, 66, 67, 68, 75, 85, 93, 107, 154, 155, 157, 161, 163, 167, 174, 175, 181, 183, 223, 224, 227, 308, 316, 318, 323, 331, 369, 404, 405, 406],
        "descricao_intro": "Uma seleção especial de hinos voltados ao batismo e ao chamado de conversão. Cada melodia é um convite à entrega e ao novo nascimento em Cristo."
    },
    12: {
        "titulo": "Coletânea de Jovens e Menores",
        "hinos": [431, 432, 433, 434, 435, 436, 437, 438, 439, 440, 441, 442, 443, 444, 445, 446, 447, 448, 449, 450, 451, 452, 453, 454, 455, 456, 457, 458, 459, 460, 461, 462, 463, 464, 465, 466, 467, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477, 478, 479, 480],
        "descricao_intro": "Hinos dedicados às crianças, jovens e à mocidade da CCB. Melodias alegres e cheias de fé para os pequenos e jovens servos do Senhor."
    },
    13: {
        "titulo": "Coletânea da Santa Ceia",
        "hinos": [408, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419, 420, 421, 422, 423, 424, 425],
        "descricao_intro": "Hinos especialmente selecionados para o momento sagrado da Santa Ceia. Cada melodia convida à memória do sacrifício de Cristo e à comunhão com Deus."
    },
    14: {
        "titulo": "Coletânea de Funeral e Consolação",
        "hinos": [426, 427, 428, 429, 430, 236, 330, 335, 343, 362, 377, 380, 394],
        "descricao_intro": "Uma seleção de hinos para momentos de luto e despedida. Melodias de esperança na ressurreição e no reencontro eterno, trazendo conforto a quem chora."
    },
    15: {
        "titulo": "Coletânea de Marcha e Combate Espiritual",
        "hinos": [179, 209, 233, 266, 275, 280, 281, 287, 288, 289, 290, 291, 294, 298, 329, 336, 398],
        "descricao_intro": "Hinos de ânimo e firmeza espiritual. Melodias marcantes com letras de combate, vitória e caminhada avante na fé."
    },
    16: {
        "titulo": "Coletânea de Graça, Perdão e Redenção",
        "hinos": [162, 166, 188, 229, 234, 246, 253, 254, 257, 267, 269, 278, 295, 356, 384, 386],
        "descricao_intro": "Hinos que narram a experiência pessoal da salvação. Cada melodia celebra a graça de Deus, o perdão dos pecados e a transformação operada por Cristo."
    },
    17: {
        "titulo": "Coletânea de Louvor e Adoração a Deus",
        "hinos": [147, 148, 149, 164, 170, 240, 258, 271, 272, 277, 284, 285, 306, 310, 312, 319, 325, 345, 359, 378],
        "descricao_intro": "Uma seleção de hinos de exaltação e adoração. Melodias alegres e jubilosas para glorificar a Deus em conjunto."
    },
    18: {
        "titulo": "Coletânea da Segunda Vinda e Esperança Eterna",
        "hinos": [182, 201, 213, 214, 215, 219, 220, 222, 250, 264, 301, 302, 315, 339, 340, 341, 342, 357, 379, 381, 388, 409],
        "descricao_intro": "Hinos sobre a gloriosa volta de Cristo, os novos céus, a ressurreição e a vida eterna. Uma seleção cheia de esperança e expectativa."
    },
    19: {
        "titulo": "Coletânea de Paz, Conforto e Abrigo",
        "hinos": [135, 189, 191, 192, 197, 208, 211, 245, 297, 349, 361, 375, 397, 402, 403],
        "descricao_intro": "Hinos de serenidade e consolo. Para momentos em que o coração precisa de paz e a alma busca refúgio no Senhor."
    },
    20: {
        "titulo": "Coletânea de Fidelidade e Perseverança",
        "hinos": [132, 140, 176, 190, 195, 207, 231, 259, 303, 326, 337, 346, 347, 348, 350, 353, 360],
        "descricao_intro": "Hinos de caminhada firme e fidelidade até o fim. Uma seleção para fortalecer o compromisso de nunca abandonar a fé."
    },
    21: {
        "titulo": "Coletânea de Oração e Intimidade com Deus",
        "hinos": [131, 139, 142, 169, 177, 199, 238, 282, 283, 293, 351, 355, 363, 365, 371, 376, 401],
        "descricao_intro": "Hinos de oração, entrega e comunhão íntima com Deus. Melodias suaves e profundas para momentos de meditação e dependência do Senhor."
    },
    22: {
        "titulo": "Coletânea do Amor de Deus e a Sua Palavra",
        "hinos": [136, 146, 159, 160, 168, 178, 235, 241, 242, 249, 268, 292, 358, 384, 407],
        "descricao_intro": "Hinos que exaltam o amor incondicional de Deus e a Sua Palavra como guia e sustento. Uma seleção repleta de ternura e profundidade teológica."
    },
    23: {
        "titulo": "Coletânea da Pátria Celestial e Peregrinação",
        "hinos": [158, 171, 333, 334, 335, 340, 342, 343, 344, 354, 388, 391, 392, 393, 394, 396],
        "descricao_intro": "Hinos sobre a condição de peregrino neste mundo e o anseio pela pátria celestial. Melodias que elevam o olhar para Sião e para as moradas eternas preparadas por Cristo."
    }
}

# =============================================================================
# Funções Auxiliares
# =============================================================================

def carregar_projetos() -> dict:
    """Busca dinamicamente configurações de projetos na pasta projects/."""
    projetos = {}
    projects_dir = ROOT / "projects"
    if projects_dir.exists():
        for folder in sorted(projects_dir.iterdir()):
            if folder.is_dir():
                cfg_path = folder / "config.json"
                if cfg_path.exists():
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            projetos[folder.name] = json.load(f)
                    except Exception as e:
                        print(f"[config] Erro ao carregar config.json de {folder.name}: {e}")
    
    # Fallback para o projetos.json legado
    if not projetos:
        caminho = ROOT / "projetos.json"
        if caminho.exists():
            with open(caminho, "r", encoding="utf-8") as f:
                projetos = json.load(f)
    return projetos


def carregar_csv(caminho: Path) -> dict:
    hinos = {}
    if not caminho.exists():
        print(f"[aviso] CSV não encontrado: {caminho}")
        return hinos
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


def remover_acentos(texto: str) -> str:
    import unicodedata
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def gerar_slug_coletanea(cid: int, titulo: str) -> str:
    """Gera um slug único e determinístico para identificar uma coletânea no disco.
    Ex.: (1, 'Coletânea de Oração e Comunhão') -> 'coletanea-01-coletanea-de-oracao-e-comunhao'
    """
    slug = remover_acentos(titulo).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return f"coletanea-{cid:02d}-{slug}"


def duracao_video(caminho: Path) -> float:
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


def formatar_timestamp(segundos: float) -> str:
    hours = int(segundos // 3600)
    minutes = int((segundos % 3600) // 60)
    secs = int(segundos % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

# =============================================================================
# Renderização da Capa da Coletânea com PIL
# =============================================================================

def draw_text_effects(draw, pos, text, font, fill_color, config_desenho, is_multiline=False):
    x, y = pos
    sombra = config_desenho.get("sombra")
    brilho = config_desenho.get("brilho")
    
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
                        
    elif sombra:
        dx, dy = sombra.get("deslocamento", [3, 3])
        cor_sombra = tuple(sombra.get("cor", [0, 0, 0, 128]))
        if is_multiline:
            draw.multiline_text((x + dx, y + dy), text, font=font, fill=cor_sombra)
        else:
            draw.text((x + dx, y + dy), text, font=font, fill=cor_sombra)
            
    if is_multiline:
        draw.multiline_text((x, y), text, font=font, fill=fill_color)
    else:
        draw.text((x, y), text, font=font, fill=fill_color)


def load_font_and_wrap(draw, text, max_width, max_height, start_size=55):
    for font_path in FONT_PATHS:
        try:
            for size in range(start_size, 16, -2):
                font = ImageFont.truetype(font_path, size=size)
                
                lines = []
                words = text.split()
                current_line = []
                for word in words:
                    test_line = " ".join(current_line + [word])
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    w = bbox[2] - bbox[0]
                    if w <= max_width:
                        current_line.append(word)
                    else:
                        if current_line:
                            lines.append(" ".join(current_line))
                            current_line = [word]
                        else:
                            lines.append(word)
                            current_line = []
                if current_line:
                    lines.append(" ".join(current_line))
                    
                wrapped_text = "\n".join(lines)
                bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
                h = bbox[3] - bbox[1]
                w = bbox[2] - bbox[0]
                
                if h <= max_height and w <= max_width:
                    return font, wrapped_text, h
        except OSError:
            continue
            
    return ImageFont.load_default(), text, 20


def draw_wrapped_text(draw, text, font, pos, max_width, fill_color, config_desenho):
    x_base, y = pos
    align = config_desenho.get("align", "left")
    
    lines = text.split('\n')
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        
        if align == "center":
            x = x_base + (max_width - w) // 2
        elif align == "right":
            x = x_base + max_width - w
        else:
            x = x_base
            
        draw_text_effects(draw, (x, y), line, font, fill_color, config_desenho, is_multiline=False)
        y += h + 8


def extrair_frame_de_video(video_path: Path, width=1920, height=1080) -> Image.Image:
    try:
        # Obter a duração do vídeo
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
        duration = float(probe.stdout.strip())
    except Exception:
        duration = 30.0
        
    # Extrair frame a 25% da duração do vídeo para evitar transições/telas pretas
    t = duration * 0.25
    
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-ss", str(t), "-i", str(video_path),
             "-vframes", "1", "-vf",
             f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
             "-q:v", "2", "-y", tmp_path],
            capture_output=True, timeout=30
        )
        frame = Image.open(tmp_path).convert("RGB")
        frame.load()
        return frame
    except Exception as e:
        print(f"  [aviso] Erro ao extrair frame de {video_path.name}: {e}")
        # Retorna fundo verde escuro padrão
        return Image.new("RGB", (width, height), (3, 35, 18))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def gerar_capa_coletanea(cid: int, titulo_coletanea: str, numeros: list, projeto_cfg: dict, out_path: Path, video_base_para_frame: Path = None):
    if _HAS_THUMB_PIPELINE:
        try:
            print(f"  [thumb v02] Gerando capa para Coletânea {cid}...")
            W, H = 1920, 1080
            
            # 1. Obter o frame de fundo
            if video_base_para_frame and video_base_para_frame.exists():
                frame = extrair_frame_de_video(video_base_para_frame, W, H)
            else:
                frame = Image.new("RGB", (W, H), (3, 35, 18))
                
            # 2. Obter a máscara
            mascara_path = projeto_cfg.get("mascara")
            if mascara_path:
                mascara_efetiva = ROOT / mascara_path
            else:
                mascara_efetiva = ROOT / "assets" / "mascaras" / "mascara-do-canal-hinos-de-ninar.png"
                
            # 3. Aplicar troca de fundo
            if not mascara_efetiva.exists():
                print(f"  [aviso] Máscara não encontrada em: {mascara_efetiva}")
                resultado = frame.convert("RGBA")
            else:
                from trocar_fundo_thumb import aplicar_troca_de_fundo
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_frame:
                    tmp_frame_path = tmp_frame.name
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_resultado:
                    tmp_resultado_path = tmp_resultado.name
                    
                try:
                    frame.save(tmp_frame_path, "JPEG", quality=95)
                    aplicar_troca_de_fundo(
                        template_path=str(mascara_efetiva),
                        fundo_path=tmp_frame_path,
                        saida_path=tmp_resultado_path,
                        **TROCA_FUNDO_PARAMS,
                    )
                    resultado = Image.open(tmp_resultado_path).convert("RGBA")
                finally:
                    for p in [tmp_frame_path, tmp_resultado_path]:
                        if os.path.exists(p):
                            try:
                                os.unlink(p)
                            except Exception:
                                pass
                                
            # 4. Desenhar número do selo (cid)
            tema = escolher_tema(cid)
            desenhar_numero(resultado, cid, tema)
            
            # 5. Desenhar título da coletânea
            desenhar_titulo(resultado, titulo_coletanea, tema)
            
            # 6. Salvar capa final
            out_path.parent.mkdir(parents=True, exist_ok=True)
            resultado_rgb = resultado.convert("RGB")
            resultado_rgb.save(str(out_path), "JPEG", quality=95)
            print(f"  ✓ Capa v02 gerada com sucesso: {out_path.name}")
            return
        except Exception as e:
            print(f"  [aviso] Erro no pipeline de thumbnail v02: {e}. Usando layout legado.")
            
    # --- Layout legado (fallback se o v02 falhar ou não estiver disponível) ---
    imagem_base_path = ROOT / projeto_cfg.get("imagem_base", "images/sem-numero.png")
    if not imagem_base_path.exists():
        raise FileNotFoundError(f"Imagem base do projeto não encontrada: {imagem_base_path}")
        
    img = Image.open(imagem_base_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size
    
    desenho_num = projeto_cfg.get("desenho", {}).get("numero", {})
    x = desenho_num.get("x", 120)
    y_top = desenho_num.get("y_top", 150)
    y_bottom = desenho_num.get("y_bottom", 780)
    max_width = 850
    cor = tuple(desenho_num.get("cor", [26, 45, 90, 255]))
    
    max_height = y_bottom - y_top
    
    font_title, wrapped_title, h_title = load_font_and_wrap(draw, titulo_coletanea, max_width, max_height - 250, start_size=85)
    numbers_str = ", ".join(str(n) for n in numeros)
    font_numbers, wrapped_numbers, h_numbers = load_font_and_wrap(draw, numbers_str, max_width, 200, start_size=42)
    
    margin = 35
    total_height = h_title + margin + h_numbers
    y_start = max(y_top + 15, y_top + (max_height - total_height) // 2 - 70)
    
    draw_wrapped_text(draw, wrapped_title, font_title, (x, y_start), max_width, cor, desenho_num)
    draw_wrapped_text(draw, wrapped_numbers, font_numbers, (x, y_start + h_title + margin), max_width, cor, desenho_num)
    
    img.convert("RGB").save(str(out_path))

# =============================================================================
# Loop Principal
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Gerador de coletâneas de hinos para o YouTube.")
    parser.add_argument("--projeto", required=True, help="Nome do projeto configurado em projetos.json")
    parser.add_argument("--forcar", action="store_true", help="Força a regeração de coletâneas que já existem.")
    parser.add_argument("--apenas-thumbs", action="store_true", dest="apenas_thumbs", help="Gera apenas as thumbnails (capas) das coletâneas, sem concatenar vídeos.")
    args = parser.parse_args()
    
    # Carregar configurações
    projetos = carregar_projetos()
    if args.projeto not in projetos:
        print(f"ERRO: Projeto '{args.projeto}' não encontrado no projetos.json.")
        sys.exit(1)
        
    projeto_cfg = projetos[args.projeto]
    csv_path = ROOT / projeto_cfg.get("csv_path", "")
    hinos_nomes = carregar_csv(csv_path)
    
    print(f"Iniciando gerador de coletâneas para o projeto '{args.projeto}'...")
    
    # Resolver caminhos específicos do projeto
    videos_dir = ROOT / "output" / args.projeto
    coletaneas_dir = ROOT / "output" / args.projeto / "coletaneas"
    
    # Fallback para o diretório antigo projects/ se não houver vídeos na pasta output/
    if not (videos_dir.exists() and any(videos_dir.glob("*.mp4"))):
        proj_dir = ROOT / "projects" / args.projeto
        if proj_dir.exists():
            videos_dir = proj_dir / "outputs" / "videos"
            coletaneas_dir = proj_dir / "outputs" / "coletaneas"
        
    coletaneas_dir.mkdir(parents=True, exist_ok=True)
    
    coletaneas_geradas = []
    
    for cid, col in COLETANEAS.items():
        titulo = col["titulo"]
        hinos_list = col["hinos"]
        descricao_intro = col["descricao_intro"]
        
        folder_name = f"{cid:02d} - {titulo}"
        col_dir = coletaneas_dir / folder_name
        col_dir.mkdir(parents=True, exist_ok=True)
        
        video_output = col_dir / f"{titulo} - {args.projeto}.mp4"
        slug_capa = gerar_slug_coletanea(cid, titulo)
        capa_output = col_dir / f"{slug_capa}.png"
        info_output = col_dir / "info.md"
        capitulos_output = col_dir / "capitulos.txt"

        # Renomear capa.png genérica para slug único, se existir
        capa_legada = col_dir / "capa.png"
        if capa_legada.exists() and not capa_output.exists():
            capa_legada.rename(capa_output)
            print(f"  → Capa renomeada: capa.png → {capa_output.name}")
        
        print(f"\n========================================================")
        print(f"Processando Coletânea {cid}: {titulo}")
        print(f"Hinos: {hinos_list}")
        
        # 1. Verificar se os vídeos individuais existem
        videos_locais = []
        videos_faltantes = []
        for hino in hinos_list:
            num_str = formatar_numero_completo(hino)
            v_path = videos_dir / f"hino-{args.projeto}-{num_str}.mp4"
            if not v_path.exists():
                # Tentar encontrar arquivo .mp4 que comece com o número (ex: "001- Cristo meu Mestre.mp4")
                is_coro = num_str.upper().startswith("C")
                try:
                    num_val = int(num_str[1:] if is_coro else num_str)
                except ValueError:
                    num_val = None
                
                if num_val is not None:
                    found_v = None
                    for p in videos_dir.glob("*.mp4"):
                        if p.name.startswith(".") or "-legendado" in p.name:
                            continue
                        name_lower = p.name.lower()
                        if is_coro:
                            if name_lower.startswith(f"coro {num_val:03d}") or name_lower.startswith(f"c{num_val:03d}") or name_lower.startswith(f"coro {num_val}"):
                                found_v = p
                                break
                        else:
                            if name_lower.startswith(f"{num_val:03d}") or name_lower.startswith(f"{num_val}-") or name_lower.startswith(f"{num_val} "):
                                found_v = p
                                break
                    if found_v:
                        v_path = found_v
 
            if v_path.exists():
                videos_locais.append((hino, v_path))
            else:
                videos_faltantes.append(f"Hino {hino} (esperado em {v_path.name} ou iniciando com {num_str})")
                
        if videos_faltantes and not args.apenas_thumbs:
            print(f"AVISO: Pulando coletânea '{titulo}' devido aos seguintes vídeos faltantes:")
            for m in videos_faltantes:
                print(f"  - {m}")
            continue
            
        # 2. Gerar a capa (Thumbnail) da Coletânea se não existir ou se --forcar
        if not capa_output.exists() or args.forcar:
            print(f"Gerando capa '{capa_output.name}'...")
            video_base_para_frame = videos_locais[0][1] if videos_locais else None
            gerar_capa_coletanea(cid, titulo, hinos_list, projeto_cfg, capa_output, video_base_para_frame)
            print(f"  ✓ Capa salva em {capa_output.relative_to(ROOT)}")
        else:
            print(f"Capa já existe ({capa_output.name}), pulando...")
        
        # Se --apenas-thumbs, pular concatenação de vídeos e metadados
        if args.apenas_thumbs:
            continue
            
        # 3. Concatenar vídeos e calcular os capítulos
        timeline = []
        current_time = 0.0
        
        # Criar arquivo de lista para o concat do ffmpeg
        lista_txt = col_dir / "lista.txt"
        with open(lista_txt, "w", encoding="utf-8") as f:
            for hino, v_path in videos_locais:
                num_key = hino
                hino_str = str(hino).strip()
                if hino_str.upper().startswith("C") and hino_str[1:].isdigit():
                    try:
                        num_key = int(hino_str[1:])
                    except ValueError:
                        pass
                raw_nome = hinos_nomes.get(hino) or hinos_nomes.get(num_key) or f"Hino {hino}"
                nome_hino = limpar_nome_hino(raw_nome)
                timestamp_str = formatar_timestamp(current_time)
                hino_str = str(hino).strip()
                if hino_str.upper().startswith("C") and hino_str[1:].isdigit():
                    timeline.append(f"{timestamp_str} - Coro {int(hino_str[1:])} - {nome_hino}")
                else:
                    timeline.append(f"{timestamp_str} - Hino {hino} - {nome_hino}")
                
                # Escrever no arquivo list para o concat
                f.write(f"file '{v_path.resolve()}'\n")
                
                # Obter duração
                dur = duracao_video(v_path)
                current_time += dur
                
        # Gerar os capítulos no formato YouTube
        capitulos_texto = "\n".join(timeline)
        with open(capitulos_output, "w", encoding="utf-8") as f:
            f.write(capitulos_texto + "\n")
        print(f"  ✓ Capítulos salvos em {capitulos_output.relative_to(ROOT)}")
        
        # 4. Concatenar vídeos via ffmpeg se não existir ou se --forcar
        if not video_output.exists() or args.forcar:
            print("Concatenando vídeos com FFmpeg (sem re-codificação, lossless)...")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(lista_txt.resolve()),
                "-c", "copy",
                str(video_output.resolve())
            ]
            # Rodar subprocesso ocultando a saída verbosa
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  ✗ ERRO na concatenação: {result.stderr}")
            else:
                print(f"  ✓ Vídeo concatenado salvo em {video_output.relative_to(ROOT)}")
        else:
            print("Vídeo concatenado já existe, pulando...")
            
        # Remover lista.txt temporário
        if lista_txt.exists():
            lista_txt.unlink()
            
        # 5. Gerar arquivo MD de metadados para o YouTube (title, description, tags)
        print("Gerando metadados do YouTube...")
        nome_exibicao = projeto_cfg.get("nome_exibicao", args.projeto)
        yt_title = f"{nome_exibicao} | {titulo} | Hinos CCB"
        
        # Formatar a lista estruturada de hinos (bullet points) para a descrição
        lista_hinos_desc = []
        for hino in hinos_list:
            num_key = hino
            hino_str = str(hino).strip()
            if hino_str.upper().startswith("C") and hino_str[1:].isdigit():
                try:
                    num_key = int(hino_str[1:])
                except ValueError:
                    pass
            raw_nome = hinos_nomes.get(hino) or hinos_nomes.get(num_key) or f"Hino {hino}"
            nome_hino = limpar_nome_hino(raw_nome)
            if hino_str.upper().startswith("C") and hino_str[1:].isdigit():
                lista_hinos_desc.append(f"• Coro {int(hino_str[1:])} - {nome_hino}")
            else:
                lista_hinos_desc.append(f"• Hino {hino} - {nome_hino}")
        lista_hinos_formatada = "\n".join(lista_hinos_desc)
        
        yt_description = (
            f"{nome_exibicao} — {titulo}\n"
            f"{descricao_intro}\n\n"
            f"🎹 Projeto: {nome_exibicao}\n"
            f"📖 Hinário: Hinário 5\n\n"
            f"Hinos contidos nesta coletânea:\n"
            f"{lista_hinos_formatada}\n\n"
            f"Capítulos (Timeline):\n"
            f"{capitulos_texto}\n\n"
            f"Que esta melodia instrumental possa trazer paz, comunhão e edificação ao seu coração.\n\n"
            f"Inscreva-se no canal para acompanhar mais hinos instrumentais da CCB no teclado."
        )
        
        # Tags de no máximo 400 caracteres
        tag_titulo_slug = remover_acentos(titulo).lower()
        base_tags = [
            f"coletanea {tag_titulo_slug}",
            f"coletânea {titulo.lower()}",
            "hinos ccb",
            "hinos da ccb",
            "ccb hinos",
            "ccb instrumental",
            "hinos instrumentais ccb",
            "música instrumental cristã",
            "musica instrumental crista",
            "louvor instrumental",
            "hinos para meditação",
            "hinos para adoração",
            "congregação cristã no brasil",
            "congregacao crista no brasil",
            "instrumental ccb",
            nome_exibicao.lower(),
            f"hinos {nome_exibicao.lower()}"
        ]
        
        valid_tags = []
        current_len = 0
        for tag in base_tags:
            tag = tag.strip()
            if not tag:
                continue
            added = len(tag) + (2 if valid_tags else 0)
            if current_len + added <= 400:
                valid_tags.append(tag)
                current_len += added
            else:
                break
        yt_tags = ", ".join(valid_tags)
        
        # Criar o arquivo info.md
        md_content = (
            f"# Metadados para o YouTube\n\n"
            f"## Título\n"
            f"```text\n"
            f"{yt_title}\n"
            f"```\n\n"
            f"## Descrição\n"
            f"```text\n"
            f"{yt_description}\n"
            f"```\n\n"
            f"## Tags ({len(yt_tags)} caracteres, máximo 400)\n"
            f"```text\n"
            f"{yt_tags}\n"
            f"```\n"
        )
        
        with open(info_output, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"  ✓ Metadados salvos em {info_output.relative_to(ROOT)}")

        # Guardar metadados para exportação do CSV no final
        coletaneas_geradas.append({
            "id": cid,
            "video_file": video_output.name,
            "titulo": yt_title,
            "descricao": yt_description,
            "capa_file": capa_output.name,
            "nome_projeto": nome_exibicao,
            "tags": yt_tags
        })

    # 6. Exportar o CSV de todas as coletâneas se houverem
    if coletaneas_geradas:
        csv_output_path = coletaneas_dir / "youtube_upload_coletaneas.csv"
        print(f"\nExportando CSV geral das coletâneas para: {csv_output_path.relative_to(ROOT)}")
        with open(csv_output_path, "w", newline="", encoding="utf-8-sig") as csv_f:
            writer = csv.writer(csv_f)
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
            for col in coletaneas_geradas:
                v_file = col["video_file"]
                stem = Path(v_file).stem
                video_file_clean = stem.replace("-", " ").replace("_", " ")
                video_file_clean = " ".join(video_file_clean.split())  # normalize spaces
                
                # Tags de no máximo 400 caracteres
                tags = col["tags"]
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
                    col["id"],
                    v_file,
                    video_file_clean,
                    col["titulo"],
                    col["descricao"],
                    col["capa_file"],
                    col["nome_projeto"],
                    tags,
                    "",  # data
                    ""   # hora
                ])
        print("  ✓ CSV exportado com sucesso!")

    print("\n✓ Processamento de todas as coletâneas finalizado!")

if __name__ == "__main__":
    main()
