#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_legendas.py — Gerador e embutidor de legendas (letras) nos vídeos dos hinos.

Uso:
  python gerar_legendas.py --projeto hinos_de_ninar --numero 1
  python gerar_legendas.py --projeto piano_yamaha --numero 53 --saida-legendado output/legendados/hino-53.mp4
"""

import os
import re
import csv
import sys
import json
import argparse
import subprocess
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent
LETRAS_DIR = ROOT / "hinos_txt" / "letras_separadas"
MP3_DIR = ROOT / "mp3"
OUTPUT_DIR = ROOT / "output"

def carregar_letra_hino(numero: int, projeto_nome: str = "") -> list[list[str]]:
    """
    Busca a letra do hino/coro e agrupa em estrofes (lista de linhas).
    """
    indice_path = LETRAS_DIR / "_indice.csv"
    if not indice_path.exists():
        print(f"[erro] _indice.csv não encontrado em {LETRAS_DIR}")
        return []

    num_str = str(numero).strip()
    is_coro = num_str.upper().startswith("C") and num_str[1:].isdigit()
    if not is_coro:
        is_coro = "coro" in projeto_nome.lower()

    if is_coro:
        if num_str.upper().startswith("C"):
            num_int = int(num_str[1:])
        else:
            num_int = int(num_str)
        tipo_busca = "coro"
    else:
        num_int = int(num_str)
        tipo_busca = "hino"

    arquivo = None
    with open(indice_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tipo_csv = row.get("tipo", "").strip().lower()
            try:
                num_csv = int(row.get("numero", "").strip())
            except (ValueError, AttributeError):
                continue
            if tipo_csv == tipo_busca and num_csv == num_int:
                arquivo = row.get("arquivo", "").strip()
                break

    if not arquivo:
        print(f"[aviso] Hino/Coro {numero} não encontrado no _indice.csv")
        return []

    letra_path = LETRAS_DIR / arquivo
    if not letra_path.exists():
        print(f"[erro] Arquivo de letra {letra_path} não existe.")
        return []

    linhas = letra_path.read_text(encoding="utf-8").splitlines()
    if not linhas:
        return []

    # Ignorar primeira linha se contiver "Hino" ou "Coro"
    inicio_linha = 0
    if "hino" in linhas[0].lower() or "coro" in linhas[0].lower():
        inicio_linha = 1

    # Agrupar por estrofes
    estrofes = []
    estrofe_atual = []
    for i in range(inicio_linha, len(linhas)):
        linha = linhas[i].strip()
        if not linha:
            if estrofe_atual:
                estrofes.append(estrofe_atual)
                estrofe_atual = []
            continue
        
        # Remove número da estrofe no início se houver (ex: "1. Cristo..." -> "Cristo...")
        linha_limpa = re.sub(r"^\d+\.\s*", "", linha)
        # Se for coro, remove indicativo "Coro:"
        linha_limpa = re.sub(r"^coro:\s*", "", linha_limpa, flags=re.IGNORECASE)
        
        estrofe_atual.append(linha_limpa)

    if estrofe_atual:
        estrofes.append(estrofe_atual)

    return estrofes

def encontrar_arquivo_mp3(numero: int, projeto_nome: str = "") -> Path | None:
    """Busca o arquivo MP3 do hino no diretório mp3/."""
    num_str = str(numero).strip()
    is_coro = num_str.upper().startswith("C") and num_str[1:].isdigit()
    
    pattern = f"*{int(num_str[1:] if is_coro else num_str):03d}*.mp3"
    
    # Busca com padrão de 3 dígitos
    for p in MP3_DIR.glob(pattern):
        if p.name.startswith("."):
            continue
        return p
    
    # Fallback para busca por número no início do nome
    for p in MP3_DIR.glob("*.mp3"):
        if p.name.startswith("."):
            continue
        if is_coro:
            if p.name.lower().startswith(f"coro {int(num_str[1:]):03d}") or p.name.lower().startswith(f"coro {int(num_str[1:])}"):
                return p
        else:
            if p.name.startswith(f"{int(num_str):03d}") or p.name.startswith(f"{numero}-") or p.name.startswith(f"{numero} "):
                return p
                
    return None

def duracao_audio(caminho: Path) -> float:
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

def detectar_transicoes_estrofes(mp3_path: Path, num_estrofes: int, duracao_total: float) -> list[float]:
    """
    Analisa o envelope de energia do áudio para achar as transições entre estrofes.
    Retorna os tempos de início de cada estrofe (exclui a introdução).
    """
    print("  [audio] Analisando envelope de energia do áudio...")
    try:
        # Converter MP3 para PCM usando FFmpeg
        cmd = [
            'ffmpeg', '-i', str(mp3_path),
            '-f', 'f32le', '-acodec', 'pcm_f32le', '-ar', '16000', '-ac', '1', '-'
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        stdout, _ = process.communicate()
        audio = np.frombuffer(stdout, dtype=np.float32)
        sr = 16000
    except Exception as e:
        print(f"  [aviso] Falha ao ler PCM do áudio: {e}. Usando fallback linear.")
        return []

    if len(audio) == 0:
        return []

    # Computa energia em blocos de 1 segundo com hop de 100ms
    frame_size = 16000
    hop_size = 1600
    energy = []
    times = []
    for i in range(0, len(audio) - frame_size, hop_size):
        energy.append(np.sum(audio[i:i+frame_size]**2))
        times.append(i / sr)

    energy = np.array(energy)
    times = np.array(times)
    
    if len(energy) == 0:
        return []

    energy /= np.max(energy)
    
    # Suaviza a curva de energia levemente para filtrar ruídos pontuais
    smooth_energy = np.convolve(energy, np.ones(5)/5, mode='same')

    # Detecta mínimos locais (vales) de energia
    # Para N estrofes, esperamos N-1 transições + 1 início (introdução)
    minima = []
    window_size = 100  # 10 segundos
    for i in range(window_size, len(smooth_energy) - window_size):
        local_window = smooth_energy[i - window_size : i + window_size]
        if smooth_energy[i] == np.min(local_window) and smooth_energy[i] < 0.20:
            minima.append((times[i], smooth_energy[i]))

    # Filtrar mínimos muito próximos (gaps entre versos devem ter pelo menos 15s)
    filtered_minima = []
    for t, e in minima:
        if not filtered_minima or t - filtered_minima[-1][0] > 15:
            filtered_minima.append((t, e))

    # O número total de seções esperadas é num_estrofes + 1 (introdução)
    transicoes_esperadas = num_estrofes
    
    # Se encontramos exatamente o número esperado de transições relevantes
    if len(filtered_minima) == transicoes_esperadas:
        print(f"  [audio] Transições detectadas automaticamente: {[round(t, 2) for t, _ in filtered_minima]}s")
        return [t for t, _ in filtered_minima]
    
    # Se encontramos transições próximas (ex: tolerância de +/- 1)
    if abs(len(filtered_minima) - transicoes_esperadas) <= 1 and len(filtered_minima) > 0:
        tempos = [t for t, _ in filtered_minima]
        # Se faltou uma transição, estimamos a última proporcionalmente
        while len(tempos) < transicoes_esperadas:
            diff_media = np.mean(np.diff([0] + tempos)) if len(tempos) > 1 else tempos[0]
            tempos.append(tempos[-1] + diff_media)
        # Se sobrou, cortamos o excesso
        tempos = tempos[:transicoes_esperadas]
        print(f"  [audio] Transições ajustadas/estimadas: {[round(t, 2) for t in tempos]}s")
        return tempos

    print(f"  [audio] Não foi possível mapear com precisão ({len(filtered_minima)} mínimos achados para {transicoes_esperadas} esperados). Usando fallback linear.")
    return []

def calcular_tempos_legendas(estrofes: list[list[str]], mp3_path: Path, offset: float = 0.0) -> list[dict]:
    """Calcula os tempos precisos para cada estrofe e linha da legenda."""
    dur_total = duracao_audio(mp3_path)
    num_estrofes = len(estrofes)
    
    # Tenta detecção de áudio
    transicoes = detectar_transicoes_estrofes(mp3_path, num_estrofes, dur_total)
    
    # Fallback Linear se a detecção falhar
    if not transicoes:
        intro_padrao = 15.0 if dur_total > 40 else 5.0
        tempo_restante = dur_total - intro_padrao
        dur_estrofe = tempo_restante / num_estrofes
        transicoes = [intro_padrao + i * dur_estrofe for i in range(num_estrofes)]

    # Adiciona a duração total como limite superior final
    limites = transicoes + [dur_total]
    
    mapa_legendas = []
    # Mapear cada estrofe
    for idx_est, estrofe in enumerate(estrofes):
        inicio_est = limites[idx_est]
        fim_est = limites[idx_est + 1]
        dur_est = fim_est - inicio_est
        
        # Divide o tempo da estrofe igualmente pelo número de linhas dela
        num_linhas = len(estrofe)
        dur_linha = dur_est / num_linhas
        
        for idx_lin, linha in enumerate(estrofe):
            inicio_lin = inicio_est + idx_lin * dur_linha
            fim_lin = inicio_lin + dur_linha
            
            # Deixar uma pequena folga de 50ms no final para a transição
            fim_lin = max(inicio_lin + 0.5, fim_lin - 0.05)
            
            mapa_legendas.append({
                "texto": linha,
                "inicio": inicio_lin + offset,
                "fim": fim_lin + offset
            })
            
    return mapa_legendas

def formatar_tempo_ass(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int(round((segundos - int(segundos)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def gerar_arquivo_ass(mapa_legendas: list[dict], output_ass: Path, hino_nome: str):
    """Escreve as legendas no formato ASS (Advanced SubStation Alpha)."""
    conteudo = []
    
    # Cabeçalho padrão do script ASS
    conteudo.append("[Script Info]")
    conteudo.append(f"; Legenda gerada automaticamente para {hino_nome}")
    conteudo.append(f"Title: {hino_nome}")
    conteudo.append("ScriptType: v4.00+")
    conteudo.append("WrapStyle: 0")
    conteudo.append("PlayResX: 1920")
    conteudo.append("PlayResY: 1080")
    conteudo.append("ScaledBorderAndShadow: yes")
    conteudo.append("")
    
    # Definição de Estilo
    # Fonte: Montserrat
    # Cores no formato ASS BGR (Blue-Green-Red) em hexadecimal: &HAABBGGRR
    # PrimaryColour: &H00FFFFFF (Branco)
    # OutlineColour: &H000F3C21 (Verde Escuro CCB - R:33, G:60, B:15 -> &H000F3C21)
    conteudo.append("[V4+ Styles]")
    conteudo.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    conteudo.append("Style: Default,Montserrat,58,&H00FFFFFF,&H000000FF,&H000F3C21,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,10,10,120,1")
    conteudo.append("")
    
    # Eventos de Diálogo
    conteudo.append("[Events]")
    conteudo.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
    
    for item in mapa_legendas:
        inicio = formatar_tempo_ass(item["inicio"])
        fim = formatar_tempo_ass(item["fim"])
        texto = item["texto"]
        # Efeito de Fade in e Fade out de 250ms com {\fad(250,250)}
        conteudo.append(f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{{\\fad(250,250)}}{texto}")
        
    output_ass.write_text("\n".join(conteudo), encoding="utf-8")

def embutir_legenda_no_video(video_origem: Path, ass_path: Path, video_destino: Path):
    """Chama o FFmpeg para embutir as legendas ASS no vídeo final usando caminhos relativos."""
    print(f"  [ffmpeg] Embutindo legendas no vídeo...")
    
    # Caminhos relativos a ROOT para evitar problemas de escape de caracteres no FFmpeg
    rel_video_origem = str(video_origem.relative_to(ROOT))
    rel_ass_path = str(ass_path.relative_to(ROOT))
    rel_video_destino = str(video_destino.relative_to(ROOT))
    
    # Escapar caracteres especiais que possam existir no nome relativo
    rel_ass_path = rel_ass_path.replace(":", "\\:").replace("'", "'\\''")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", rel_video_origem,
        "-vf", f"subtitles=filename='{rel_ass_path}'",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        rel_video_destino
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed with code {result.returncode}.\nStderr:\n{result.stderr}")

def main():
    parser = argparse.ArgumentParser(description="Gera e embuti legendas em vídeos de hinos.")
    parser.add_argument("--projeto", required=True, help="Nome do projeto (ex: hinos_de_ninar)")
    parser.add_argument("--numero", required=True, help="Número do hino/coro (ex: 53 ou C1)")
    parser.add_argument("--saida-legendado", help="Caminho do arquivo de vídeo de saída")
    parser.add_argument("--legenda-json", help="Caminho para arquivo JSON com legendas sincronizadas")
    args = parser.parse_args()

    numero_str = args.numero
    try:
        numero = int(numero_str)
    except ValueError:
        numero = numero_str # coros: "C1"

    projeto = args.projeto
    
    print(f"Iniciando processo de legendas para o Hino {numero} (Projeto: {projeto})...")
    
    # 1. Carrega estrofes/letra ou JSON customizado
    estrofes = None
    dados_legenda = None
    if args.legenda_json:
        legenda_json_path = Path(args.legenda_json)
        if not legenda_json_path.exists():
            print(f"[erro] Arquivo JSON de legendas {legenda_json_path} não existe.")
            sys.exit(1)
        try:
            with open(legenda_json_path, "r", encoding="utf-8") as f:
                dados_legenda = json.load(f)
            print(f"  [legenda] Carregada legenda personalizada de {legenda_json_path.name}")
        except Exception as e:
            print(f"[erro] Falha ao carregar JSON de legendas: {e}")
            sys.exit(1)
    else:
        estrofes = carregar_letra_hino(numero, projeto)
        if not estrofes:
            print("[erro] Letra não pôde ser carregada.")
            sys.exit(1)
        
    # 2. Localiza arquivo MP3
    mp3_path = encontrar_arquivo_mp3(numero, projeto)
    if not mp3_path:
        print("[erro] Arquivo MP3 não encontrado.")
        sys.exit(1)
        
    if estrofes:
        print(f"  Letra carregada: {len(estrofes)} estrofes encontradas.")
    print(f"  Áudio localizado: {mp3_path.name}")
    
    # 3. Carregar projetos.json para calcular o offset (vinheta + frame)
    projetos_cfg_path = ROOT / "projetos.json"
    if projetos_cfg_path.exists():
        try:
            with open(projetos_cfg_path, "r", encoding="utf-8") as f:
                projetos_cfg = json.load(f)
        except Exception as e:
            print(f"  [aviso] Erro ao carregar projetos.json: {e}")
            projetos_cfg = {}
    else:
        projetos_cfg = {}

    projeto_cfg = projetos_cfg.get(projeto, {})
    vinheta_cfg = projeto_cfg.get("vinheta", "")
    dur_vinheta = 0.0
    if vinheta_cfg:
        vinheta_path = Path(vinheta_cfg)
        if not vinheta_path.is_absolute():
            vinheta_path = ROOT / vinheta_path
        if vinheta_path.exists():
            dur_vinheta = duracao_audio(vinheta_path)
            print(f"  [offset] Vinheta configurada: {vinheta_path.name} ({dur_vinheta:.2f}s)")
        else:
            print(f"  [aviso] Vinheta configurada não encontrada: {vinheta_path}")

    # Delay do áudio no vídeo final: dur_vinheta + FRAME_DURATION (5s)
    offset = dur_vinheta + 5.0
    print(f"  [offset] Aplicando deslocamento de legenda: {offset:.2f}s (vinheta={dur_vinheta:.2f}s + frame=5s)")

    # 4. Calcula os tempos ou monta a partir do JSON
    if dados_legenda:
        mapa_legendas = []
        for item in dados_legenda.get("letra", []):
            mapa_legendas.append({
                "texto": item["texto"],
                "inicio": float(item["inicio"]) + offset,
                "fim": float(item["fim"]) + offset
            })
    else:
        mapa_legendas = calcular_tempos_legendas(estrofes, mp3_path, offset=offset)
    
    # 4. Escreve arquivo de legendas ASS temporário
    tmp_ass = ROOT / f"_tmp_legenda_{projeto}_{numero}.ass"
    gerar_arquivo_ass(mapa_legendas, tmp_ass, f"Hino {numero}")
    print(f"  Legendas calculadas/carregadas e salvas em {tmp_ass.name}")
    
    # 5. Localiza o vídeo gerado original
    num_fmt = f"{int(numero_str[1:] if numero_str.upper().startswith('C') else numero_str):03d}"
    if numero_str.upper().startswith('C'):
        num_fmt = f"C{num_fmt}"
        
    video_original = OUTPUT_DIR / f"hino-{projeto}-{num_fmt}.mp4"
    if not video_original.exists():
        # tenta sem formatação de 3 dígitos
        video_original = OUTPUT_DIR / f"hino-{projeto}-{numero}.mp4"
        
    if not video_original.exists():
        print(f"[erro] Vídeo original não encontrado em {OUTPUT_DIR}. Certifique-se de gerar o vídeo primeiro usando gerar_videos.py.")
        tmp_ass.unlink(missing_ok=True)
        sys.exit(1)
        
    # 6. Define arquivo de saída
    if args.saida_legendado:
        video_saida = Path(args.saida_legendado)
    else:
        video_saida = OUTPUT_DIR / f"hino-{projeto}-{num_fmt}-legendado.mp4"
        
    video_saida.parent.mkdir(parents=True, exist_ok=True)
    
    # 7. Executa o FFmpeg para embutir as legendas
    try:
        embutir_legenda_no_video(video_original, tmp_ass, video_saida)
        print(f"\n✅ Vídeo legendado gerado com sucesso em: {video_saida.relative_to(ROOT)}")
    except Exception as e:
        print(f"\n✗ Erro ao gerar vídeo legendado: {e}")
    finally:
        # Limpar arquivo temporário de legendas
        tmp_ass.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
