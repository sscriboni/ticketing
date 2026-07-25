@echo off
cd /d "%~dp0"
echo Inizializzazione e avvio di Troubletick (Porta 5001)...

if exist "venv" (
    if not exist "venv\Scripts\activate.bat" (
        echo Pulizia vecchia cartella venv...
        rmdir /s /q "venv" 2>nul
    )
)

if not exist "venv\Scripts\activate.bat" (
    echo Creazione dell'ambiente virtuale in corso...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo [ERRORE DI PERMESSI / FILE IN USO]
        echo Impossibile creare l'ambiente virtuale in 'venv'.
        echo Motivo: Un processo Python attivo o la sincronizzazione di Google Drive sta bloccando alcuni file della cartella venv.
        echo.
        echo SUGGERIMENTO PER RISOLVERE:
        echo  - Metti in pausa la sincronizzazione di Google Drive.
        echo  - Elimina manualmente la cartella venv in Esplora Risorse.
        echo  - Riavvia questo script.
        echo.
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
    call venv\Scripts\activate.bat
)

cd app
uvicorn main:app --host 0.0.0.0 --port 5001
pause
