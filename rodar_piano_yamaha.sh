#!/usr/bin/env bash
# =============================================================================
# rodar_piano_yamaha.sh — Execução completa do projeto "Hinos em Piano Yamaha"
#
# Uso:
#   ./rodar_piano_yamaha.sh              # processa tudo pendente + coletâneas
#   ./rodar_piano_yamaha.sh --forcar     # força regeração de coletâneas já existentes
# =============================================================================

set -e
cd "$(dirname "$0")"

PROJETO="piano_yamaha"
PYTHON="${PYTHON:-python3}"

echo "============================================================"
echo "  Projeto: Hinos em Piano Yamaha"
echo "  Vinheta: vinheta/vinheta-hinario-04-v1.mp4"
echo "============================================================"

# 1. Gerar vídeos individuais (hinos + coros)
echo ""
echo "▶ Etapa 1/2 — Gerando vídeos individuais..."
$PYTHON gerar_videos.py --projeto $PROJETO --sem-download

# 2. Gerar coletâneas (concatenação sem vinheta — já incluída em cada vídeo)
echo ""
echo "▶ Etapa 2/2 — Gerando coletâneas..."
if [[ "$1" == "--forcar" ]]; then
    $PYTHON gerar_coletaneas.py --projeto $PROJETO --forcar
else
    $PYTHON gerar_coletaneas.py --projeto $PROJETO
fi

echo ""
echo "✅  Projeto '$PROJETO' concluído!"
