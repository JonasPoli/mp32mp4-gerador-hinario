#!/usr/bin/env python3
import os
import json
import glob
import re
from datetime import datetime

DIAG_DIR = "/Library/Logs/DiagnosticReports"

def analisar_panic_file(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
        
        if not linhas:
            return None
        
        info = {
            "arquivo": os.path.basename(caminho),
            "data": "Desconhecida",
            "processo": "Desconhecido",
            "cpu": "Desconhecido",
            "causa": "Desconhecido",
            "detalhes": ""
        }
        
        # Tenta parsear como formato JSON/IPS do macOS Moderno (JSON lines)
        meta = {}
        panic_data = {}
        
        try:
            meta = json.loads(linhas[0].strip())
            info["data"] = meta.get("timestamp", "Desconhecida")
        except Exception:
            pass
            
        try:
            panic_data = json.loads(linhas[1].strip())
            panic_str = panic_data.get("macOSPanicString", "")
        except Exception:
            # Caso não seja JSON lines, lê o arquivo todo como texto
            panic_str = "".join(linhas)
            
        if panic_str:
            info["detalhes"] = panic_str.strip()
            
            # Tenta extrair CPU
            # Ex: panic(cpu 4 caller ...)
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
                    
            # Tenta extrair causa/tipo
            trap_match = re.search(r"Kernel trap at.*type\s+\d+=([^,\n]+)", panic_str, re.IGNORECASE)
            if trap_match:
                info["causa"] = trap_match.group(1).strip()
            elif "page fault" in panic_str.lower():
                info["causa"] = "Page Fault (Falha de memória/paginação)"
                
        # Se data continua vazia, usa data de modificação do arquivo
        if info["data"] == "Desconhecida":
            mtime = os.path.getmtime(caminho)
            info["data"] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
        return info
    except Exception as e:
        return {"arquivo": os.path.basename(caminho), "erro": str(e)}

def main():
    print("=" * 75)
    print(" 🔍  Analisador de Kernel Panics (Crash de Sistema) no macOS")
    print("=" * 75)
    
    padrao = os.path.join(DIAG_DIR, "*.panic")
    arquivos = glob.glob(padrao)
    
    # Também buscar logs de extensão .ips (formatos recentes)
    padrao_ips = os.path.join(DIAG_DIR, "Kernel-*.ips")
    arquivos.extend(glob.glob(padrao_ips))
    
    if not arquivos:
        print(f"Nenhum relatório de Kernel Panic encontrado em {DIAG_DIR}.")
        print("Isso sugere que o sistema não gerou logs ou os crashes recentes não foram panics limpos.")
        return
        
    # Ordenar por data de modificação (mais recente primeiro)
    arquivos.sort(key=os.path.getmtime, reverse=True)
    
    print(f"Encontrados {len(arquivos)} relatórios de Kernel Panic. Analisando os mais recentes:\n")
    
    for i, arq in enumerate(arquivos[:3]): # Analisa até os 3 mais recentes
        info = analisar_panic_file(arq)
        if not info or "erro" in info:
            continue
            
        print(f"[{i+1}] Arquivo: {info['arquivo']}")
        print(f"    📅 Data:       {info['data']}")
        print(f"    Processo:   {info['processo']}")
        print(f"    Causa:      {info['causa']}")
        print(f"    Instabilidade no: {info['cpu']}")
        print("    " + "-" * 65)
        
        # Mostrar as primeiras linhas do panic string
        linhas_panic = info["detalhes"].split("\n")
        print("    Resumo do Log:")
        for l in linhas_panic[:4]:
            print(f"      {l}")
        print("=" * 75)
        
    print("\n💡 DICA DE HACKINTOSH:")
    print(" - Se os crashes ocorrem repetidamente no mesmo 'CPU Core' (ex: CPU Core 4),")
    print("   provavelmente esse núcleo específico do processador está instável sob carga pesada.")
    print("   Considere revisar undervoltings, LLC (Load Line Calibration) na BIOS ou refrigeração.")
    print(" - Page Faults / SMAP faults sob carga alta de renderização muitas vezes indicam RAM instável")
    print("   (desative XMP/ajuste timings) ou necessidade de um pequeno aumento de voltagem do CPU Core/Vcore.")

if __name__ == "__main__":
    main()
