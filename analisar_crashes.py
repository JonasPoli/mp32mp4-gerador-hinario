#!/usr/bin/env python3
import os
import sys
import glob
import re
import json
from datetime import datetime

DIAG_DIR = "/Library/Logs/DiagnosticReports"
LOG_DIR = "/Volumes/Dados/work/hinário/logs"
MONITOR_LOG = os.path.join(LOG_DIR, "monitor_recursos.log")

def ler_ultimas_linhas(caminho, n=15):
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
        return [l.strip() for l in linhas[-n:]]
    except Exception as e:
        return [f"Erro ao ler logs de recursos: {str(e)}"]

def analisar_panic_file(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
        
        if not linhas:
            return None
        
        info = {
            "arquivo": os.path.basename(caminho),
            "data": "Desconhecida",
            "dt_obj": None,
            "processo": "Desconhecido",
            "cpu": "Desconhecido",
            "causa": "Desconhecido",
            "detalhes": ""
        }
        
        # IPS format / JSON lines macOS moderno
        panic_str = ""
        try:
            meta = json.loads(linhas[0].strip())
            timestamp_str = meta.get("timestamp", "")
            info["data"] = timestamp_str
            # Tenta parsear datetime (ex: 2026-07-10 19:29:38.00 -0300)
            # Remove timezones para parse simplificado
            clean_ts = re.sub(r"\s*[-+]\d{4}$", "", timestamp_str)
            info["dt_obj"] = datetime.strptime(clean_ts.split(".")[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
            
        try:
            panic_data = json.loads(linhas[1].strip())
            panic_str = panic_data.get("macOSPanicString", "")
        except Exception:
            panic_str = "".join(linhas)
            
        if panic_str:
            info["detalhes"] = panic_str.strip()
            
            # Tenta extrair CPU
            cpu_match = re.search(r"panic\(cpu\s+(\d+)", panic_str, re.IGNORECASE)
            if cpu_match:
                info["cpu"] = f"CPU Core {cpu_match.group(1)}"
            else:
                fault_cpu_match = re.search(r"Fault CPU:\s*(\w+)", panic_str, re.IGNORECASE)
                if fault_cpu_match:
                    info["cpu"] = f"CPU Core {fault_cpu_match.group(1)}"
                    
            # Tenta extrair processo/task
            proc_match = re.search(r"Process name corresponding to current thread \([^)]+\):\s*([^\n\r]+)", panic_str)
            if proc_match:
                info["processo"] = proc_match.group(1).strip()
            else:
                task_match = re.search(r"Panicked task\s+[^:]+:\s*\d+\s+threads:\s*pid\s+\d+:\s*([^\n\r]+)", panic_str)
                if task_match:
                    info["processo"] = task_match.group(1).strip()
                    
            # Causa
            trap_match = re.search(r"Kernel trap at.*type\s+\d+=([^,\n]+)", panic_str, re.IGNORECASE)
            if trap_match:
                info["causa"] = trap_match.group(1).strip()
            elif "page fault" in panic_str.lower():
                info["causa"] = "Page Fault (Falha de memoria/paginacao)"
                
        if info["data"] == "Desconhecida":
            mtime = os.path.getmtime(caminho)
            info["data"] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            info["dt_obj"] = datetime.fromtimestamp(mtime)
            
        return info
    except Exception as e:
        return {"arquivo": os.path.basename(caminho), "erro": str(e)}

def main():
    print("=" * 85)
    print(" 🛠️  Analisador de Recursos e Diagnostico de Crashes — Hinario CCB")
    print("=" * 85)

    # 1. Procurar Kernel Panics do macOS
    padrao = os.path.join(DIAG_DIR, "*.panic")
    arquivos = glob.glob(padrao)
    padrao_ips = os.path.join(DIAG_DIR, "Kernel-*.ips")
    arquivos.extend(glob.glob(padrao_ips))
    
    ultimo_panic = None
    if arquivos:
        arquivos.sort(key=os.path.getmtime, reverse=True)
        ultimo_panic = analisar_panic_file(arquivos[0])

    # 2. Exibir ultimo Panic detectado
    if ultimo_panic and "erro" not in ultimo_panic:
        print("\n🚨 ULTIMO KERNEL PANIC REGISTRADO PELO MACOS:")
        print(f"   Arquivo:      {ultimo_panic['arquivo']}")
        print(f"   Data/Hora:    {ultimo_panic['data']}")
        print(f"   Processo:     {ultimo_panic['processo']}")
        print(f"   Causa/Trap:   {ultimo_panic['causa']}")
        print(f"   Core Instavel: {ultimo_panic['cpu']}")
        print("   " + "-" * 70)
        linhas_p = ultimo_panic["detalhes"].split("\n")
        print("   Detalhes do Panic:")
        for l in linhas_p[:3]:
            print(f"     {l}")
    else:
        print("\nℹ️  Nenhum Kernel Panic recente registrado pelo macOS.")
        print("   Se o computador reiniciou de repente sem salvar logs, isso pode indicar:")
        print("   1. Corte de energia de protecao (temperatura muito alta ou voltagem baixa demais na CPU).")
        print("   2. Instabilidade critica da placa-mae ou fonte de alimentacao.")

    # 3. Ler logs de Recursos
    print("\n📊 ULTIMOS REGISTROS DO MONITOR DE RECURSOS (Logs locais):")
    linhas_log = ler_ultimas_linhas(MONITOR_LOG, 10)
    
    if not linhas_log:
        print(f"   [Nenhum log de monitoramento encontrado em {MONITOR_LOG}]")
    else:
        for l in linhas_log:
            print(f"   {l}")

    # 4. Correlacao e Dicas de Solucao de Problemas
    print("\n💡 CORRELACAO E RECOMENDACOES DE ESTABILIDADE:")
    
    # Se temos monitor_recursos.log, extrair ultimo estado
    ultimo_estado_recursos = None
    if linhas_log and not linhas_log[-1].startswith("Erro"):
        # Tentar extrair dados da ultima linha
        # Exemplo: [2026-07-10 19:29:38.123] [PROJ:hinos_de_ninar] [HINO:014] [FASE:embutindo legendas] | CPU:78.5% ...
        linha = linhas_log[-1]
        proj_match = re.search(r"\[PROJ:([^\]]+)\]", linha)
        hino_match = re.search(r"\[HINO:([^\]]+)\]", linha)
        fase_match = re.search(r"\[FASE:([^\]]+)\]", linha)
        cpu_match = re.search(r"CPU:([\d\.]+)%", linha)
        ram_match = re.search(r"RAM:([\d\.]+)%", linha)
        
        if proj_match and hino_match and fase_match:
            print(f"   📍 O pipeline parou em: Projeto '{proj_match.group(1)}', Hino {hino_match.group(1)}, Fase '{fase_match.group(1)}'")
            if cpu_match and ram_match:
                print(f"      Uso de recursos no ultimo segundo: CPU {cpu_match.group(1)}% | RAM {ram_match.group(1)}%")
        
    if ultimo_panic and "erro" not in ultimo_panic:
        causa = ultimo_panic['causa'].lower()
        processo = ultimo_panic['processo'].lower()
        
        if "page fault" in causa or "smap" in causa:
            print("   ⚠️  Diagnostico: Falha de Pagina (Page Fault) sob carga alta.")
            print("      - Esta falha indica que a CPU tentou ler ou escrever em um endereco de memoria invalido.")
            print("      - Causa provavel 1: Instabilidade na memoria RAM (timings muito apertados, XMP instavel, ou pente defeituoso).")
            print("      - Causa provavel 2: Instabilidade do proprio CPU Core. Um nucleo instavel por undervolt")
            print("        ou Vcore insuficiente pode errar calculos de ponteiro de memoria e causar um Page Fault falso.")
            print("      - Acao sugerida: Desativar XMP/perfil de overclock de RAM temporariamente na BIOS e retestar.")
        elif "double fault" in causa:
            print("   ⚠️  Diagnostico: Double Fault (Falha dupla da CPU).")
            print("      - Ocorre quando a CPU falha ao tentar tratar uma falha anterior. Indica instabilidade severa de hardware.")
            print("      - Acao sugerida: Revisar voltagens de CPU na BIOS. Se houver undervolt, reduza-o (aumente a voltagem).")
        
        if "cpu" in ultimo_panic['cpu'].lower():
            core = ultimo_panic['cpu']
            print(f"   ⚠️  Diagnostico: Kernel Panic recorrente no '{core}'.")
            print(f"      - Se os crashes apontam sempre para o mesmo nucleo, este nucleo especifico esta instavel.")
            print("      - Acao sugerida: Aumentar ligeiramente o Vcore (voltagem do nucleo) ou ajustar o Load Line Calibration (LLC)")
            print("        na BIOS para evitar a queda de voltagem sob carga pesada (Vdroop).")
    else:
        print("   ⚠️  Como nao ha logs de Kernel Panic recentes para este crash, a placa-mae provavelmente reiniciou")
        print("      instantaneamente devido a uma protecao fisica de hardware:")
        print("      - Protecao Termica: A CPU passou da temperatura limite (geralmente 100°C) e desligou instantaneamente.")
        print("      - Protecao de Corrente/Voltagem: A fonte ou o circuito VRM da placa-mae nao suportou o pico de consumo")
        print("        da CPU durante a codificacao do FFmpeg e desarmou/reiniciou.")
        print("      - Acao sugerida: Instalar o 'Intel Power Gadget' ou utilitario de monitoramento do Hackintosh para checar")
        print("        as temperaturas sob carga. Limpar coolers e trocar pasta termica se necessario.")

    print("=" * 85 + "\n")

if __name__ == "__main__":
    main()
