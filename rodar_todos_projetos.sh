#!/usr/bin/env bash
# =============================================================================
# rodar_todos_projetos.sh — Gera vídeos base + legendados para múltiplos
# projetos do Hinário CCB, em sequência.
#
# Cada projeto é processado completamente antes de passar ao próximo.
# Se interrompido, basta rodar novamente — continua de onde parou.
#
# Uso:
#   ./rodar_todos_projetos.sh              # processa todos os projetos pendentes
#   ./rodar_todos_projetos.sh --pular-base # só gera legendados (pula vídeo base)
# =============================================================================

set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
PULAR_BASE="${1:-}"

# Projetos a processar (na ordem solicitada)
PROJETOS=(
    "hinos_de_ninar"
    "piano_yamaha"
    "brass"
    "string"
    "palhetas"
    "sopro"
    "orquestra"
    "meia_hora"
)

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

    # Verificar se o diretório de inputs existe
    INPUTS_DIR="projects/$PROJETO/inputs"
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

    for JSON_FILE in $(find "$INPUTS_DIR" -maxdepth 1 -name "*.json" ! -name "._*" | sort); do
        JSON_NAME=$(basename "$JSON_FILE")

        # Extrair número do hino do nome do arquivo
        # Suporta: hino_001.json, 001.json, 001- Nome.json
        NUMERO=""
        if [[ "$JSON_NAME" =~ ^hino_([0-9]+)\.json$ ]]; then
            NUMERO=$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')
        elif [[ "$JSON_NAME" =~ ^([0-9]+)\.json$ ]]; then
            NUMERO=$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')
        elif [[ "$JSON_NAME" =~ ^([0-9]+)[-\ ] ]]; then
            NUMERO=$(echo "${BASH_REMATCH[1]}" | sed 's/^0*//')
        fi

        if [ -z "$NUMERO" ]; then
            echo "  [aviso] Não foi possível extrair número de: $JSON_NAME — Pulando."
            continue
        fi

        NUM_FMT=$(printf "%03d" "$NUMERO")

        # O nome padronizado do legendado é hino-{projeto}-{NNN}.mp4
        LEGENDADO="$OUTPUT_PROJ/hino-$PROJETO-$NUM_FMT.mp4"
        BASE_VIDEO="$OUTPUT_PROJ/hino-$PROJETO-$NUM_FMT.mp4"

        # Verificar no banco de dados se o hino já foi concluído (com legendas)
        STATUS=$($PYTHON -c "
import sqlite3
conn = sqlite3.connect('progresso.db')
r = conn.execute('SELECT status FROM videos WHERE projeto=? AND numero=?', ('$PROJETO', $NUMERO)).fetchone()
print(r[0] if r else 'pendente')
conn.close()
" 2>/dev/null || echo "pendente")

        if [ "$STATUS" = "concluido" ] && [ -f "$LEGENDADO" ]; then
            PULADOS=$((PULADOS + 1))
            continue
        fi

        PROCESSADOS=$((PROCESSADOS + 1))
        RESTANTES=$((TOTAL_JSON - PROCESSADOS - PULADOS - ERROS))

        echo ""
        echo "  ──────────────────────────────────────────────────────────"
        echo "  [$PROCESSADOS] Hino $NUM_FMT ($PROJETO) — Restantes: ~$RESTANTES"

        # ── 1. Gerar vídeo base (se não existe e não foi pedido para pular) ──
        if [ "$PULAR_BASE" != "--pular-base" ]; then
            if [ ! -f "$BASE_VIDEO" ]; then
                echo "  ▶ Gerando vídeo base..."
                if ! $PYTHON gerar_videos.py --projeto "$PROJETO" --apenas "$NUMERO" --sem-download; then
                    echo "  ✗ Falha ao gerar vídeo base para hino $NUMERO"
                    ERROS=$((ERROS + 1))
                    continue
                fi
            else
                echo "  ✓ Vídeo base já existe: $(basename $BASE_VIDEO)"
            fi
        fi

        # Verificar se o vídeo base existe antes de continuar
        if [ ! -f "$BASE_VIDEO" ]; then
            echo "  ✗ Vídeo base não encontrado: $BASE_VIDEO — Pulando."
            ERROS=$((ERROS + 1))
            continue
        fi

        # ── 2. Embutir legendas ──
        echo "  ▶ Embutindo legendas..."
        if $PYTHON gerar_legendas.py --projeto "$PROJETO" --numero "$NUMERO"; then
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
    done

    echo ""
    echo "  ────────────────────────────────────────────────────────────"
    echo "  📊 Resumo do projeto '$PROJETO':"
    echo "     Processados: $PROCESSADOS"
    echo "     Já existiam: $PULADOS"
    echo "     Erros:       $ERROS"
    echo "  ────────────────────────────────────────────────────────────"
done

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  ✅  Pipeline completo! Todos os projetos foram processados."
echo "══════════════════════════════════════════════════════════════════"
