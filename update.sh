#!/usr/bin/env bash
# update.sh — Aggiorna Payslip Tracker con le ultime modifiche dal repository Git
# e ricostruisce/riavvia i container interessati.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Payslip Tracker — aggiornamento ==="

if [ ! -d ".git" ]; then
    echo "❌ Questa cartella non è un repository Git."
    echo "   Clonalo con: git clone <url-del-tuo-repo> payslip-app"
    exit 1
fi

# 1. Salva eventuali modifiche locali non committate (.env non è tracciato, resta intatto)
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "📍 Branch corrente: $BRANCH"

if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Ci sono modifiche locali non committate:"
    git status --short
    read -rp "Vuoi metterle da parte con 'git stash' e continuare? [s/N] " CONFIRM
    if [[ "$CONFIRM" =~ ^[sS]$ ]]; then
        git stash push -m "auto-stash prima di update.sh $(date '+%Y-%m-%d %H:%M:%S')"
        STASHED=1
    else
        echo "❌ Aggiornamento annullato per evitare di perdere modifiche locali."
        exit 1
    fi
fi

# 2. Scarica le modifiche dal repository remoto
echo ""
echo "⬇️  Scarico gli aggiornamenti da origin/$BRANCH..."
git fetch origin

LOCAL_HASH="$(git rev-parse HEAD)"
REMOTE_HASH="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL_HASH" == "$REMOTE_HASH" ]; then
    echo "✅ Sei già alla versione più recente. Nessun aggiornamento necessario."
    exit 0
fi

echo "📥 Trovate nuove modifiche, aggiorno..."
git pull --ff-only origin "$BRANCH"

if [ "${STASHED:-0}" == "1" ]; then
    echo "🔄 Riapplico le modifiche locali messe da parte..."
    git stash pop || echo "⚠️  Conflitto durante il ripristino dello stash: risolvilo manualmente con 'git stash list' / 'git stash pop'."
fi

# 3. Ricostruisce e riavvia solo ciò che è cambiato
echo ""
echo "🔧 Ricostruzione immagini e riavvio dei container..."
docker compose up -d --build

echo ""
echo "🧹 Pulizia immagini Docker inutilizzate..."
docker image prune -f

echo ""
echo "✅ Aggiornamento completato (da ${LOCAL_HASH:0:7} a ${REMOTE_HASH:0:7})."
docker compose ps
