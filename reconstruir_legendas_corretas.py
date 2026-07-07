#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reconstruir_legendas_corretas.py

Reconstrói os timestamps de legendas dos hinos lentos com base na
estrutura real dos silêncios do MP3:

  Estrutura descoberta:
  - O 1º silêncio grande (>2s) = FIM da introdução / INÍCIO do canto
  - Os silêncios subsequentes a cada ~80s = PAUSA entre repetições
  - A letra é repetida N vezes ao longo do MP3

  Para cada repetição:
  - Começa logo após o silêncio de transição
  - Os N versos são distribuídos no tempo disponível
  - Cada verso divide o tempo em partes iguais
  - As linhas dentro de cada verso dividem o tempo do verso em partes iguais

Exemplo hino 001 (4 versos × 5 linhas × 2 repetições):
  - Introdução: 0→29.3s (silêncio em 29.3-32.7s)
  - Rep 1: 32.7→109.4s (76.7s para 4 versos)
  - Silêncio 109.4-112.7s
  - Rep 2: 112.7→189.3s (76.6s para 4 versos)
  ... etc.

No vídeo final: offset = +15s (vinheta 10s + frame 5s)
  Logo: silêncio do MP3 em 29.3s = silêncio do vídeo em 44.3s ≈ 45s ✓

Uso:
  python reconstruir_legendas_corretas.py             # todos
  python reconstruir_legendas_corretas.py --numero 1  # hino 1
  python reconstruir_legendas_corretas.py --dry-run   # só mostra
"""

import argparse, json, re, subprocess
from pathlib import Path

MP3_DIR   = Path(__file__).parent / "mp3" / "orgao_eletronico_drawbar"
OFFSET_VIDEO = 15.0  # vinheta(10s) + frame(5s)


# ─────────────────────────────────────────────────────────────────
def detectar_silencias_grandes(mp3_path, limiar_db=-35, dur_min=2.0):
    """Detecta silêncios com duração >= dur_min."""
    r = subprocess.run([
        "ffmpeg", "-i", str(mp3_path),
        "-af", f"silencedetect=noise={limiar_db}dB:d={dur_min}",
        "-f", "null", "-"
    ], capture_output=True, text=True)
    sils, start = [], None
    for line in r.stderr.splitlines():
        ms = re.search(r"silence_start:\s*([\d.]+)", line)
        me = re.search(r"silence_end:\s*([\d.]+)", line)
        if ms: start = float(ms.group(1))
        if me and start is not None:
            end = float(me.group(1))
            sils.append((start, end, end - start))
            start = None
    return sils


def distribuir_linhas_no_intervalo(linhas, t_start, t_end, pausa_entre_linhas=0.08):
    """
    Distribui as linhas da letra uniformemente entre t_start e t_end.
    Respeita pequenas pausas entre linhas.
    """
    n = len(linhas)
    if n == 0:
        return []
    dur_total = t_end - t_start
    dur_por_linha = dur_total / n
    resultado = []
    for i, item in enumerate(linhas):
        ini = t_start + i * dur_por_linha
        fim = ini + dur_por_linha - pausa_entre_linhas
        resultado.append(dict(item, inicio=round(ini, 3), fim=round(fim, 3)))
    return resultado


def reconstruir(letra_ref, silencias, dur_total):
    """
    Usa os silêncios grandes como delimitadores de repetições.
    
    Estrutura:
      [intro] [sil0] [rep1] [sil1] [rep2] [sil2] ... [repN] [silFinal]
    
    A letra (N versos) é distribuída em cada intervalo [repK].
    """
    n_versos = max((item.get("num_verso") or 1) for item in letra_ref)
    n_linhas_por_verso = {}
    versos = {}
    for item in letra_ref:
        v = item.get("num_verso", 1)
        if v not in versos:
            versos[v] = []
        versos[v].append(item)
        n_linhas_por_verso[v] = len(versos[v])

    # Intervalos entre silêncios (= blocos de música)
    # Construir os pontos de fronteira: 0, sil0_start, sil0_end, sil1_start, sil1_end, ...
    fronteiras = [0.0]
    for s, e, d in silencias:
        fronteiras.append(s)   # fim do bloco anterior
        fronteiras.append(e)   # início do bloco seguinte
    fronteiras.append(dur_total)

    # Blocos de música: pares (fronteiras[i], fronteiras[i+1]) onde i é par
    blocos_musica = []
    for i in range(0, len(fronteiras) - 1, 2):
        start = fronteiras[i]
        end   = fronteiras[i + 1]
        if end - start > 3.0:  # ignorar blocos muito curtos
            blocos_musica.append((start, end))

    print(f"    Blocos de música ({len(blocos_musica)}): intro + {len(blocos_musica)-1} repetições")
    for i, (s, e) in enumerate(blocos_musica):
        tag = "intro" if i == 0 else f"rep {i}"
        print(f"      [{tag}] {s:.1f}s → {e:.1f}s ({e-s:.1f}s)")

    # O 1º bloco é a introdução (sem letra)
    # Os blocos 1..N são as repetições do canto
    blocos_canto = blocos_musica[1:]

    if not blocos_canto:
        print(f"    [erro] Nenhum bloco de canto detectado!")
        return None

    num_repeticoes = len(blocos_canto)
    nova_letra = []

    for rep_idx, (b_start, b_end) in enumerate(blocos_canto):
        b_dur = b_end - b_start

        # Distribuir os versos uniformemente no bloco
        dur_por_verso = b_dur / n_versos

        for v_idx, (num_verso, linhas_verso) in enumerate(sorted(versos.items())):
            v_start = b_start + v_idx * dur_por_verso
            v_end   = v_start + dur_por_verso

            linhas_novas = distribuir_linhas_no_intervalo(linhas_verso, v_start, v_end)
            nova_letra.extend(linhas_novas)

    return nova_letra


# ─────────────────────────────────────────────────────────────────
def processar_json(json_path, dry_run=False):
    mp3_path = json_path.with_suffix(".mp3")
    if not mp3_path.exists():
        print(f"  [skip] {json_path.stem[:40]:42s} | MP3 não encontrado")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        dados = json.load(f)

    letra_ref = dados.get("letra", [])
    if not letra_ref:
        return False

    dur_total = float(dados.get("duracao_mp3", 0.0))
    nome = json_path.stem[:50]

    # Detectar silêncios grandes
    silencias = detectar_silencias_grandes(mp3_path, limiar_db=-35, dur_min=2.0)
    if not silencias:
        silencias = detectar_silencias_grandes(mp3_path, limiar_db=-30, dur_min=1.5)

    if not silencias:
        print(f"  [skip] {nome[:50]:52s} | Sem silêncios detectados")
        return False

    print(f"\n  ▶ {nome}")
    print(f"    Silêncios grandes ({len(silencias)}): ", end="")
    print(", ".join(f"{s:.1f}-{e:.1f}s" for s,e,d in silencias[:4]))

    # Extrair somente os versos únicos da referência (1ª repetição)
    versos_unicos = {}
    for item in letra_ref:
        v = item.get("num_verso", 1)
        if v not in versos_unicos:
            versos_unicos[v] = []
        # Adicionar somente se não duplicado por num_linha
        linhas_existentes = [x.get("num_linha") for x in versos_unicos[v]]
        if item.get("num_linha") not in linhas_existentes:
            versos_unicos[v].append(item)

    letra_ref_unica = []
    for v in sorted(versos_unicos.keys()):
        letra_ref_unica.extend(sorted(versos_unicos[v], key=lambda x: x.get("num_linha", 0)))

    print(f"    Versos únicos: {len(versos_unicos)} | Linhas únicas: {len(letra_ref_unica)}")

    nova_letra = reconstruir(letra_ref_unica, silencias, dur_total)
    if nova_letra is None:
        return False

    # Estatísticas
    primeiro_ini = nova_letra[0]["inicio"]
    ultimo_fim   = nova_letra[-1]["fim"]
    cobertura    = ultimo_fim / dur_total * 100

    print(f"    1ª legenda: {primeiro_ini:.1f}s no MP3 = {primeiro_ini + OFFSET_VIDEO:.1f}s no vídeo")
    print(f"    Última:     {ultimo_fim:.1f}s no MP3 = {ultimo_fim + OFFSET_VIDEO:.1f}s no vídeo")
    print(f"    Cobertura:  {cobertura:.0f}% | {len(nova_letra)} linhas")

    if dry_run:
        print(f"    [dry-run] Primeiras 3:")
        for item in nova_letra[:3]:
            print(f"      {item['inicio']:7.1f}s-{item['fim']:7.1f}s | {item['texto'][:40]}")
        print(f"    [dry-run] Últimas 3:")
        for item in nova_letra[-3:]:
            print(f"      {item['inicio']:7.1f}s-{item['fim']:7.1f}s | {item['texto'][:40]}")
        return True

    dados["letra"] = nova_letra
    dados["legendas_reconstruidas"] = True
    dados["legendas_offset_video_s"] = OFFSET_VIDEO
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print(f"    ✅ Salvo!")
    return True


# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--numero", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jsons = sorted(MP3_DIR.glob("*.json"))
    if args.numero:
        num = int(args.numero)
        jsons = [j for j in jsons if re.match(rf"^0*{num}[-\s]", j.name)]

    print(f"{'─'*65}")
    print(f"Processando {len(jsons)} arquivo(s) | offset vídeo = +{OFFSET_VIDEO}s")
    print(f"{'─'*65}")

    atualizados, erros = 0, []
    for j in jsons:
        try:
            ok = processar_json(j, dry_run=args.dry_run)
            if ok: atualizados += 1
        except Exception as e:
            print(f"  ✗ ERRO: {j.name}: {e}")
            import traceback; traceback.print_exc()
            erros.append(j.name)

    print(f"\n{'═'*65}")
    print(f"Atualizados: {atualizados}/{len(jsons)} | Erros: {len(erros)}")


if __name__ == "__main__":
    main()
