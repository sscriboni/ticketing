#!/bin/bash
echo "Avvio di Troubletick..."

cd "$(dirname "$0")"

# Verifica l'esistenza dell'ambiente virtuale
if [ ! -f "venv/bin/activate" ]; then
    echo "[ERRORE] Ambiente virtuale (venv) non trovato! Assicurati di aver eseguito ./install.sh prima di avviare il server."
    exit 1
fi

# Verifica se l'ambiente virtuale è valido dopo un eventuale cambio cartella
venv/bin/python3 -c "import sys" &> /dev/null
if [ $? -ne 0 ]; then
    echo "[AVVISO] La cartella del progetto è stata spostata o rinominata."
    echo "Ricreazione dell'ambiente virtuale (venv) in corso..."
    python3 -m venv --clear venv
    source venv/bin/activate
    pip install -r app/requirements.txt
else
    source venv/bin/activate
fi

cd app
uvicorn main:app --host 0.0.0.0 --port 5001 --root-path /ticketing