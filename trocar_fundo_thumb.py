from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw
import argparse
import os


def fit_cover(img, size):
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)


def criar_mascara_area_fundo(w, h, proteger_direita=True):
    """
    Máscara branca = onde a nova imagem aparece.
    Máscara preta = onde a nova imagem não aparece.

    A ideia é aplicar mais no fundo/esquerda/centro
    e proteger a caixa de música, logo e etiquetas.
    """

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    # Área principal onde o fundo novo pode aparecer.
    # Vai da esquerda até um pouco antes da caixa de música.
    draw.rectangle((0, 0, int(w * 0.72), h), fill=255)

    # Também deixa aparecer um pouco atrás da caixa, mas mais fraco via gradiente.
    draw.rectangle((int(w * 0.62), 0, int(w * 0.82), h), fill=130)

    if proteger_direita:
        # Protege a região da caixa de música
        draw.rectangle((int(w * 0.58), int(h * 0.30), w, h), fill=0)

        # Protege o logo superior direito
        draw.rectangle((int(w * 0.76), 0, w, int(h * 0.34)), fill=0)

        # Protege a etiqueta "Caixa de Música"
        draw.rectangle((int(w * 0.68), int(h * 0.86), w, h), fill=0)

        # Protege faixa inferior esquerda/centro onde estão textos fixos
        draw.rectangle((0, int(h * 0.76), int(w * 0.62), h), fill=0)

    # Suaviza a máscara para não ficar recortado duro
    mask = mask.filter(ImageFilter.GaussianBlur(45))

    return mask


def aplicar_troca_de_fundo(
    template_path,
    fundo_path,
    saida_path,
    opacidade=0.38,
    blur=5,
    escurecer=0.65,
    saturacao=0.85,
    verde=0.55,
    apagar_fundo_antigo=0.65,
    escala=1.0,
    posicao_x=0.45,
    posicao_y=0.45,
    proteger_direita=True,
):
    template = Image.open(template_path).convert("RGBA")
    W, H = template.size

    fundo = Image.open(fundo_path).convert("RGB")

    # Redimensiona o novo fundo
    target_w = int(W * escala)
    target_h = int(H * escala)

    fundo = fit_cover(fundo, (target_w, target_h))

    # Ajusta aparência do print para virar fundo
    fundo = ImageEnhance.Brightness(fundo).enhance(escurecer)
    fundo = ImageEnhance.Color(fundo).enhance(saturacao)

    if blur > 0:
        fundo = fundo.filter(ImageFilter.GaussianBlur(blur))

    fundo = fundo.convert("RGBA")

    # Posicionamento manual por porcentagem
    # 0.0 = esquerda/topo, 0.5 = centro, 1.0 = direita/baixo
    x = int((W - target_w) * posicao_x)
    y = int((H - target_h) * posicao_y)

    camada_novo_fundo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    camada_novo_fundo.alpha_composite(fundo, (x, y))

    # Máscara da área onde o novo fundo pode aparecer
    mask = criar_mascara_area_fundo(W, H, proteger_direita=proteger_direita)

    # Controla opacidade do novo fundo
    mask_novo_fundo = mask.point(lambda p: int(p * opacidade))

    # Camada verde escura para "apagar" a flor antiga
    camada_verde = Image.new("RGBA", (W, H), (3, 35, 18))
    mask_verde = mask.point(lambda p: int(p * apagar_fundo_antigo))
    camada_verde.putalpha(mask_verde)

    # Filtro verde por cima do novo fundo para manter identidade
    filtro_verde = Image.new("RGBA", (W, H), (3, 42, 22))
    mask_filtro = mask.point(lambda p: int(p * verde))
    filtro_verde.putalpha(mask_filtro)

    # Aplica máscara no novo fundo
    camada_novo_fundo.putalpha(mask_novo_fundo)

    # Ordem:
    # 1. template original
    # 2. camada verde escura por cima para esconder fundo antigo
    # 3. novo fundo por cima com opacidade
    # 4. filtro verde por cima
    final = template.copy()
    final = Image.alpha_composite(final, camada_verde)
    final = Image.alpha_composite(final, camada_novo_fundo)
    final = Image.alpha_composite(final, filtro_verde)

    # Reforça borda original, caso tenha escurecido um pouco
    draw = ImageDraw.Draw(final)
    draw.rectangle((0, 0, W - 1, H - 1), outline=(214, 165, 25, 255), width=10)

    final = final.convert("RGB")
    os.makedirs(os.path.dirname(saida_path), exist_ok=True) if os.path.dirname(saida_path) else None
    final.save(saida_path, quality=95)

    print(f"Imagem gerada: {saida_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Troca/funde o fundo da thumb mantendo a arte base.")
    parser.add_argument("--template", required=True)
    parser.add_argument("--fundo", required=True)
    parser.add_argument("--saida", required=True)

    parser.add_argument("--opacidade", type=float, default=0.38)
    parser.add_argument("--blur", type=float, default=5)
    parser.add_argument("--escurecer", type=float, default=0.65)
    parser.add_argument("--saturacao", type=float, default=0.85)
    parser.add_argument("--verde", type=float, default=0.55)
    parser.add_argument("--apagar", type=float, default=0.65)

    parser.add_argument("--escala", type=float, default=1.0)
    parser.add_argument("--x", type=float, default=0.45)
    parser.add_argument("--y", type=float, default=0.45)

    parser.add_argument("--nao-proteger-direita", action="store_true")

    args = parser.parse_args()

    aplicar_troca_de_fundo(
        template_path=args.template,
        fundo_path=args.fundo,
        saida_path=args.saida,
        opacidade=args.opacidade,
        blur=args.blur,
        escurecer=args.escurecer,
        saturacao=args.saturacao,
        verde=args.verde,
        apagar_fundo_antigo=args.apagar,
        escala=args.escala,
        posicao_x=args.x,
        posicao_y=args.y,
        proteger_direita=not args.nao_proteger_direita,
    )