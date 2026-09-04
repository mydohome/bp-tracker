#!/usr/bin/env bash
# apply-update.sh — Applica un aggiornamento scaricato da Claude (file zip)
# al repository locale, mostra cosa è cambiato, fa commit e push su GitHub.
#
# Si ferma volutamente PRIMA di ricostruire i container: quello resta un
# passo separato e consapevole (./update.sh oppure docker compose up -d
# --build), da fare dopo aver controllato che il push sia andato a buon
# fine — così non si rischia di far ripartire l'app con un push a metà o
# fallito.
#
# Uso:
#   ./apply-update.sh [percorso-zip] ["messaggio di commit"]
#
# Se non specifichi il percorso dello zip, cerca automaticamente lo zip
# più recente scaricato in ~/Downloads che inizia con "payslip-app".
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# --- 1. Individua il file zip ---
if [ -n "${1:-}" ]; then
    ZIP_PATH="$1"
else
    ZIP_PATH="$(ls -t "$HOME"/Downloads/payslip-app*.zip 2>/dev/null | head -n1 || true)"
fi

if [ -z "${ZIP_PATH:-}" ] || [ ! -f "$ZIP_PATH" ]; then
    echo "❌ Nessuno zip trovato."
    echo "   Uso: ./apply-update.sh [percorso-zip] [\"messaggio di commit\"]"
    echo "   (senza argomenti, cerco il più recente payslip-app*.zip in ~/Downloads)"
    exit 1
fi

COMMIT_MSG="${2:-Aggiornamento $(date '+%Y-%m-%d %H:%M')}"

echo "=== Applica aggiornamento ==="
echo "Repo:  $REPO_DIR"
echo "Zip:   $ZIP_PATH"
echo ""

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "❌ Questa cartella non è un repository Git."
    exit 1
fi

# --- 2. Estrai lo zip in una cartella temporanea ---
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
unzip -oq "$ZIP_PATH" -d "$TMP_DIR"

SRC_DIR="$TMP_DIR/payslip-app"
if [ ! -d "$SRC_DIR" ]; then
    SRC_DIR="$TMP_DIR"  # fallback se lo zip non ha la sottocartella
fi

# --- 3. Non sovrascrivere file con modifiche locali non committate ---
# (tipicamente docker-compose.yml, se hai personalizzato la porta)
EXCLUDES=(--exclude='.git' --exclude='.env')
for f in docker-compose.yml; do
    if [ -f "$f" ] && ! git diff --quiet -- "$f" 2>/dev/null; then
        echo "⚠️  $f ha modifiche locali non committate: non lo sovrascrivo."
        echo "    Confrontalo manualmente, se vuoi: diff $f \"$SRC_DIR/$f\""
        EXCLUDES+=(--exclude="$f")
    fi
done

# --- 4. Sincronizza i file ---
rsync -a "${EXCLUDES[@]}" "$SRC_DIR/" "$REPO_DIR/"

# --- 5. Mostra cosa è cambiato ---
echo ""
echo "📋 Modifiche rilevate:"
git status --short

if [ -z "$(git status --porcelain)" ]; then
    echo ""
    echo "✅ Nessuna modifica da applicare: repository già aggiornato."
    exit 0
fi

# --- 6. Commit e push ---
git add -A
git commit -m "$COMMIT_MSG"
git push

echo ""
echo "✅ Push completato su GitHub."
echo "   Ora esegui './update.sh' (oppure 'docker compose up -d --build')"
echo "   per applicare le modifiche ai container in esecuzione."
