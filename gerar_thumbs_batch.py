#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_thumbs_batch.py — Geração em lote de thumbnails no novo formato (v01)

Regenera ou gera pela primeira vez as thumbnails de múltiplos projetos usando
o pipeline visual de gerar_thumb_v01.py. Salva diretamente em thumbs/, no
formato esperado por gerar_videos.py (sobrescreve arquivos existentes).

─────────────────────────────────────────────────────────────────────────────
PROJETOS SUPORTADOS
─────────────────────────────────────────────────────────────────────────────
  hinos_de_ninar  → Gera para TODOS os hinos do CSV (480 hinos)
  orgao_yamaha    → Gera apenas os hinos com status='concluido' no banco
  piano_yamaha    → Gera apenas os hinos com status='concluido' no banco
  hinario5        → Gera para TODOS os hinos do CSV (480 hinos)
  coros           → Gera para TODOS os hinos do CSV

─────────────────────────────────────────────────────────────────────────────
SAÍDA
─────────────────────────────────────────────────────────────────────────────
  thumbs/hino-{projeto}-NNN.png  → arquivo final (PNG, sobrescreve existente)

─────────────────────────────────────────────────────────────────────────────
USO
─────────────────────────────────────────────────────────────────────────────
  # Gera hinos_de_ninar (todos) + orgao_yamaha (concluídos):
  python gerar_thumbs_batch.py

  # Gera apenas um projeto específico:
  python gerar_thumbs_batch.py --projeto hinos_de_ninar
  python gerar_thumbs_batch.py --projeto orgao_yamaha

  # Regenera apenas um hino específico em todos os projetos do lote:
  python gerar_thumbs_batch.py --apenas 53

  # Regenera um hino específico num projeto específico:
  python gerar_thumbs_batch.py --projeto orgao_yamaha --apenas 20
"""

import argparse
import csv
import json
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT      = Path(__file__).parent
THUMBS_DIR = ROOT / "thumbs"

# ── Importações dos outros módulos do projeto ────────────────────────────────
from gerar_thumb_v01 import gerar_thumb as _gerar_thumb_v01
from gerar_thumb_v02 import gerar_thumb as _gerar_thumb_v02
from gerar_videos import formatar_numero_completo
from PIL import Image


def carregar_projetos() -> dict:
    """
    Carrega o arquivo projetos.json com as configurações de cada projeto.

    Returns:
        Dicionário com nome_do_projeto → dicionário de configurações.
    """
    return json.load(open(ROOT / "projetos.json", encoding="utf-8"))


def carregar_hinos_csv(csv_path: Path) -> dict[int, str]:
    """
    Carrega o mapeamento número→nome a partir de um CSV do hinário.

    Detecta automaticamente as colunas de número e nome procurando pelas
    palavras "número"/"numero" e "nome"/"título"/"titulo" nos cabeçalhos.

    Args:
        csv_path: Caminho para o arquivo CSV (ex: fontes/hinario5.csv).

    Returns:
        Dicionário {numero_int: nome_str} com todos os hinos do arquivo.
    """
    hinos = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            num_key  = next((k for k in row if "número" in k.lower() or "numero" in k.lower()), None)
            nome_key = next((k for k in row if "nome" in k.lower() or "título" in k.lower() or "titulo" in k.lower()), None)
            if num_key and nome_key:
                try:
                    hinos[int(row[num_key].strip())] = row[nome_key].strip()
                except ValueError:
                    pass
    return hinos


def hinos_concluidos_db(projeto_nome: str) -> list[int]:
    """
    Retorna os números dos hinos que já foram totalmente processados para um projeto.

    Consulta a tabela 'videos' do banco SQLite (progresso.db) e filtra
    apenas os registros com status='concluido', em ordem crescente.

    Args:
        projeto_nome: Chave do projeto (ex: "orgao_yamaha").

    Returns:
        Lista de inteiros com os números dos hinos concluídos.
    """
    conn = sqlite3.connect(str(ROOT / "progresso.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT numero FROM videos WHERE projeto = ? AND status = 'concluido' ORDER BY numero",
        (projeto_nome,),
    ).fetchall()
    conn.close()
    return [r["numero"] for r in rows]


def gerar_thumb_novo(numero: int, nome: str, projeto_nome: str, instrumento_path: str | None = None) -> Path:
    """
    Gera uma thumbnail no novo formato para um hino e salva no caminho esperado.

    Processo:
      1. Chama gerar_thumb_v01 para criar o JPEG em um arquivo temporário.
      2. Converte o JPEG para PNG e salva em thumbs/hino-{projeto}-NNN.png.
      3. Remove o arquivo temporário.

    O arquivo PNG de saída sobrescreve qualquer versão anterior sem aviso.

    Args:
        numero:           Número do hino (inteiro).
        nome:             Nome do hino.
        projeto_nome:     Chave do projeto (ex: "hinos_de_ninar").
        instrumento_path: Caminho do PNG do instrumento definido no projeto
                          (campo "instrumento" em projetos.json). None = aleatório.

    Returns:
        Path do arquivo PNG salvo em thumbs/.
    """
    num_fmt   = formatar_numero_completo(numero)
    dest_path = THUMBS_DIR / f"hino-{projeto_nome}-{num_fmt}.png"

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # hinos_de_ninar usa pipeline v02 (máscara do canal Hinos de Ninar + troca de fundo)
        # todos os outros projetos continuam usando v01
        if projeto_nome == "hinos_de_ninar":
            _gerar_thumb_v02(
                numero_hino=numero,
                titulo_hino=nome,
                output_path=tmp_path,
                instrumento_path=instrumento_path,
            )
        else:
            _gerar_thumb_v01(
                numero_hino=numero,
                titulo_hino=nome,
                output_path=tmp_path,
                instrumento_path=instrumento_path,
            )
        Image.open(tmp_path).convert("RGB").save(str(dest_path))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return dest_path



def gerar_thumbs_projeto(projeto_nome: str, projeto_cfg: dict, numeros: list[int]) -> tuple[int, int]:
    """
    Gera thumbnails para uma lista de números de hinos em um projeto.

    Itera sobre os números fornecidos, busca o nome no CSV do projeto e
    chama gerar_thumb_novo para cada um. Registra e conta sucessos e erros.

    Args:
        projeto_nome: Chave do projeto.
        projeto_cfg:  Configurações do projeto (do projetos.json).
        numeros:      Lista de números de hinos a processar.

    Returns:
        Tupla (quantidade_ok, quantidade_erros).
    """
    hinos_csv = ROOT / projeto_cfg.get("csv_path", "fontes/hinario5.csv")
    todos     = carregar_hinos_csv(hinos_csv)

    ok = erros = 0
    for numero in numeros:
        nome = todos.get(numero)
        if not nome:
            print(f"  [{projeto_nome}] Hino {numero} não encontrado no CSV — pulando")
            erros += 1
            continue
        try:
            gerar_thumb_novo(numero, nome, projeto_nome, instrumento_path=projeto_cfg.get("instrumento"))

            num_fmt = formatar_numero_completo(numero)
            print(f"  ✓ {num_fmt}  {nome[:55]}")
            ok += 1
        except Exception as e:
            print(f"  ✗ Erro hino {numero}: {e}")
            erros += 1

    print(f"\n  {ok} thumbs geradas, {erros} erros — projeto: {projeto_nome}")
    return ok, erros


def main():
    parser = argparse.ArgumentParser(
        description="Geração em lote de thumbnails v01 para projetos do Hinário CCB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python gerar_thumbs_batch.py
  python gerar_thumbs_batch.py --projeto hinos_de_ninar
  python gerar_thumbs_batch.py --projeto orgao_yamaha --apenas 20
        """
    )
    parser.add_argument(
        "--projeto",
        choices=["hinos_de_ninar", "orgao_yamaha", "piano_yamaha", "coros", "hinario5"],
        help="Projeto a processar (padrão: hinos_de_ninar + orgao_yamaha)",
    )
    parser.add_argument(
        "--apenas", type=int,
        help="Gera apenas este número de hino (em todos os projetos do lote)",
    )
    args = parser.parse_args()

    projetos = carregar_projetos()
    THUMBS_DIR.mkdir(exist_ok=True)

    # Define quais projetos processar
    tarefas = [args.projeto] if args.projeto else ["hinos_de_ninar", "orgao_yamaha"]

    total_ok = total_err = 0

    for proj in tarefas:
        cfg = projetos[proj]
        print(f"\n{'='*60}")
        print(f"Projeto: {proj} ({cfg.get('nome_exibicao', proj)})")

        # Determina quais hinos gerar
        if args.apenas:
            numeros = [args.apenas]
        elif proj in ("orgao_yamaha", "piano_yamaha"):
            # Para projetos parcialmente gerados: só os que já têm vídeo
            numeros = hinos_concluidos_db(proj)
            print(f"  → {len(numeros)} hinos concluídos no banco")
        else:
            # Para projetos completos: todos do CSV
            hinos_csv = ROOT / cfg.get("csv_path", "fontes/hinario5.csv")
            todos     = carregar_hinos_csv(hinos_csv)
            numeros   = sorted(todos.keys())
            print(f"  → {len(numeros)} hinos no CSV")

        print(f"{'='*60}")
        ok, err = gerar_thumbs_projeto(proj, cfg, numeros)
        total_ok  += ok
        total_err += err

    print(f"\n{'='*60}")
    print(f"TOTAL: {total_ok} thumbs geradas, {total_err} erros")
    print(f"📁 {THUMBS_DIR}  (PNGs para upload no YouTube)")


if __name__ == "__main__":
    main()
