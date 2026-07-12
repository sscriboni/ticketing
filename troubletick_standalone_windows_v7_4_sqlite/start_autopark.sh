#!/bin/bash
echo "Avvio di Autopark Webapp (Porta 5002)..."

cd "$(dirname "$0")"

# Verifica l'esistenza dell'ambiente virtuale
if [ ! -f "venv/bin/activate" ]; then
    echo "[ERRORE] Ambiente virtuale (venv) non trovato! Assicurati di aver eseguito ./install.sh prima di avviare il server."
    exit 1
fi

# Attiva l'ambiente virtuale, posizionati in app/ e avvia la webapp Autopark
source venv/bin/activate
cd app
uvicorn appautopark:app --host 0.0.0.0 --port 5002
