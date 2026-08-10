# Troubletick PWA — PowerShell Script per avviare api.py con Uvicorn su porta 5002

$CurrentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $CurrentDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Avvio Troubletick FastAPI REST Backend su Porta 5002   " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Attivazione dell'ambiente virtuale se presente
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "[OK] Attivazione ambiente virtuale 'venv'..." -ForegroundColor Green
    & ".\venv\Scripts\Activate.ps1"
} elseif (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "[OK] Attivazione ambiente virtuale '.venv'..." -ForegroundColor Green
    & ".\.venv\Scripts\Activate.ps1"
} elseif (Test-Path "app\venv\Scripts\Activate.ps1") {
    Write-Host "[OK] Attivazione ambiente virtuale 'app\venv'..." -ForegroundColor Green
    & ".\app\venv\Scripts\Activate.ps1"
} else {
    Write-Host "[INFO] Nessun venv rilevato, utilizzo Python di sistema..." -ForegroundColor Gray
}

Write-Host "`n==========================================================" -ForegroundColor DarkCyan
Write-Host "  API Server:        http://127.0.0.1:5002" -ForegroundColor White
Write-Host "  API Docs Swagger:  http://127.0.0.1:5002/docs" -ForegroundColor White
Write-Host "  API Redoc:         http://127.0.0.1:5002/redoc" -ForegroundColor White
Write-Host "  Automezzi API:     http://127.0.0.1:5002/api/automezzi" -ForegroundColor White
Write-Host "  Prenotazioni API:  http://127.0.0.1:5002/api/prenotazioni" -ForegroundColor White
Write-Host "==========================================================`n" -ForegroundColor DarkCyan
Write-Host "Premere CTRL+C per arrestare il server.`n" -ForegroundColor Yellow

# 2. Avvio Uvicorn con auto-reload sulla porta 5002
python -m uvicorn app.api:app --host 0.0.0.0 --port 5002 --reload
