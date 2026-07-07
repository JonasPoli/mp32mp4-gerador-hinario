#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recalcular_timestamps_legendas.py — Recalcula os timestamps das legendas
usando os silêncios REAIS do áudio como âncoras.

Problema detectado: os timestamps gerados automaticamente não respeitam
as pausas reais do MP3. Ex: linha marcada em 30s mas o áudio está em silêncio.

Solução:
  1. Detectar todos os silêncios do MP3
  2. Construir uma lista de "blocos de áudio" (períodos com som)
  3. Distribuir as linhas da letra nesses blocos, respeitando a estrutura
     de versos (N linhas por verso, com pausa entre versos)
  4. Verificar cobertura e replicar para repetições

Uso:
  python recalcular_timestamps_legendas.py              # todos
  python recalcular_timestamps_legendas.py --numero 1  # só hino 1
  python recalcular_timestamps_legendas.py --dry-run   # mostra sem salvar
"""

import argparse
import json
import re
import subprocess
import numpy as np
from pathlib import Path

MP3_DIR = Path(__file__).parent / "mp3" / "orgao_eletronico_drawbar"
OFFSET_VIDEO_S = 15.0  # vinheta (10s) + frame (5s) no vídeo final


def detectar_silencias(mp3_path, limiar_db=-35, dur_min=0.5):
    """Retorna lista de (start, end, dur) para silêncios encontrados."""
    r = subprocess.run([
        "ffmpeg", "-i", str(mp3_path),
        "-af", f"silencedetect=noise={limiar_db}dB:d={dur_min}",
        "-f", "null", "-"
    ], capture_output=True, text=True)
    sils, start = [], None
    for line in r.stderr.splitlines():
        ms = re.search(r"silence_start:\s*([\d.]+)", line)
        me = re.search(r"silence_end:\s*([\d.]+)", line)
        if ms:
            start = float(ms.group(1))
        if me and start is not None:
            end = float(me.group(1))
            sils.append((start, end, end - start))
            start = None
    return sils


def blocos_de_audio(silencias, dur_total, min_dur_bloco=3.0):
    """
    A partir dos silêncios, extrai períodos com áudio.
    Retorna lista de (start, end, dur).
    """
    blocos = []
    cursor = 0.0
    for s_start, s_end, s_dur in silencias:
        if s_start > cursor + 0.2:
            b_dur = s_start - cursor
            if b_dur >= min_dur_bloco:
                blocos.append((cursor, s_start, b_dur))
        cursor = s_end
    if dur_total - cursor >= min_dur_bloco:
        blocos.append((cursor, dur_total, dur_total - cursor))
    return blocos


def calcular_timestamps_por_blocos(letra, blocos, dur_total):
    """
    Distribui as linhas da letra nos blocos de áudio.

    Estratégia:
    - Agrupa as linhas por verso
    - Cada verso ocupa um bloco (ou parte de um bloco)
    - Dentro de cada verso, as linhas são distribuídas proporcionalmente
    
    Para hinos que repetem:
    - Identifica o período de repetição
    - Replica os tempos para as demais repetições
    """
    # Agrupar linhas por verso
    versos = {}
    for item in letra:
        v = item.get("num_verso", 1)
        if v not in versos:
            versos[v] = []
        versos[v].append(item)
    
    num_versos = len(versos)
    num_linhas_total = len(letra)
    
    if not blocos:
        return None
    
    # Filtrar blocos muito curtos (ruído de transição)
    # Para N versos, esperamos N blocos grandes de áudio
    # Separados por pausas longas (entre versos)
    
    # Calcular limiar de duração para "bloco de verso"
    dur_media_bloco = sum(b[2] for b in blocos) / len(blocos)
    blocos_versos = [b for b in blocos if b[2] >= dur_media_bloco * 0.5]
    
    if len(blocos_versos) < num_versos:
        # Tentar com limiar menor
        blocos_versos = [b for b in blocos if b[2] >= 4.0]
    
    print(f"    {len(blocos)} blocos de áudio → {len(blocos_versos)} blocos de verso (para {num_versos} versos)")
    
    # Verificar se temos repetições
    # Heurística: se blocos_versos > num_versos, há repetição
    num_repeticoes = max(1, round(len(blocos_versos) / num_versos))
    print(f"    Número de repetições detectadas: {num_repeticoes}")
    
    # Para cada bloco de verso, distribuir as linhas daquele verso
    nova_letra = []
    
    for rep in range(num_repeticoes):
        base_bloco = rep * num_versos
        for idx_verso, (num_verso, linhas_verso) in enumerate(sorted(versos.items())):
            bloco_idx = base_bloco + idx_verso
            if bloco_idx >= len(blocos_versos):
                break
            
            b_start, b_end, b_dur = blocos_versos[bloco_idx]
            n_linhas = len(linhas_verso)
            
            # Distribuir linhas uniformemente no bloco
            # Com uma pequena margem de 0.1s no início e 0.3s no fim
            margem_ini = 0.1
            margem_fim = 0.3
            dur_util = b_dur - margem_ini - margem_fim
            
            if dur_util <= 0:
                dur_util = b_dur
                margem_ini = 0.0
                margem_fim = 0.0
            
            dur_linha = dur_util / n_linhas
            
            for idx_linha, item_orig in enumerate(linhas_verso):
                t_ini = b_start + margem_ini + idx_linha * dur_linha
                t_fim = t_ini + dur_linha - 0.05  # pequena folga entre linhas
                
                nova_letra.append({
                    "texto":     item_orig["texto"],
                    "inicio":    round(t_ini, 3),
                    "fim":       round(min(t_fim, b_end - 0.05), 3),
                    "num_linha": item_orig.get("num_linha"),
                    "tipo":      item_orig.get("tipo", "verso"),
                    "num_verso": item_orig.get("num_verso"),
                })
    
    return nova_letra


def verificar_timestamps(letra, silencias, tolerancia=1.0):
    """
    Verifica se alguma linha começa dentro de um silêncio.
    Retorna lista de problemas.
    """
    problemas = []
    for item in letra:
        t = item["inicio"]
        for s_start, s_end, s_dur in silencias:
            if s_dur >= 1.0 and s_start <= t <= s_end:
                problemas.append(
                    f"L{item.get('num_linha')}v{item.get('num_verso')} começa em {t:.1f}s "
                    f"(dentro do silêncio {s_start:.1f}-{s_end:.1f}s)"
                )
    return problemas


def processar_json(json_path, dry_run=False):
    mp3_path = json_path.with_suffix(".mp3")
    if not mp3_path.exists():
        print(f"  [skip] MP3 não encontrado")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        dados = json.load(f)

    letra_orig = dados.get("letra", [])
    if not letra_orig:
        return False

    dur_total = float(dados.get("duracao_mp3", 0.0))
    nome = json_path.stem[:45]
    print(f"\n  ▶ {nome}")

    # Detectar silêncios
    silencias = detectar_silencias(mp3_path, limiar_db=-35, dur_min=0.5)
    
    # Verificar problemas no JSON atual
    problemas = verificar_timestamps(letra_orig, silencias)
    if not problemas:
        print(f"    ✓ Timestamps OK (nenhuma linha em silêncio)")
        return False
    
    print(f"    ⚠️  {len(problemas)} problema(s) encontrado(s):")
    for p in problemas[:3]:
        print(f"      {p}")

    # Construir blocos de áudio
    blocos = blocos_de_audio(silencias, dur_total, min_dur_bloco=3.0)
    print(f"    Blocos de áudio detectados: {len(blocos)}")
    for b in blocos:
        print(f"      {b[0]:7.1f}s → {b[1]:7.1f}s ({b[2]:.1f}s)")

    # Recalcular timestamps
    nova_letra = calcular_timestamps_por_blocos(letra_orig, blocos, dur_total)
    
    if nova_letra is None or len(nova_letra) == 0:
        print(f"    [erro] Não foi possível recalcular.")
        return False

    # Verificar resultado
    novos_problemas = verificar_timestamps(nova_letra, silencias)
    cobertura = nova_letra[-1]["fim"] / dur_total * 100
    
    print(f"    Nova cobertura: {cobertura:.0f}% | Novos problemas: {len(novos_problemas)}")
    print(f"    Primeiras 2 linhas:")
    for item in nova_letra[:2]:
        print(f"      {item['inicio']:7.1f}s-{item['fim']:7.1f}s | {item['texto'][:40]}")
    print(f"    Últimas 2 linhas:")
    for item in nova_letra[-2:]:
        print(f"      {item['inicio']:7.1f}s-{item['fim']:7.1f}s | {item['texto'][:40]}")

    if dry_run:
        print(f"    [dry-run] Não salvo.")
        return True

    if novos_problemas:
        print(f"    [aviso] Ainda há {len(novos_problemas)} problemas após recálculo.")

    dados["letra"] = nova_letra
    dados["timestamps_recalculados"] = True
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print(f"    ✅ Salvo!")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--numero", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jsons = sorted(MP3_DIR.glob("*.json"))
    if args.numero:
        num = int(args.numero)
        jsons = [j for j in jsons if re.match(rf"^0*{num}[-\s]", j.name)]

    print(f"Processando {len(jsons)} arquivo(s)...")
    atualizados = 0
    for j in jsons:
        try:
            ok = processar_json(j, dry_run=args.dry_run)
            if ok:
                atualizados += 1
        except Exception as e:
            print(f"  ✗ ERRO: {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'═'*60}")
    print(f"Atualizados: {atualizados}/{len(jsons)}")


if __name__ == "__main__":
    main()
