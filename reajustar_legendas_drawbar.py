#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reajustar_legendas_drawbar.py — Replica legendas para todas as repetições do hino.

Estratégia:
  A 1ª execução do hino (já mapeada no JSON) vai de letra[0].inicio até letra[-1].fim.
  O MP3 tem duração_total ≈ 2× (ou N×) esse bloco.
  
  Detectamos o período de repetição com ffmpeg silencedetect usando limiar alto,
  que identifica os silêncios entre estrofes, e calculamos o padrão de repetição.
  
  Abordagem principal: 
    period = (dur_total - intro) / num_repeticoes
    A 2ª+ execução começa offset_n = inicio_1a + period × n

Uso:
  python reajustar_legendas_drawbar.py
  python reajustar_legendas_drawbar.py --numero 32
  python reajustar_legendas_drawbar.py --dry-run
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

MP3_DIR = Path(__file__).parent / "mp3" / "orgao_eletronico_drawbar"


def silencias_mp3(path, limiar_db=-40, dur_min=2.0):
    """Detecta silêncios e retorna lista de {'start', 'end', 'dur'}"""
    r = subprocess.run([
        "ffmpeg", "-i", str(path),
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
            sils.append({"start": start, "end": end, "dur": end - start})
            start = None
    return sils


def detectar_inicio_2a_repeticao(letra, dur_total, mp3_path):
    """
    Detecta onde começa a 2ª execução do hino.
    
    Método: a duração da 1ª execução (intro_inicio → ultima_linha_fim) 
    deve repetir-se. Usamos essa duração como período estimado e refinamos
    pela detecção de silêncios.
    
    Retorna (inicio_2a, periodo) onde inicio_2a é o tempo de início
    da 2ª execução (relativo ao início da 1ª).
    """
    inicio_1a = letra[0]["inicio"]
    fim_1a    = letra[-1]["fim"]
    dur_1a    = fim_1a - inicio_1a  # duração da 1ª execução de letra

    # Estimativa: período = duração 1a + silêncio entre repetições
    # Número de repetições esperadas
    num_rep = round((dur_total - inicio_1a) / (dur_1a + 5))  # +5s de pausa estimada
    if num_rep < 2:
        num_rep = 2

    periodo_estimado = (dur_total - inicio_1a) / num_rep

    # Refinar com silencedetect: procurar silêncio logo após fim da 1ª execução
    sils = silencias_mp3(mp3_path, limiar_db=-40, dur_min=2.0)
    
    # Buscar silêncio próximo ao fim estimado da 1ª execução (±30s)
    janela_start = fim_1a - 10
    janela_end   = fim_1a + 30
    sil_transicao = None
    for s in sils:
        if janela_start <= s["start"] <= janela_end:
            sil_transicao = s
            break

    if sil_transicao:
        inicio_2a = sil_transicao["end"]
        periodo   = inicio_2a - inicio_1a
    else:
        # Fallback: período estimado
        inicio_2a = inicio_1a + periodo_estimado
        periodo   = periodo_estimado

    return inicio_2a, periodo, num_rep


def replicar_letra(letra_ref, inicio_1a, inicio_2a, periodo, dur_total):
    """
    Replica os tempos de letra_ref para todas as repetições.
    
    Para cada repetição k (k=0 é a original):
      offset_k = inicio_1a + k * periodo
      nova_linha.inicio = item.inicio - inicio_1a + offset_k
      nova_linha.fim    = item.fim    - inicio_1a + offset_k
    
    Para a repetição 0, mantém os tempos originais (sem modificar).
    Para as demais, replica com o offset correto.
    """
    todas = []

    # Número de repetições que cabem na duração total
    num_reps = 1
    while inicio_1a + num_reps * periodo < dur_total - 5:
        num_reps += 1

    for k in range(num_reps):
        offset_k = inicio_1a + k * periodo
        bloco_fim = min(dur_total - 0.1, offset_k + periodo + 2.0)

        for item in letra_ref:
            t_ini_rel = item["inicio"] - inicio_1a
            t_fim_rel = item["fim"]    - inicio_1a

            abs_ini = offset_k + t_ini_rel
            abs_fim = offset_k + t_fim_rel

            # Não ir além do fim do arquivo
            if abs_ini >= dur_total - 1.0:
                continue
            abs_fim = min(abs_fim, dur_total - 0.05)

            todas.append({
                "texto":     item["texto"],
                "inicio":    round(abs_ini, 3),
                "fim":       round(abs_fim, 3),
                "num_linha": item.get("num_linha"),
                "tipo":      item.get("tipo", "verso"),
                "num_verso": item.get("num_verso"),
            })

    return todas


def processar_json(json_path: Path, dry_run=False, forcar=False):
    mp3_path = json_path.with_suffix(".mp3")
    if not mp3_path.exists():
        print(f"  [skip] MP3 não encontrado: {mp3_path.name}")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        dados = json.load(f)

    letra = dados.get("letra", [])
    if not letra:
        print(f"  [skip] Sem letra: {json_path.name}")
        return False

    dur_total  = float(dados.get("duracao_mp3", 0.0))
    ultimo_fim = letra[-1]["fim"]
    cobertura  = ultimo_fim / dur_total * 100 if dur_total > 0 else 0.0

    nome = json_path.stem[:45]

    if cobertura >= 85.0 and not forcar:
        print(f"  ✓ {nome:47s} | {cobertura:.0f}% OK (até {ultimo_fim:.0f}s)")
        return False

    print(f"  ↺ {nome:47s} | {cobertura:.0f}% ({ultimo_fim:.0f}s/{dur_total:.0f}s)")

    inicio_1a = letra[0]["inicio"]

    try:
        inicio_2a, periodo, num_reps_est = detectar_inicio_2a_repeticao(
            letra, dur_total, mp3_path
        )
    except Exception as e:
        print(f"    [erro] Falha na detecção: {e}")
        return False

    print(f"    Período detectado: {periodo:.1f}s | início 2ª: {inicio_2a:.1f}s | reps est.: {num_reps_est}")

    # Verificar se faz sentido (período deve ser ~igual à duração da 1ª exec)
    dur_1a = letra[-1]["fim"] - inicio_1a
    if abs(periodo - dur_1a) > dur_1a * 0.4:
        # Pode ser que a 1ª exec já tem intro mais curta que as demais
        # Usar período da duração total / repetições
        print(f"    [ajuste] Período {periodo:.1f}s difere muito da duração 1ª exec ({dur_1a:.1f}s)")
        # Tentar calcular baseado em quantas repetições cabem
        for n in range(2, 6):
            p = (dur_total - inicio_1a) / n
            if abs(p - dur_1a) < dur_1a * 0.25:
                periodo = p
                inicio_2a = inicio_1a + periodo
                print(f"    → Usando {n} repetições, período={periodo:.1f}s")
                break

    nova_letra = replicar_letra(letra, inicio_1a, inicio_2a, periodo, dur_total)
    novo_ultimo = nova_letra[-1]["fim"] if nova_letra else 0.0
    nova_cobertura = novo_ultimo / dur_total * 100

    print(f"    Nova cobertura: {nova_cobertura:.0f}% (até {novo_ultimo:.1f}s de {dur_total:.0f}s)")
    print(f"    Total de linhas: {len(letra)} → {len(nova_letra)}")

    if nova_cobertura < cobertura + 5 and not forcar:
        print(f"    [skip] Melhoria insignificante.")
        return False

    if dry_run:
        print(f"    [dry-run] Não salvo.")
        # Mostrar amostra do final
        print(f"    Últimas 3 linhas:")
        for item in nova_letra[-3:]:
            print(f"      {item['inicio']:7.1f}s-{item['fim']:7.1f}s | {item['texto'][:40]}")
        return True

    dados["letra"] = nova_letra
    dados["legendas_revisadas"] = True
    dados["legendas_periodo_s"] = round(periodo, 3)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print(f"    ✅ Salvo — última linha: «{nova_letra[-1]['texto'][:40]}» em {novo_ultimo:.1f}s")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Replica legendas para todas as repetições dos hinos lentos"
    )
    parser.add_argument("--numero", type=str, default=None,
                        help="Número do hino a processar (ex: 32)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostra o que faria sem salvar")
    parser.add_argument("--forcar", action="store_true",
                        help="Reprocessa mesmo arquivos com >85% cobertura")
    args = parser.parse_args()

    jsons = sorted(MP3_DIR.glob("*.json"))
    if not jsons:
        print(f"Nenhum JSON encontrado em {MP3_DIR}")
        return

    if args.numero:
        num = int(args.numero)
        jsons = [j for j in jsons if re.match(rf"^0*{num}[-\s]", j.name)]
        if not jsons:
            print(f"Nenhum JSON para o hino {args.numero}")
            return

    print(f"{'─'*72}")
    print(f"Processando {len(jsons)} arquivo(s) em {MP3_DIR.name}/")
    print(f"{'─'*72}")

    atualizados, erros = 0, []
    for j in jsons:
        try:
            ok = processar_json(j, dry_run=args.dry_run, forcar=args.forcar)
            if ok:
                atualizados += 1
        except Exception as e:
            print(f"  ✗ ERRO: {j.name}: {e}")
            erros.append(j.name)

    print(f"\n{'═'*72}")
    print(f"Resumo: {atualizados} atualizado(s), {len(erros)} erro(s)")

    if not args.dry_run:
        print(f"\nVerificação de cobertura:")
        ok_cnt = ruim = 0
        for j in sorted(MP3_DIR.glob("*.json")):
            try:
                d = json.load(open(j))
                dur = d.get("duracao_mp3", 0)
                lt  = d.get("letra", [])
                ult = lt[-1]["fim"] if lt else 0
                pct = ult / dur * 100 if dur else 0
                if pct >= 85:
                    ok_cnt += 1
                else:
                    ruim += 1
                    print(f"  ⚠️  {j.stem[:50]:52s} | {pct:.0f}% ({ult:.0f}s/{dur:.0f}s)")
            except Exception:
                pass
        print(f"\n  ✅ OK (≥85%): {ok_cnt}   ⚠️  Baixo (<85%): {ruim}")


if __name__ == "__main__":
    main()
