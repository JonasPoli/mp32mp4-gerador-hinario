#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corrigir_timestamps_legendas.py — Corrige timestamps das legendas que 
caem dentro de silêncios do áudio.

Estratégia SIMPLES e correta:
  1. Detectar silêncios do MP3
  2. Para cada linha da letra cujo .inicio cai dentro de um silêncio:
     → Mover o .inicio para o fim do silêncio + 0.05s
     → Mover o .fim proporcionalmente
  3. Verificar que nenhuma linha sobrepõe silêncios longos
  4. Também verifica e ajusta o .fim se cair dentro de um silêncio longo

Contexto do projeto:
  - Vinheta: 10s + Frame: 5s → offset no vídeo = 15s
  - Os timestamps no JSON são em relação ao início do MP3
  - No vídeo, adicionar 15s para saber onde a legenda aparece

Uso:
  python corrigir_timestamps_legendas.py              # todos
  python corrigir_timestamps_legendas.py --numero 1  # só hino 1  
  python corrigir_timestamps_legendas.py --dry-run   # mostra sem salvar
"""

import argparse, json, re, subprocess
from pathlib import Path

MP3_DIR = Path(__file__).parent / "mp3" / "orgao_eletronico_drawbar"


def detectar_silencias(mp3_path, limiar_db=-35, dur_min=0.8):
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


def ponto_em_silencio(t, silencias, limiar_dur=0.5):
    """Retorna o silêncio (start, end) se t cair dentro de um, senão None."""
    for s, e, d in silencias:
        if d >= limiar_dur and s <= t <= e:
            return (s, e)
    return None


def corrigir_linha(item, silencias, dur_total):
    """
    Corrige o inicio e fim de uma linha da letra.
    Se o inicio cair em silêncio → move para fim_silencio + 0.05s.
    Se o fim   cair em silêncio → move para inicio_silencio - 0.05s.
    """
    ini = item["inicio"]
    fim = item["fim"]
    corrigido = False

    # Corrigir inicio
    sil = ponto_em_silencio(ini, silencias)
    if sil:
        novo_ini = sil[1] + 0.05  # logo após o silêncio
        duracao_orig = fim - ini
        novo_fim = novo_ini + duracao_orig
        item = dict(item, inicio=round(novo_ini, 3), fim=round(novo_fim, 3))
        ini, fim = item["inicio"], item["fim"]
        corrigido = True

    # Corrigir fim (se cair em silêncio, truncar antes)
    sil_fim = ponto_em_silencio(fim, silencias)
    if sil_fim and sil_fim != ponto_em_silencio(ini, silencias):
        novo_fim = sil_fim[0] - 0.05
        if novo_fim > ini + 0.5:  # manter pelo menos 0.5s de duração
            item = dict(item, fim=round(novo_fim, 3))
            corrigido = True

    # Garantir que não ultrapassa o fim do arquivo
    if item["fim"] > dur_total - 0.05:
        item = dict(item, fim=round(dur_total - 0.05, 3))

    return item, corrigido


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
    nome = json_path.stem[:50]

    # Detectar silêncios
    silencias = detectar_silencias(mp3_path)

    # Encontrar linhas problemáticas (caem em silêncios)
    problemas_antes = []
    for item in letra_orig:
        if ponto_em_silencio(item["inicio"], silencias):
            problemas_antes.append(item)

    if not problemas_antes:
        print(f"  ✓ {nome[:50]:52s} | OK")
        return False

    print(f"\n  ↺ {nome[:50]}")
    print(f"    {len(problemas_antes)} linha(s) com início em silêncio:")
    for item in problemas_antes[:3]:
        sil = ponto_em_silencio(item["inicio"], silencias)
        print(f"      L{item.get('num_linha')}v{item.get('num_verso')} "
              f"em {item['inicio']:.1f}s (silêncio {sil[0]:.1f}-{sil[1]:.1f}s) "
              f"| {item['texto'][:30]}")

    # Corrigir todas as linhas
    nova_letra = []
    num_corrigidas = 0
    for item in letra_orig:
        item_corr, foi_corrigido = corrigir_linha(item, silencias, dur_total)
        nova_letra.append(item_corr)
        if foi_corrigido:
            num_corrigidas += 1

    # Verificar resultado
    problemas_depois = [
        item for item in nova_letra
        if ponto_em_silencio(item["inicio"], silencias)
    ]

    # Verificar cobertura
    cobertura = nova_letra[-1]["fim"] / dur_total * 100

    print(f"    Corrigidas: {num_corrigidas} | Problemas restantes: {len(problemas_depois)}")
    print(f"    Cobertura: {cobertura:.0f}%")
    print(f"    Primeiras linhas:")
    for item in nova_letra[:2]:
        print(f"      {item['inicio']:7.1f}s - {item['fim']:7.1f}s | {item['texto'][:40]}")
    print(f"    Últimas linhas:")
    for item in nova_letra[-2:]:
        print(f"      {item['inicio']:7.1f}s - {item['fim']:7.1f}s | {item['texto'][:40]}")

    if dry_run:
        print(f"    [dry-run] Não salvo.")
        return True

    dados["letra"] = nova_letra
    dados["timestamps_corrigidos"] = True
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

    print(f"Verificando {len(jsons)} arquivo(s)...")
    atualizados = 0
    for j in jsons:
        try:
            ok = processar_json(j, dry_run=args.dry_run)
            if ok: atualizados += 1
        except Exception as e:
            print(f"  ✗ ERRO em {j.name}: {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'═'*60}")
    print(f"Arquivos com correções: {atualizados}/{len(jsons)}")


if __name__ == "__main__":
    main()
