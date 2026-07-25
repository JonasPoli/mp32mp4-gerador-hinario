#!/usr/bin/env bash
# =============================================================================
# adicionar_legendas_batch.sh — Adiciona legendas em vídeos base já gerados
#
# Uso para brass e string (padrão):
#   ./adicionar_legendas_batch.sh \
#     --preset-ffmpeg veryfast \
#     --threads-ffmpeg 1 \
#     --low-priority \
#     --pausa-ffmpeg 1.5 \
#     --pausa-entre-hinos 10.0
#
# Uso para projetos específicos:
#   ./adicionar_legendas_batch.sh --projetos "brass string palhetas" \
#     --preset-ffmpeg veryfast --threads-ffmpeg 1 --low-priority
#
# Este script NÃO re-gera vídeos base. Apenas embute legendas nos vídeos
# que já existem mas estão sem legenda (status != concluido no banco).
# =============================================================================

set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

# Projetos padrão a processar (somente os que sabemos ter problemas)
PROJETOS_DEFAULT="brass string"
PROJETOS=""
EXTRA_ARGS=()
PAUSA_ENTRE_HINOS=0.0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --projetos)
            PROJETOS="$2"
            shift 2
            ;;
        --pausa-entre-hinos)
            PAUSA_ENTRE_HINOS="$2"
            EXTRA_ARGS+=("$1" "$2")
            shift 2
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

if [ -z "$PROJETOS" ]; then
    PROJETOS="$PROJETOS_DEFAULT"
fi

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  📝  Adicionando legendas em vídeos existentes"
echo "══════════════════════════════════════════════════════════════════"
echo "  Projetos: $PROJETOS"
echo "══════════════════════════════════════════════════════════════════"
echo ""

# ── Coordenação com outros scripts (lock por hino) ────────────────────────────
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

release_my_locks() {
    for _lk in "${_MY_LOCKS[@]}"; do
        rm -f "$_lk/pid" 2>/dev/null
        rmdir "$_lk" 2>/dev/null || true
    done
}
trap release_my_locks EXIT INT TERM

# ── 1. Processar cada projeto ─────────────────────────────────────────────────
TOTAL_GERAL=0
ERROS_GERAL=0
START_GLOBAL=$(date +%s)

for PROJETO in $PROJETOS; do
    echo "┌──────────────────────────────────────────────────────────────────┐"
    echo "│  Projeto: $PROJETO"
    echo "└──────────────────────────────────────────────────────────────────┘"

    INPUTS_DIR="projects/$PROJETO/inputs"
    if [ ! -d "$INPUTS_DIR" ]; then
        echo "  ⚠️  Diretório de inputs não encontrado: $INPUTS_DIR — Pulando."
        continue
    fi

    OUTPUT_PROJ="output/$PROJETO"
    mkdir -p "$OUTPUT_PROJ"

    TOTAL_JSON=$(find "$INPUTS_DIR" -maxdepth 1 -name "*.json" ! -name "._*" | wc -l | tr -d ' ')
    echo "  📄 Total de JSONs de legenda: $TOTAL_JSON"

    PROCESSADOS=0
    PULADOS=0
    ERROS=0
    START_TIME=$(date +%s)

    while IFS= read -u 3 -r -d '' JSON_FILE; do
        JSON_NAME=$(basename "$JSON_FILE")

        # Extrair número do hino do nome do arquivo
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
            continue
        fi

        if [[ "$NUMERO" =~ ^C([0-9]+)$ ]]; then
            NUM_FMT="C$(printf "%03d" "${BASH_REMATCH[1]}")"
        else
            NUM_FMT=$(printf "%03d" "$NUMERO")
        fi

        BASE_VIDEO="$OUTPUT_PROJ/hino-$PROJETO-$NUM_FMT.mp4"

        # Verificar status no banco
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

        # Pular se já está concluído (com legendas)
        if [ "$STATUS" = "concluido" ] && [ -f "$BASE_VIDEO" ]; then
            PULADOS=$((PULADOS + 1))
            continue
        fi

        # Pular se o vídeo base não existe (nada a legendar)
        if [ ! -f "$BASE_VIDEO" ]; then
            continue
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
        RESTANTES=$((TOTAL_JSON - PROCESSADOS - PULADOS))

        echo ""
        echo "  ──────────────────────────────────────────────────────────"
        echo "  [$PROCESSADOS] Hino $NUM_FMT ($PROJETO) — Restantes: ~$RESTANTES"

        # Embutir legendas
        echo "  ▶ Embutindo legendas..."
        if $PYTHON gerar_legendas.py --projeto "$PROJETO" --numero "$NUMERO" "${EXTRA_ARGS[@]}"; then
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

        # Pausa entre hinos para resfriamento
        if (( $(echo "$PAUSA_ENTRE_HINOS > 0" | bc -l 2>/dev/null || echo 0) )); then
            sleep "$PAUSA_ENTRE_HINOS"
        fi
    done 3< <(find "$INPUTS_DIR" -maxdepth 1 -name "*.json" ! -name "._*" -print0 | sort -z)

    TOTAL_GERAL=$((TOTAL_GERAL + PROCESSADOS))
    ERROS_GERAL=$((ERROS_GERAL + ERROS))

    echo ""
    echo "  ────────────────────────────────────────────────────────────"
    echo "  📊 Resumo do projeto '$PROJETO':"
    echo "     Legendados: $PROCESSADOS"
    echo "     Já tinham:  $PULADOS"
    echo "     Erros:      $ERROS"
    echo "  ────────────────────────────────────────────────────────────"
done

END_GLOBAL=$(date +%s)
ELAPSED_GLOBAL=$((END_GLOBAL - START_GLOBAL))
ELAPSED_MIN=$((ELAPSED_GLOBAL / 60))
ELAPSED_HOR=$((ELAPSED_MIN / 60))
ELAPSED_MIN_REM=$((ELAPSED_MIN % 60))

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  ✅  Legendas adicionadas!"
echo "     Total processados: $TOTAL_GERAL"
echo "     Erros:             $ERROS_GERAL"
echo "     Tempo total:       ${ELAPSED_HOR}h${ELAPSED_MIN_REM}m"
echo "══════════════════════════════════════════════════════════════════"
