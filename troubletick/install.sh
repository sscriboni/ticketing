#!/bin/bash
echo "Inizializzazione installazione di Troubletick..."

# Posizionati nella directory dello script
cd "$(dirname "$0")"

# Verifica se python3 è installato
if ! command -v python3 &> /dev/null; then
    echo "[ERRORE] python3 non trovato! Assicurati di averlo installato e che sia nel PATH."
    exit 1
fi

# Crea l'ambiente virtuale se non esiste
if [ ! -d "venv" ]; then
    echo "Creazione ambiente virtuale (venv)..."
    python3 -m venv venv
else
    echo "Ambiente virtuale (venv) già esistente."
fi

# Attiva l'ambiente virtuale
echo "Attivazione ambiente virtuale e installazione dipendenze..."
source venv/bin/activate
cd app
pip install -r requirements.txt

echo ""
echo "Installazione completata con successo! Ora puoi avviare il server eseguendo: ./start.sh"