#!/bin/bash
echo "Avvio di Troubletick..."

cd "$(dirname "$0")"

# Verifica l'esistenza dell'ambiente virtuale
if [ ! -f "venv/bin/activate" ]; then
    echo "[ERRORE] Ambiente virtuale (venv) non trovato! Assicurati di aver eseguito ./install.sh prima di avviare il server."
    exit 1
fi

# Attiva l'ambiente virtuale, posizionati in app/ e avvia il server
source venv/bin/activate
cd app
uvicorn main:app --host 0.0.0.0 --port 5001 --root-path /ticketing