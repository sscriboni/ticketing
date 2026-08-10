@echo off
title Troubletick - PWA API Backend (Porta 5002)
cd /d "%~dp0"

echo ==========================================================
echo   Avvio Troubletick FastAPI REST Backend su Porta 5002
echo ==========================================================
echo.

:: 1. Attivazione dell'ambiente virtuale se presente (venv o .venv)
if exist "venv\Scripts\activate.bat" (
    echo [OK] Attivazione ambiente virtuale 'venv'...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo [OK] Attivazione ambiente virtuale '.venv'...
    call .venv\Scripts\activate.bat
) else if exist "app\venv\Scripts\activate.bat" (
    echo [OK] Attivazione ambiente virtuale 'app\venv'...
    call app\venv\Scripts\activate.bat
) else (
    echo [INFO] Nessun venv rilevato, utilizzo Python di sistema...
)

echo.
echo ==========================================================
echo   API Server:        http://127.0.0.1:5002
echo   API Docs Swagger:  http://127.0.0.1:5002/docs
echo   API Redoc:         http://127.0.0.1:5002/redoc
echo   Automezzi API:     http://127.0.0.1:5002/api/automezzi
echo   Prenotazioni API:  http://127.0.0.1:5002/api/prenotazioni
echo ==========================================================
echo.
echo Premere CTRL+C per arrestare il server in qualsiasi momento.
echo.

:: 2. Avvio Uvicorn con auto-reload sulla porta 5002
python -m uvicorn app.api:app --host 0.0.0.0 --port 5002 --reload

if errorlevel 1 (
    echo.
    echo [ATTENZIONE] Avvio con 'python -m uvicorn' fallito, tentativo con comando 'uvicorn'...
    uvicorn app.api:app --host 0.0.0.0 --port 5002 --reload
)

pause
