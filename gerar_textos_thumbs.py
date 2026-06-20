from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import argparse
import csv


# ============================================================
# CONFIGURAÇÕES DE FONTE
# ============================================================

FONTES_POSSIVEIS = [
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Bold.ttf",

    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",

    # Windows, se usar depois
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arialbi.ttf",
]


def carregar_fonte(tamanho):
    for caminho in FONTES_POSSIVEIS:
        if os.path.exists(caminho):
            return ImageFont.truetype(caminho, tamanho)

    raise FileNotFoundError(
        "Nenhuma fonte encontrada. Ajuste a lista FONTES_POSSIVEIS no início do script."
    )


# ============================================================
# FUNÇÕES DE TEXTO
# ============================================================

def limpar_titulo(texto):
    texto = str(texto).strip().upper()
    texto = texto.replace("...", "")
    texto = texto.replace("…", "")
    texto = " ".join(texto.split())
    return texto


def texto_bbox(draw, texto, fonte, stroke_width=0):
    box = draw.textbbox((0, 0), texto, font=fonte, stroke_width=stroke_width)
    return box[2] - box[0], box[3] - box[1]


def gerar_quebras_em_ate_3_linhas(palavras):
    """
    Gera todas as quebras possíveis em 1, 2 ou 3 linhas.
    Nunca corta palavras.
    """
    n = len(palavras)

    if n == 0:
        return [[""]]

    if n == 1:
        return [[palavras[0]]]

    possibilidades = []

    # 1 linha
    possibilidades.append([" ".join(palavras)])

    # 2 linhas
    for i in range(1, n):
        possibilidades.append([
            " ".join(palavras[:i]),
            " ".join(palavras[i:])
        ])

    # 3 linhas
    for i in range(1, n):
        for j in range(i + 1, n):
            possibilidades.append([
                " ".join(palavras[:i]),
                " ".join(palavras[i:j]),
                " ".join(palavras[j:])
            ])

    return possibilidades


def escolher_melhor_quebra(draw, texto, fonte, largura_maxima, max_linhas=3, stroke_width=8):
    """
    Escolhe a melhor quebra em até 3 linhas.
    Não corta palavra.
    Não descarta palavra.
    """
    texto = limpar_titulo(texto)
    palavras = texto.split()

    possibilidades = gerar_quebras_em_ate_3_linhas(palavras)

    melhores = []

    for linhas in possibilidades:
        if len(linhas) > max_linhas:
            continue

        larguras = [
            texto_bbox(draw, linha, fonte, stroke_width=stroke_width)[0]
            for linha in linhas
        ]

        if max(larguras) <= largura_maxima:
            maior = max(larguras)
            menor = min(larguras)
            media = sum(larguras) / len(larguras)

            # Critérios:
            # 1. evitar linhas muito desiguais;
            # 2. ocupar bem a largura;
            # 3. preferir 3 linhas quando o título é grande.
            desequilibrio = maior - menor
            aproveitamento = abs(largura_maxima * 0.82 - media)

            bonus_tres_linhas = 0
            if len(palavras) >= 4 and len(linhas) == 3:
                bonus_tres_linhas = -80

            score = desequilibrio + aproveitamento + bonus_tres_linhas

            melhores.append((score, linhas))

    if melhores:
        melhores.sort(key=lambda x: x[0])
        return melhores[0][1]

    return None


def escolher_fonte_que_cabe(
    draw,
    texto,
    largura_maxima,
    altura_maxima,
    tamanho_min=28,
    tamanho_max=155,
    max_linhas=3,
    entrelinhas=0.84,
    stroke_ratio=0.07
):
    """
    Diminui a fonte até o título completo caber.
    Nunca corta palavras.
    """
    texto = limpar_titulo(texto)

    for tamanho in range(tamanho_max, tamanho_min - 1, -2):
        fonte = carregar_fonte(tamanho)
        stroke_width = max(5, int(tamanho * stroke_ratio))

        linhas = escolher_melhor_quebra(
            draw=draw,
            texto=texto,
            fonte=fonte,
            largura_maxima=largura_maxima,
            max_linhas=max_linhas,
            stroke_width=stroke_width
        )

        if not linhas:
            continue

        altura_linha = int(tamanho * entrelinhas)
        altura_total = altura_linha * len(linhas)

        larguras = [
            texto_bbox(draw, linha, fonte, stroke_width=stroke_width)[0]
            for linha in linhas
        ]

        if altura_total <= altura_maxima and max(larguras) <= largura_maxima:
            return fonte, linhas, tamanho, altura_linha, stroke_width

    raise ValueError(
        f"Não foi possível encaixar o título em {max_linhas} linhas sem cortar palavras: {texto}"
    )


# ============================================================
# EFEITOS VISUAIS
# ============================================================

def criar_gradiente_vertical(largura, altura, cor_topo, cor_base):
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
    texto,
    fonte,
    cor_topo,
    cor_base,
    stroke,
    stroke_width=8
):
    """
    Cria uma camada com:
    - sombra escura;
    - contorno grosso;
    - brilho dourado;
    - preenchimento com gradiente.
    """
    temp = Image.new("RGBA", (2200, 500), (0, 0, 0, 0))
    dtemp = ImageDraw.Draw(temp)

    w, h = texto_bbox(dtemp, texto, fonte, stroke_width=stroke_width)

    largura = w + 120
    altura = h + 110

    x = 55
    y = 40

    final = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))

    # Sombra externa
    sombra = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sombra)
    ds.text(
        (x + 10, y + 13),
        texto,
        font=fonte,
        fill=(0, 0, 0, 210),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 210)
    )
    sombra = sombra.filter(ImageFilter.GaussianBlur(7))
    final.alpha_composite(sombra)

    # Brilho dourado externo
    glow = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    dg.text(
        (x, y),
        texto,
        font=fonte,
        fill=(255, 225, 120, 100),
        stroke_width=stroke_width + 4,
        stroke_fill=(255, 205, 70, 100)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(3))
    final.alpha_composite(glow)

    # Contorno
    contorno = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    dc = ImageDraw.Draw(contorno)
    dc.text(
        (x, y),
        texto,
        font=fonte,
        fill=(255, 255, 255, 255),
        stroke_width=stroke_width,
        stroke_fill=stroke
    )
    final.alpha_composite(contorno)

    # Máscara do preenchimento das letras
    mask = Image.new("L", (largura, altura), 0)
    dm = ImageDraw.Draw(mask)
    dm.text((x, y), texto, font=fonte, fill=255)

    # Gradiente dentro das letras
    grad = criar_gradiente_vertical(largura, altura, cor_topo, cor_base)
    grad.putalpha(mask)
    final.alpha_composite(grad)

    # Luz branca sutil no topo
    brilho = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    db = ImageDraw.Draw(brilho)
    db.text(
        (x - 2, y - 3),
        texto,
        font=fonte,
        fill=(255, 255, 255, 75),
        stroke_width=1,
        stroke_fill=(255, 255, 255, 50)
    )
    final.alpha_composite(brilho)

    return final


# ============================================================
# TEMAS DE CORES
# ============================================================

def escolher_tema(numero):
    """
    Alterna temas claros para as fontes.
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


# ============================================================
# DESENHAR NÚMERO
# ============================================================

def desenhar_numero(base, numero, tema):
    W, H = base.size

    camada = Image.new("RGBA", (330, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    # Sombra do selo
    sombra = Image.new("RGBA", camada.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(sombra)
    ds.rounded_rectangle(
        (15, 18, 320, 140),
        radius=22,
        fill=(0, 0, 0, 130)
    )
    sombra = sombra.filter(ImageFilter.GaussianBlur(7))
    camada.alpha_composite(sombra)

    # Selo
    d.rounded_rectangle(
        (10, 10, 320, 138),
        radius=22,
        fill=tema["selo_fill"],
        outline=tema["selo_borda"],
        width=5
    )

    d.rounded_rectangle(
        (22, 22, 308, 126),
        radius=16,
        outline=(255, 255, 230, 130),
        width=2
    )

    # Fonte do número ajustável
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
        (165, 74),
        numero_txt,
        font=fonte_num,
        fill=tema["numero_fill"],
        anchor="mm",
        stroke_width=4,
        stroke_fill=tema["numero_stroke"]
    )

    # Inclinação
    camada = camada.rotate(-10, expand=True, resample=Image.Resampling.BICUBIC)

    # Posição do selo
    base.alpha_composite(camada, (-5, 12))


# ============================================================
# DESENHAR TÍTULO
# ============================================================

def desenhar_titulo(base, titulo, tema):
    W, H = base.size
    d = ImageDraw.Draw(base)

    # Área onde o título deve caber.
    # Ajuste fino se quiser.
    x1 = int(W * 0.055)
    y1 = int(H * 0.145)
    x2 = int(W * 0.590)
    y2 = int(H * 0.735)

    largura_max = x2 - x1
    altura_max = y2 - y1

    fonte, linhas, tamanho, altura_linha, stroke_width = escolher_fonte_que_cabe(
        draw=d,
        texto=titulo,
        largura_maxima=largura_max,
        altura_maxima=altura_max,
        tamanho_min=28,
        tamanho_max=155,
        max_linhas=3,
        entrelinhas=0.84
    )

    altura_total = altura_linha * len(linhas)

    # Centraliza verticalmente na área do título
    y = y1 + int((altura_max - altura_total) * 0.53)

    for idx, linha in enumerate(linhas):
        # A segunda linha recebe cor de destaque.
        # Exemplo: CRISTO / MEU / MESTRE
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
            stroke_width=stroke_width
        )

        # Inclinação estilo thumbnail
        texto_layer = texto_layer.rotate(-2.2, expand=True, resample=Image.Resampling.BICUBIC)

        # Posição da linha
        base.alpha_composite(texto_layer, (x1 - 42, y - 42))

        y += altura_linha


# ============================================================
# LEITURA DO CSV
# ============================================================

def ler_csv_hinos(csv_path):
    """
    Lê CSV com tolerância para:
    - vírgula;
    - ponto e vírgula;
    - título contendo vírgulas.
    """

    linhas = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        conteudo = f.read().splitlines()

    if not conteudo:
        raise ValueError("CSV vazio.")

    cabecalho = conteudo[0].strip()

    if ";" in cabecalho:
        separador = ";"
    else:
        separador = ","

    for numero_linha, linha in enumerate(conteudo[1:], start=2):
        linha = linha.strip()

        if not linha:
            continue

        partes = linha.split(separador)

        if len(partes) < 2:
            print(f"Aviso: linha {numero_linha} ignorada: {linha}")
            continue

        numero = partes[0].strip().strip('"').strip("'")

        # Junta tudo depois da primeira coluna.
        # Assim, se o título tiver vírgula, não quebra.
        titulo = separador.join(partes[1:]).strip()
        titulo = titulo.strip('"').strip("'").strip()

        if not numero or not titulo:
            print(f"Aviso: linha {numero_linha} sem número ou título: {linha}")
            continue

        linhas.append({
            "numero": numero,
            "titulo": titulo
        })

    return linhas


# ============================================================
# GERAÇÃO
# ============================================================

def gerar_thumb(template_path, saida_path, numero, titulo):
    base = Image.open(template_path).convert("RGBA")

    tema = escolher_tema(numero)

    desenhar_numero(base, numero, tema)
    desenhar_titulo(base, titulo, tema)

    os.makedirs(os.path.dirname(saida_path), exist_ok=True) if os.path.dirname(saida_path) else None

    base.convert("RGB").save(saida_path, quality=95)

    print(f"Gerado: {saida_path}")


def nome_arquivo_seguro(numero):
    numero = str(numero).strip()
    numero = numero.replace("/", "-").replace("\\", "-")
    numero = numero.replace(" ", "_")

    if numero.isdigit():
        return numero.zfill(3)

    return numero


def gerar_em_lote(csv_path, template_path, pasta_saida):
    os.makedirs(pasta_saida, exist_ok=True)

    linhas = ler_csv_hinos(csv_path)

    if not linhas:
        raise ValueError("Nenhum hino encontrado no CSV.")

    erros = []

    for item in linhas:
        numero = item["numero"]
        titulo = item["titulo"]

        saida = os.path.join(
            pasta_saida,
            f"hino_{nome_arquivo_seguro(numero)}.jpg"
        )

        try:
            gerar_thumb(
                template_path=template_path,
                saida_path=saida,
                numero=numero,
                titulo=titulo
            )
        except Exception as e:
            erros.append((numero, titulo, str(e)))
            print(f"ERRO no hino {numero} - {titulo}: {e}")

    if erros:
        print("\nAlguns hinos deram erro:")
        for numero, titulo, erro in erros:
            print(f"- {numero} | {titulo} | {erro}")
    else:
        print("\nTodas as thumbs foram geradas com sucesso.")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gera thumbnails do Hinário com número e nome do hino."
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="CSV com número e nome do hino."
    )

    parser.add_argument(
        "--template",
        required=True,
        help="Imagem base da thumbnail."
    )

    parser.add_argument(
        "--saida",
        required=True,
        help="Pasta de saída."
    )

    args = parser.parse_args()

    gerar_em_lote(
        csv_path=args.csv,
        template_path=args.template,
        pasta_saida=args.saida
    )