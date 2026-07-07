#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rodar_legendados_orgao_yamaha.py — Gera vídeos base + legendados hino a hino
para o projeto "orgao_yamaha".

A fonte de verdade é a pasta mp3/ — cada arquivo .json corresponde a um hino.
O script é resiliente a interrupções: retoma do ponto onde parou.

Uso:
    python3 rodar_legendados_orgao_yamaha.py
    python3 rodar_legendados_orgao_yamaha.py --forcar-coletaneas
    python3 rodar_legendados_orgao_yamaha.py --pular-base      # só gera legendados
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT      = Path(__file__).parent
MP3_DIR   = ROOT / "mp3"
OUT_DIR   = ROOT / "output" / "orgao_yamaha"
PROJETO   = "orgao_yamaha"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _numero_do_arquivo(json_path: Path):
    """Extrai o número do hino/coro do nome do arquivo JSON."""
    name = json_path.stem  # ex: "001- Cristo meu Mestre"
    # Coro: "Coro 001- ..." ou "C001-..."
    m_coro = re.match(r"(?:Coro\s+|C)0*(\d+)", name, re.IGNORECASE)
    if m_coro:
        return f"C{int(m_coro.group(1))}"
    # Hino normal: "001-...", "001 ..."
    m_hino = re.match(r"^0*(\d+)", name)
    if m_hino:
        return str(int(m_hino.group(1)))
    return None


def _num_fmt(numero_str: str) -> str:
    """Retorna número formatado com 3 dígitos, ex: '1' → '001', 'C1' → 'C001'."""
    if numero_str.upper().startswith("C"):
        return f"C{int(numero_str[1:]):03d}"
    return f"{int(numero_str):03d}"


def _fmt_tempo(seg: float) -> str:
    seg = int(seg)
    h, rem = divmod(seg, 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Descoberta de hinos
# ---------------------------------------------------------------------------

def listar_hinos() -> list[dict]:
    """
    Varre mp3/ em busca de arquivos .json (excluindo ocultos).
    Retorna lista de dicts com 'numero', 'num_fmt', 'json_path'.
    """
    hinos = []
    for p in sorted(MP3_DIR.glob("*.json")):
        if p.name.startswith("."):
            continue
        numero = _numero_do_arquivo(p)
        if numero is None:
            print(f"  [aviso] Não foi possível extrair número de: {p.name}")
            continue
        hinos.append({
            "numero":   numero,
            "num_fmt":  _num_fmt(numero),
            "json_path": p,
        })

    # Ordenar: hinos numéricos primeiro, depois coros
    def sort_key(h):
        n = h["numero"]
        if n.upper().startswith("C"):
            return (1, int(n[1:]))
        return (0, int(n))

    hinos.sort(key=sort_key)
    return hinos


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--forcar-coletaneas", action="store_true",
                        help="Força regeração de coletâneas já existentes.")
    parser.add_argument("--pular-base", action="store_true",
                        help="Pula a geração do vídeo base e vai direto ao legendado.")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    hinos = listar_hinos()
    if not hinos:
        print(f"[erro] Nenhum arquivo JSON encontrado em {MP3_DIR}. Verifique o diretório.")
        sys.exit(1)

    # Filtrar os que já têm legendado
    pendentes = []
    for h in hinos:
        leg_name = f"hino-{PROJETO}-{h['num_fmt']}.mp4"
        legendado = OUT_DIR / leg_name
        if legendado.exists():
            h["skip"] = True
        else:
            h["skip"] = False
            pendentes.append(h)

    ja_prontos = len(hinos) - len(pendentes)
    print(f"\n📋 Projeto: {PROJETO}")
    print(f"   Total de hinos/coros encontrados: {len(hinos)}")
    print(f"   Já finalizados (legendado existe): {ja_prontos}")
    print(f"   A processar agora:                 {len(pendentes)}")
    print()

    if not pendentes:
        print("✅ Todos os vídeos legendados já existem. Nada a fazer.")
    else:
        tempos_totais: list[float] = []

        for i, h in enumerate(pendentes, start=1):
            t_start_hino = time.time()
            dt_base = 0.0
            dt_leg = 0.0

            numero    = h["numero"]
            nfmt      = h["num_fmt"]
            base_name = f"hino-{PROJETO}-{nfmt}.mp4"
            leg_name  = f"hino-{PROJETO}-{nfmt}.mp4"
            base_path = OUT_DIR / base_name
            leg_path  = OUT_DIR / leg_name

            print(f"──────────────────────────────────────────────────────────────────")
            print(f"[{i}/{len(pendentes)}] Hino/Coro: {nfmt}")

            # ── 1. Vídeo base ──────────────────────────────────────────────
            if base_path.exists() and not args.pular_base:
                print(f"  ✓ Vídeo base já existe: {base_name}")
            elif not args.pular_base:
                if leg_path.exists():
                    print(f"  ✓ Legendado final já existe: {leg_name}. Pulando base.")
                else:
                    print(f"  ▶ Gerando vídeo base...")
                    t0 = time.time()
                    res = subprocess.run([
                        sys.executable, "gerar_videos.py",
                        "--projeto", PROJETO,
                        "--apenas", numero,
                        "--sem-download",
                    ], cwd=str(ROOT))
                    dt_base = time.time() - t0
                    if res.returncode != 0:
                        print(f"  ✗ Falha ao gerar vídeo base (código {res.returncode}). Pulando.")
                        continue
                    print(f"  ✓ Vídeo base gerado em {_fmt_tempo(dt_base)}")

            if not base_path.exists() and not leg_path.exists():
                print(f"  ✗ Vídeo base não encontrado após geração: {base_name}. Pulando.")
                continue

            # ── 2. Legendado ───────────────────────────────────────────────
            if leg_path.exists():
                print(f"  ✓ Legendado final já existe: {leg_name}.")
            else:
                print(f"  ▶ Embutindo legendas...")
                t0 = time.time()
                res = subprocess.run([
                    sys.executable, "gerar_legendas.py",
                    "--projeto", PROJETO,
                    "--numero", numero,
                ], cwd=str(ROOT))
                dt_leg = time.time() - t0

                if res.returncode == 0 and leg_path.exists():
                    dt_total_hino = time.time() - t_start_hino
                    tempos_totais.append(dt_total_hino)
                    
                    media = sum(tempos_totais) / len(tempos_totais)
                    restantes = len(pendentes) - i
                    eta = _fmt_tempo(media * restantes)
                    
                    detalhe_tempo = []
                    if dt_base > 0:
                        detalhe_tempo.append(f"base: {_fmt_tempo(dt_base)}")
                    if dt_leg > 0:
                        detalhe_tempo.append(f"legenda: {_fmt_tempo(dt_leg)}")
                    str_detalhe = f" ({', '.join(detalhe_tempo)})" if detalhe_tempo else ""

                    print(f"  ✓ Finalizado em {_fmt_tempo(dt_total_hino)}{str_detalhe}  |  média: {_fmt_tempo(media)}  |  Restam: {restantes} hinos  |  ETA: {eta}")
                    
                    # Atualizar o banco de dados
                    db_path = ROOT / "progresso.db"
                    if db_path.exists():
                        try:
                            from datetime import datetime, timezone
                            now_iso = datetime.now(timezone.utc).isoformat()
                            import sqlite3
                            conn = sqlite3.connect(str(db_path))
                            rel_path = f"output/{PROJETO}/hino-{PROJETO}-{nfmt}.mp4"
                            conn.execute(
                                "UPDATE videos SET output = ?, status = 'concluido', atualizado_em = ? WHERE projeto = ? AND numero = ?",
                                (rel_path, now_iso, PROJETO, numero)
                            )
                            conn.commit()
                            conn.close()
                            print(f"  ✓ Banco de dados atualizado com a saída: {rel_path}")
                        except Exception as db_err:
                            print(f"  [aviso] Não foi possível atualizar o banco de dados: {db_err}")
                else:
                    print(f"  ✗ Falha ao embutir legenda para {nfmt} (código {res.returncode})")

    # ── 3. Coletâneas ──────────────────────────────────────────────────────
    coletaneas_script = ROOT / "gerar_coletaneas.py"
    if coletaneas_script.exists():
        print()
        print("══════════════════════════════════════════════════════════════════")
        print("▶ Gerando coletâneas catalogadas (gerar_coletaneas.py)...")
        print("══════════════════════════════════════════════════════════════════")
        cmd_col = [sys.executable, "gerar_coletaneas.py", "--projeto", PROJETO]
        if args.forcar_coletaneas:
            cmd_col.append("--forcar")
        subprocess.run(cmd_col, cwd=str(ROOT))
    else:
        print(f"\n  [info] gerar_coletaneas.py não encontrado; etapa de coletâneas ignorada.")

    print()
    print("══════════════════════════════════════════════════════════════════")
    print("✅  Processo completo do projeto 'orgao_yamaha' finalizado!")
    print("══════════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
