@echo off
echo Inizializzazione e avvio di Autopark Webapp (Porta 5002)...

REM Verifica l'esistenza dell'ambiente virtuale
if not exist "venv\Scripts\activate.bat" (
    echo Creazione dell'ambiente virtuale in corso...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRORE] Impossibile creare l'ambiente virtuale. Assicurati che Python sia installato e nel PATH.
        pause
        exit /b 1
    )
    echo Ambiente virtuale creato.
    echo Installazione delle dipendenze in corso...
    call venv\Scripts\activate.bat
    pip install -r app\requirements.txt
    if errorlevel 1 (
        echo [ERRORE] Installazione delle dipendenze fallita.
        pause
        exit /b 1
    )
    echo Dipendenze installate con successo!
) else (
    REM Attiva l'ambiente virtuale
    call venv\Scripts\activate.bat
)

REM Posizionati nella cartella app e avvia la webapp Autopark
cd app
uvicorn appautopark:app --host 0.0.0.0 --port 5002
pause
