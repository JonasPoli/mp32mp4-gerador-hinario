#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_csv_youtube.py — Exporta metadados de vídeos concluídos para upload no YouTube

Uso:
  python gerar_csv_youtube.py --projeto piano_yamaha
"""

import os
import csv
import re
import sys
import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.append(str(ROOT))

from gerar_videos import (
    carregar_projetos,
    abrir_banco,
    carregar_csv,
    limpar_nome_hino,
    formatar_template,
    camel_case,
    remover_acentos,
    carregar_letra_hino,
    formatar_numero_completo,
    carregar_templates_youtube
)

def extrair_metadados(numero: int, nome: str, projeto_nome: str, projeto_cfg: dict) -> tuple[str, str, str]:
    """Retorna o título, descrição e tags formatados para o hino."""
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

    # Format templates
    titulo = formatar_template(titulo_temp, variables)
    descricao = formatar_template(desc_temp, variables)
    tags = formatar_template(tags_temp, variables)

    # Limitar tags a 500 caracteres
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

    # Inserir a letra na descrição
    letra = carregar_letra_hino(numero, projeto_nome)
    if letra:
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

    return titulo, descricao, tags

def main():
    parser = argparse.ArgumentParser(description="Exporta metadados do YouTube para CSV.")
    parser.add_argument("--projeto", required=True, help="Nome do projeto (ex: piano_yamaha)")
    args = parser.parse_args()

    projeto = args.projeto
    projetos = carregar_projetos()
    if projeto not in projetos:
        print(f"[erro] Projeto '{projeto}' não encontrado.")
        sys.exit(1)

    projeto_cfg = projetos[projeto]
    csv_path = ROOT / projeto_cfg.get("csv_path", "")
    hinos_csv = carregar_csv(csv_path)

    conn = abrir_banco()
    cursor = conn.execute(
        "SELECT numero, output, thumb_file FROM videos WHERE projeto = ? AND status = 'concluido' ORDER BY numero",
        (projeto,)
    )
    rows = cursor.fetchall()

    if not rows:
        print(f"Nenhum vídeo concluído encontrado para o projeto '{projeto}'.")
        sys.exit(0)

    # Definir caminhos das pastas de saída
    proj_outputs = ROOT / "projects" / projeto / "outputs"
    proj_outputs.mkdir(parents=True, exist_ok=True)
    csv_out_path = proj_outputs / "youtube_upload.csv"

    print(f"Exportando metadados de {len(rows)} vídeos concluídos para {csv_out_path.relative_to(ROOT)}...")

    headers = ["hino_numero", "titulo", "descricao", "tags", "caminho_video", "caminho_thumbnail"]

    with open(csv_out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for row in rows:
            numero = row["numero"]
            video_rel = row["output"]
            thumb_rel = row["thumb_file"]

            nome_raw = hinos_csv.get(numero) or hinos_csv.get(str(numero)) or f"Hino {numero}"
            nome = limpar_nome_hino(nome_raw)

            titulo, descricao, tags = extrair_metadados(numero, nome, projeto, projeto_cfg)

            # Obter caminhos absolutos
            video_abs = str(ROOT / video_rel) if video_rel else ""
            thumb_abs = str(ROOT / thumb_rel) if thumb_rel else ""

            writer.writerow([
                numero,
                titulo,
                descricao,
                tags,
                video_abs,
                thumb_abs
            ])

    print("✅ Exportação concluída com sucesso!")

if __name__ == "__main__":
    main()
