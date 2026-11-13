#!/bin/bash
cd "$(dirname "$0")"

# Attivazione virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "[ERRORE] Ambiente virtuale non trovato. Esegui prima ./install.sh"
    exit 1
fi

cd app
echo "Avvio di Troubletick sulla porta 5001..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 5001

