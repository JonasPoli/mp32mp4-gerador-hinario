#!/usr/bin/env bash
# =============================================================================
# rodar_todos_projetos.sh — Gera vídeos base + legendados para múltiplos
# projetos do Hinário CCB, em sequência.
#
# Cada projeto é processado completamente antes de passar ao próximo.
# Se interrompido, basta rodar novamente — continua de onde parou.
#
# Uso:
#   ./rodar_todos_projetos.sh                          # processa todos os projetos pendentes
#   ./rodar_todos_projetos.sh --pular-base             # só gera legendados (pula vídeo base)
#   ./rodar_todos_projetos.sh --projeto brass           # processa apenas o projeto 'brass'
#   ./rodar_todos_projetos.sh --projeto brass --projeto string  # processa 'brass' e 'string'
# =============================================================================

set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

# Separar argumentos específicos deste shell e outros a serem repassados para o python
PULAR_BASE=""
FILTRO_PROJETOS=()
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pular-base)
            PULAR_BASE="--pular-base"
            shift
            ;;
        --projeto)
            if [[ -n "$2" && ! "$2" =~ ^-- ]]; then
                FILTRO_PROJETOS+=("$2")
                shift 2
            else
                echo "  ❌ Erro: --projeto requer um nome de projeto." >&2
                exit 1
            fi
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

# Função para validar integridade de vídeos (evita usar vídeos corrompidos por crashes)
validar_video() {
    local f="$1"
    [ -f "$f" ] && [ -s "$f" ] && ffprobe -v error "$f" >/dev/null 2>&1
}

# Coordenação com outros scripts (lock por hino)
LOCK_DIR="/tmp/hinario-locks"
mkdir -p "$LOCK_DIR"
_MY_LOCKS=()


# Limpar locks órfãos (crash/reboot anterior)
for _stale in "$LOCK_DIR"/*.lock; do
    [ -d "$_stale" ] || continue
    _pid_file="$_stale/pid"
    if [ -f "$_pid_file" ]; then
        _old_pid=$(cat "$_pid_file" 2>/dev/null)
        if [ -n "$_old_pid" ] && ! kill -0 "$_old_pid" 2>/dev/null; then
            rm -f "$_pid_file"
            rmdir "$_stale" 2>/dev/null && echo "  🧹 Lock órfão removido: $(basename "$_stale")" || true
        fi
    else
        # Lock sem PID — com certeza órfão
        rmdir "$_stale" 2>/dev/null && echo "  🧹 Lock órfão removido: $(basename "$_stale")" || true
    fi
done

# Inicializar monitor de recursos de hardware
mkdir -p logs
MONITOR_PID=""
cleanup() {
    # Liberar locks de hinos
    for _lk in "${_MY_LOCKS[@]}"; do
        rm -f "$_lk/pid" 2>/dev/null
        rmdir "$_lk" 2>/dev/null || true
    done
    # Parar monitor de recursos
    if [ -n "$MONITOR_PID" ]; then
        echo ""
        echo "  ⏹ Parando o monitor de recursos (PID: $MONITOR_PID)..."
        kill "$MONITOR_PID" 2>/dev/null || true
        wait "$MONITOR_PID" 2>/dev/null || true
        rm -f logs/current_state.json
    fi
}
trap cleanup EXIT INT TERM

echo "  ▶ Iniciando o monitor de recursos de hardware..."
.venv/bin/python monitor_recursos.py > /dev/null 2>&1 &
MONITOR_PID=$!


# Projetos a processar (na ordem solicitada)
if [ ${#FILTRO_PROJETOS[@]} -gt 0 ]; then
    PROJETOS=("${FILTRO_PROJETOS[@]}")
else
    PROJETOS=(
        "hinos_de_ninar"
        "piano_yamaha"
        "brass"
        "string"
        "palhetas"
        "sopro"
        "orquestra"
        "orquestra2"
        "meia_hora"
        "coros"
    )
fi

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  🎵  Pipeline de Geração de Vídeos Legendados — Hinário CCB"
echo "══════════════════════════════════════════════════════════════════"
echo "  Projetos: ${PROJETOS[*]}"
echo "  Total:    ${#PROJETOS[@]} projetos"
echo "══════════════════════════════════════════════════════════════════"
echo ""

TOTAL_PROJETOS=${#PROJETOS[@]}
PROJETO_ATUAL=0

for PROJETO in "${PROJETOS[@]}"; do
    PROJETO_ATUAL=$((PROJETO_ATUAL + 1))

    echo ""
    echo "┌──────────────────────────────────────────────────────────────────┐"
    echo "│  [$PROJETO_ATUAL/$TOTAL_PROJETOS] Projeto: $PROJETO"
    echo "└──────────────────────────────────────────────────────────────────┘"

    # Verificar se o diretório de inputs existe (ler de config.json se possível)
    CONFIG_JSON="projects/$PROJETO/config.json"
    if [ -f "$CONFIG_JSON" ]; then
        INPUTS_DIR=$($PYTHON -c "import json; d=json.load(open('$CONFIG_JSON')); print(d.get('mp3_dir', d.get('inputs_dir', 'projects/$PROJETO/inputs')))" 2>/dev/null || echo "projects/$PROJETO/inputs")
    else
        INPUTS_DIR="projects/$PROJETO/inputs"
    fi
    if [ ! -d "$INPUTS_DIR" ]; then
        echo "  ⚠️  Diretório de inputs não encontrado: $INPUTS_DIR — Pulando."
        continue
    fi

    # Contar hinos (MP3s disponíveis)
    TOTAL_MP3=$(find "$INPUTS_DIR" -maxdepth 1 -name "*.mp3" ! -name "._*" | wc -l | tr -d ' ')
    echo "  📋 Total de MP3s encontrados: $TOTAL_MP3"

    # Criar diretório de saída
    OUTPUT_PROJ="output/$PROJETO"
    mkdir -p "$OUTPUT_PROJ"

    # Contar JSON de legendas disponíveis
    TOTAL_JSON=$(find "$INPUTS_DIR" -maxdepth 1 -name "*.json" ! -name "._*" | wc -l | tr -d ' ')
    echo "  📄 Total de JSONs de legenda: $TOTAL_JSON"

    # Listar os JSONs de legenda e processar cada um
    PROCESSADOS=0
    PULADOS=0
    ERROS=0
    START_TIME=$(date +%s)

    while IFS= read -u 3 -r -d '' JSON_FILE; do
        JSON_NAME=$(basename "$JSON_FILE")

        # Extrair número do hino do nome do arquivo
        # Suporta: hino_001.json, 001.json, 001- Nome.json, Coro 001- Nome.json, coro_001.json
        NUMERO=""
        if [[ "$JSON_NAME" =~ ^hino_([0-9]+)\.json$ ]]; then
            NUMERO=$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')
        elif [[ "$JSON_NAME" =~ ^([0-9]+)\.json$ ]]; then
            NUMERO=$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')
        elif [[ "$JSON_NAME" =~ ^([0-9]+)[-\ ] ]]; then
            NUMERO=$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')
        elif [[ "$JSON_NAME" =~ ^[Cc]oro_([0-9]+)\.json$ ]]; then
            NUMERO="C$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')"
        elif [[ "$JSON_NAME" =~ ^[Cc]oro\ +([0-9]+)\.json$ ]]; then
            NUMERO="C$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')"
        elif [[ "$JSON_NAME" =~ ^[Cc]oro\ +([0-9]+)[-\ ] ]]; then
            NUMERO="C$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')"
        fi

        if [ -z "$NUMERO" ]; then
            echo "  [aviso] Não foi possível extrair número de: $JSON_NAME — Pulando."
            continue
        fi

        if [[ "$NUMERO" =~ ^C([0-9]+)$ ]]; then
            NUM_FMT="C$(printf "%03d" "${BASH_REMATCH[1]}")"
        else
            NUM_FMT=$(printf "%03d" "$NUMERO")
        fi

        # O nome padronizado do legendado é hino-{projeto}-{NNN}.mp4
        LEGENDADO="$OUTPUT_PROJ/hino-$PROJETO-$NUM_FMT.mp4"
        BASE_VIDEO="$OUTPUT_PROJ/hino-$PROJETO-$NUM_FMT.mp4"

        # Verificar no banco de dados se o hino já foi concluído (com legendas)
        STATUS=$($PYTHON -c "
import sqlite3
conn = sqlite3.connect('progresso.db')
val = '$NUMERO'
try:
    val = int(val)
except ValueError:
    pass
r = conn.execute('SELECT status FROM videos WHERE projeto=? AND numero=?', ('$PROJETO', val)).fetchone()
print(r[0] if r else 'pendente')
conn.close()
" 2>/dev/null || echo "pendente")

        # Só pula completamente se status=concluido (legendas já embutidas e íntegras)
        if [ "$STATUS" = "concluido" ] && [ -f "$LEGENDADO" ]; then
            if validar_video "$LEGENDADO"; then
                PULADOS=$((PULADOS + 1))
                continue
            else
                echo "  ⚠️  Vídeo legendado corrompido pós-crash encontrado: $(basename "$LEGENDADO") — apagando..."
                rm -f "$LEGENDADO"
            fi
        fi

        # Tentar lock por hino (mkdir atômico) — pular se outro processo já está trabalhando
        HINO_LOCK="$LOCK_DIR/${PROJETO}-${NUMERO}.lock"
        if ! mkdir "$HINO_LOCK" 2>/dev/null; then
            echo "  ⏭ Hino $NUM_FMT ($PROJETO) — em uso por outro processo, pulando."
            PULADOS=$((PULADOS + 1))
            continue
        fi
        echo $$ > "$HINO_LOCK/pid"
        _MY_LOCKS+=("$HINO_LOCK")

        PROCESSADOS=$((PROCESSADOS + 1))
        RESTANTES=$((TOTAL_JSON - PROCESSADOS - PULADOS - ERROS))

        echo ""
        echo "  ──────────────────────────────────────────────────────────"
        echo "  [$PROCESSADOS] Hino $NUM_FMT ($PROJETO) — Restantes: ~$RESTANTES"

        # ── 1. Gerar vídeo base (se não existe/válido e não foi pedido para pular) ──
        if [ "$PULAR_BASE" != "--pular-base" ]; then
            if [ "$STATUS" = "base_pronto" ] && validar_video "$BASE_VIDEO"; then
                echo "  ✓ Vídeo base já existe e está íntegro (base_pronto): $(basename $BASE_VIDEO)"
            elif ! validar_video "$BASE_VIDEO"; then
                if [ -f "$BASE_VIDEO" ]; then
                    echo "  ⚠️  Vídeo base corrompido pós-crash encontrado: $(basename "$BASE_VIDEO") — apagando para regerar..."
                    rm -f "$BASE_VIDEO"
                fi
                echo "  ▶ Gerando vídeo base..."
                echo "{\"projeto\": \"$PROJETO\", \"numero\": \"$NUM_FMT\", \"fase\": \"gerando base\"}" > logs/current_state.json
                if ! $PYTHON gerar_videos.py --projeto "$PROJETO" --apenas "$NUMERO" --sem-download "${EXTRA_ARGS[@]}"; then
                    echo "  ✗ Falha ao gerar vídeo base para hino $NUMERO"
                    ERROS=$((ERROS + 1))
                    rm -f "$HINO_LOCK/pid" 2>/dev/null
                    rmdir "$HINO_LOCK" 2>/dev/null || true
                    _MY_LOCKS=("${_MY_LOCKS[@]/$HINO_LOCK}")
                    continue
                fi
            else
                echo "  ✓ Vídeo base já existe: $(basename $BASE_VIDEO)"
            fi
        fi

        # Verificar se o vídeo base existe e é válido antes de continuar
        if ! validar_video "$BASE_VIDEO"; then
            echo "  ✗ Vídeo base não encontrado ou corrompido: $BASE_VIDEO — Pulando."
            rm -f "$BASE_VIDEO" 2>/dev/null || true
            ERROS=$((ERROS + 1))
            rm -f "$HINO_LOCK/pid" 2>/dev/null
            rmdir "$HINO_LOCK" 2>/dev/null || true
            _MY_LOCKS=("${_MY_LOCKS[@]/$HINO_LOCK}")
            continue
        fi

        # ── 2. Embutir legendas ──
        echo "  ▶ Embutindo legendas..."
        echo "{\"projeto\": \"$PROJETO\", \"numero\": \"$NUM_FMT\", \"fase\": \"embutindo legendas\"}" > logs/current_state.json
        if $PYTHON gerar_legendas.py --projeto "$PROJETO" --numero "$NUMERO" "${EXTRA_ARGS[@]}"; then
            # Calcular ETA
            CURRENT_TIME=$(date +%s)
            ELAPSED=$((CURRENT_TIME - START_TIME))
            if [ $PROCESSADOS -gt 0 ]; then
                MEDIA=$((ELAPSED / PROCESSADOS))
                ETA_SEG=$((MEDIA * RESTANTES))
                ETA_MIN=$((ETA_SEG / 60))
                ETA_HOR=$((ETA_MIN / 60))
                ETA_MIN_REM=$((ETA_MIN % 60))
                echo "  ✓ Concluído | Média: ${MEDIA}s/hino | ETA: ${ETA_HOR}h${ETA_MIN_REM}m"
            fi
        else
            echo "  ✗ Falha ao embutir legenda para hino $NUMERO"
            ERROS=$((ERROS + 1))
        fi

        # Liberar lock deste hino
        rm -f "$HINO_LOCK/pid" 2>/dev/null
        rmdir "$HINO_LOCK" 2>/dev/null || true
        _MY_LOCKS=("${_MY_LOCKS[@]/$HINO_LOCK}")
    done 3< <(find "$INPUTS_DIR" -maxdepth 1 -name "*.json" ! -name "._*" -print0 | sort -z)

    echo ""
    echo "  ────────────────────────────────────────────────────────────"
    echo "  📊 Resumo do projeto '$PROJETO' (Fase 1 — Hinos):"
    echo "     Processados: $PROCESSADOS"
    echo "     Já existiam: $PULADOS"
    echo "     Erros:       $ERROS"
    echo "  ────────────────────────────────────────────────────────────"

    # ── Fase 1b: Verificar e retry hinos faltantes ──────────────────
    # Pular coros e meia_hora (não têm 480 hinos)
    if [ "$PROJETO" != "coros" ] && [ "$PROJETO" != "meia_hora" ]; then
        FALTANTES=$($PYTHON -c "
import sqlite3
conn = sqlite3.connect('progresso.db')
rows = conn.execute(\"SELECT numero FROM videos WHERE projeto=? AND status NOT IN ('concluido')\", ('$PROJETO',)).fetchall()
print(len(rows))
conn.close()
" 2>/dev/null || echo "0")

        if [ "$FALTANTES" -gt 0 ]; then
            echo ""
            echo "  🔄 $FALTANTES hino(s) não concluído(s) — tentando regerar..."
            echo "{\"projeto\": \"$PROJETO\", \"fase\": \"retry hinos faltantes\"}" > logs/current_state.json
            $PYTHON gerar_videos.py --projeto "$PROJETO" --sem-download "${EXTRA_ARGS[@]}" || {
                echo "  ⚠️  Falha no retry de hinos faltantes para '$PROJETO'."
            }

            # Rodar legendas nos que ficaram com base_pronto
            BASE_PRONTOS=$($PYTHON -c "
import sqlite3
conn = sqlite3.connect('progresso.db')
rows = conn.execute(\"SELECT numero FROM videos WHERE projeto=? AND status='base_pronto'\", ('$PROJETO',)).fetchall()
nums = [str(r[0]) for r in rows]
print(' '.join(nums))
conn.close()
" 2>/dev/null || echo "")

            if [ -n "$BASE_PRONTOS" ]; then
                for NUM_RETRY in $BASE_PRONTOS; do
                    HINO_LOCK="$LOCK_DIR/${PROJETO}-${NUM_RETRY}.lock"
                    if ! mkdir "$HINO_LOCK" 2>/dev/null; then
                        continue
                    fi
                    echo $$ > "$HINO_LOCK/pid"
                    _MY_LOCKS+=("$HINO_LOCK")

                    echo "  ▶ Retry legenda: hino $NUM_RETRY ($PROJETO)"
                    $PYTHON gerar_legendas.py --projeto "$PROJETO" --numero "$NUM_RETRY" "${EXTRA_ARGS[@]}" || {
                        echo "  ⚠️  Falha na legenda do hino $NUM_RETRY"
                    }

                    rm -f "$HINO_LOCK/pid" 2>/dev/null
                    rmdir "$HINO_LOCK" 2>/dev/null || true
                    _MY_LOCKS=("${_MY_LOCKS[@]/$HINO_LOCK}")
                done
            fi

            # Recontagem
            FALTANTES_FINAL=$($PYTHON -c "
import sqlite3
conn = sqlite3.connect('progresso.db')
rows = conn.execute(\"SELECT numero FROM videos WHERE projeto=? AND status NOT IN ('concluido')\", ('$PROJETO',)).fetchall()
print(len(rows))
conn.close()
" 2>/dev/null || echo "0")
            if [ "$FALTANTES_FINAL" -gt 0 ]; then
                echo "  ⚠️  Ainda faltam $FALTANTES_FINAL hino(s) após retry."
            else
                echo "  ✅ Todos os hinos concluídos após retry!"
            fi
        fi

        # ── Fase 2: Gerar coletâneas para este projeto ──────────────
        CONCLUIDOS=$($PYTHON -c "
import sqlite3
conn = sqlite3.connect('progresso.db')
r = conn.execute(\"SELECT COUNT(*) FROM videos WHERE projeto=? AND status='concluido' AND CAST(numero AS TEXT) NOT LIKE 'COL%'\", ('$PROJETO',)).fetchone()
print(r[0] if r else 0)
conn.close()
" 2>/dev/null || echo "0")

        if [ "$CONCLUIDOS" -gt 0 ]; then
            # Verificar quantas coletâneas já estão prontas (video + DB concluido)
            COLS_PRONTAS=$($PYTHON -c "
import sqlite3
conn = sqlite3.connect('progresso.db')
r = conn.execute(\"SELECT COUNT(*) FROM videos WHERE projeto=? AND status='concluido' AND CAST(numero AS TEXT) LIKE 'COL%'\", ('$PROJETO',)).fetchone()
print(r[0] if r else 0)
conn.close()
" 2>/dev/null || echo "0")

            TOTAL_COLS=23
            if [ "$COLS_PRONTAS" -ge "$TOTAL_COLS" ]; then
                echo "  ✅ Todas as $TOTAL_COLS coletâneas já concluídas para '$PROJETO' — pulando."
            else
                echo ""
                echo "  ┌──────────────────────────────────────────────────────────────────┐"
                echo "  │  📦 Coletâneas: $PROJETO ($COLS_PRONTAS/$TOTAL_COLS prontas, $CONCLUIDOS hinos)"
                echo "  └──────────────────────────────────────────────────────────────────┘"

                echo "{\"projeto\": \"$PROJETO\", \"fase\": \"gerando coletaneas\"}" > logs/current_state.json
                $PYTHON gerar_coletaneas.py --projeto "$PROJETO" "${EXTRA_ARGS[@]}" || {
                    echo "  ⚠️  Falha ao gerar coletâneas para o projeto '$PROJETO'."
                }
            fi
        else
            echo "  ⏭ Nenhum hino concluído em '$PROJETO' — pulando coletâneas."
        fi
    fi

done

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  ✅  Pipeline completo! Todos os projetos e coletâneas foram processados."
echo "══════════════════════════════════════════════════════════════════"

