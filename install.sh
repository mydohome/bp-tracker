#!/usr/bin/env bash
# install.sh — Installazione automatica di Payslip Tracker
# Presuppone Docker + Docker Compose già installati e funzionanti.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Payslip Tracker — installazione ==="

# 1. Verifica prerequisiti
if ! command -v docker &> /dev/null; then
    echo "❌ Docker non trovato. Installalo prima di continuare: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Il plugin 'docker compose' non è disponibile (serve Docker Compose v2)."
    exit 1
fi
echo "✅ Docker e Docker Compose trovati."

# 2. Configurazione .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "📝 Creato file .env da .env.example."
    echo ""
    echo "⚠️  Devi inserire la tua ANTHROPIC_API_KEY prima di continuare."
    read -rp "Incolla qui la tua Anthropic API key (sk-ant-...): " API_KEY
    if [ -n "$API_KEY" ]; then
        # Sostituisce la riga ANTHROPIC_API_KEY nel file .env
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${API_KEY}|" .env
        else
            sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${API_KEY}|" .env
        fi
        echo "✅ Chiave salvata in .env."
    else
        echo "⚠️  Nessuna chiave inserita: dovrai modificare manualmente .env prima di usare l'app."
    fi
else
    echo "ℹ️  File .env già presente, non lo sovrascrivo."
fi

# 3. Build e avvio
echo ""
echo "🚀 Costruzione e avvio dei container..."
docker compose up -d --build

echo ""
echo "⏳ Attendo che i servizi siano pronti..."
sleep 5
docker compose ps

echo ""
echo "✅ Installazione completata."
echo "   Frontend: http://localhost:8080"
echo "   Backend API docs: http://localhost:8000/docs"
echo ""
echo "Per vedere i log:      docker compose logs -f"
echo "Per fermare l'app:     docker compose down"
