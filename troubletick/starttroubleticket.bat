@echo off
cd /d "%~dp0"
echo Inizializzazione di Troubletick (Porta 5001)...

REM Se la cartella venv esiste ma e' incompleta o corrotta, tenta la rimozione
if exist "venv" if not exist "venv\Scripts\activate.bat" (
    echo Pulizia vecchia cartella venv...
    rmdir /s /q "venv" 2>nul
)

REM Verifica l'esistenza dell'ambiente virtuale
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
        echo  1. Metti in pausa la sincronizzazione di Google Drive (oppure attendi qualche secondo che termini la sincronizzazione).
        echo  2. Elimina manualmente la cartella 'venv' in Esplora Risorse.
        echo  3. Riavvia questo script.
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
    REM Test se l'ambiente virtuale e' valido (es. se la cartella e' stata spostata/rinominata)
    venv\Scripts\python.exe -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [AVVISO] La cartella del progetto e' stata spostata o rinominata.
        echo Ricreazione dell'ambiente virtuale in corso...
        python -m venv --clear venv
        if errorlevel 1 (
            rmdir /s /q "venv" 2>nul
            python -m venv venv
        )
        call venv\Scripts\activate.bat
        pip install -r app\requirements.txt
    ) else (
        call venv\Scripts\activate.bat
    )
)

REM Posizionati nella cartella app e avvia il server principale
cd app
uvicorn main:app --host 0.0.0.0 --port 5001
pause
