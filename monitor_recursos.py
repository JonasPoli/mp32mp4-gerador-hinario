#!/usr/bin/env python3
import os
import sys
import time
import json
from datetime import datetime
import subprocess

try:
    import psutil
except ImportError:
    print("Erro: A biblioteca 'psutil' nao esta instalada no ambiente virtual.")
    print("Por favor, execute: .venv/bin/pip install psutil")
    sys.exit(1)

LOG_DIR = "/Volumes/Dados/work/hinário/logs"
STATE_FILE = os.path.join(LOG_DIR, "current_state.json")
LOG_FILE = os.path.join(LOG_DIR, "monitor_recursos.log")

def obter_estado_atual():
    if not os.path.exists(STATE_FILE):
        return {"projeto": "nenhum", "numero": "nenhum", "fase": "ocioso"}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"projeto": "erro_leitura", "numero": "erro_leitura", "fase": "erro_leitura"}

def obter_temperatura_e_limite():
    # macOS sysctl para thermal level (0 = normal, 1 = moderado, 2 = pesado, 3 = critico)
    thermal_level = "N/A"
    try:
        res = subprocess.run(["sysctl", "-n", "kern.thermal_level"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            thermal_level = res.stdout.strip()
    except Exception:
        pass
    return thermal_level

def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Escrever cabecalho informando o inicio do monitoramento
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(f"Iniciando monitoramento de recursos em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"CPU Cores: {psutil.cpu_count(logical=True)} (Fisicos: {psutil.cpu_count(logical=False)})\n")
        f.write(f"Memoria Total: {psutil.virtual_memory().total / (1024**3):.2f} GB\n")
        f.write("=" * 80 + "\n")
        f.flush()
        os.fsync(f.fileno())

    print(f"Monitor de recursos rodando... Logs gravados em: {LOG_FILE}")
    
    # Inicializar os percentuais de CPU por processo para a primeira chamada
    for p in psutil.process_iter(attrs=['cpu_percent']):
        pass

    time.sleep(0.5)

    while True:
        try:
            estado = obter_estado_atual()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            # CPU
            cpu_total = psutil.cpu_percent(interval=None)
            cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
            cpu_cores_str = ",".join(f"{c:.0f}" for c in cpu_cores)
            
            # Memoria
            vm = psutil.virtual_memory()
            ram_pct = vm.percent
            ram_usada = vm.used / (1024**3)
            ram_total = vm.total / (1024**3)
            
            # Swap
            swap = psutil.swap_memory()
            swap_pct = swap.percent
            
            # Load Avg
            load1, load5, load15 = os.getloadavg()
            
            # Thermal level
            term = obter_temperatura_e_limite()

            # Top Processos por CPU e RAM
            proc_list = []
            for p in psutil.process_iter(attrs=['pid', 'name', 'cpu_percent', 'memory_info']):
                try:
                    # Nao incluir o proprio monitor no top
                    if p.info['pid'] == os.getpid():
                        continue
                    cpu_p = p.info['cpu_percent']
                    mem_info = p.info['memory_info']
                    rss_mb = (mem_info.rss if mem_info else 0) / (1024**2)
                    proc_list.append({
                        'pid': p.info['pid'],
                        'name': p.info['name'],
                        'cpu': cpu_p if cpu_p is not None else 0.0,
                        'ram': rss_mb
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            # Ordenar por CPU
            top_cpu = sorted(proc_list, key=lambda x: x['cpu'], reverse=True)[:3]
            top_cpu_str = " | ".join(f"{p['name']}({p['pid']}):{p['cpu']:.1f}%" for p in top_cpu)

            # Ordenar por RAM
            top_ram = sorted(proc_list, key=lambda x: x['ram'], reverse=True)[:3]
            top_ram_str = " | ".join(f"{p['name']}({p['pid']}):{p['ram']:.1f}MB" for p in top_ram)

            # Log line formatada
            log_line = (
                f"[{ts}] "
                f"[PROJ:{estado.get('projeto','nenhum')}] "
                f"[HINO:{estado.get('numero','nenhum')}] "
                f"[FASE:{estado.get('fase','nenhum')}] | "
                f"CPU:{cpu_total:.1f}% [{cpu_cores_str}] | "
                f"RAM:{ram_pct:.1f}% ({ram_usada:.2f}/{ram_total:.2f}GB) | "
                f"Swap:{swap_pct:.1f}% | "
                f"Load:{load1:.2f},{load5:.2f} | "
                f"Thermal:{term} | "
                f"TOP_CPU: {top_cpu_str} | "
                f"TOP_RAM: {top_ram_str}"
            )

            # Se o arquivo de log passar de 5MB, manter apenas as últimas 2000 linhas
            if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 5 * 1024 * 1024:
                try:
                    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f_read:
                        ultimas_linhas = f_read.readlines()[-2000:]
                    with open(LOG_FILE, "w", encoding="utf-8") as f_write:
                        f_write.writelines(ultimas_linhas)
                except Exception:
                    pass

            # Gravar no arquivo forcando o flush e fsync para evitar perdas em caso de panic
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
                f.flush()
                os.fsync(f.fileno())

            time.sleep(2.0)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            # Tentar gravar erro no log
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] ERRO NO MONITOR: {str(e)}\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                pass
            time.sleep(2.0)

if __name__ == "__main__":
    main()
