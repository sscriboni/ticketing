# Troubletick PWA — Ionic Single Page Application (SPA)

Scheletro completo per l'applicazione Web **PWA (Progressive Web App)** sviluppata in architettura **Single Page Application (SPA)** con il framework **Ionic Framework v7**, interamente **configurata per utilizzare percorsi relativi**.

## 📁 Struttura della Directory `/pwa`

```
troubletick/pwa/
├── index.html                   # Shell HTML dell'applicazione SPA con le viste Login e Home Page
├── config.js                    # Configurazione dinamica per percorsi relativi e base URL API
├── app.js                       # Controller JavaScript SPA (navigazione, autenticazione, API)
├── style.css                    # Personalizzazioni grafiche CSS ed Ionic
├── manifest.json                # Manifest PWA configurato con start_url e scope relativi ("./")
├── sw.js                        # Service Worker con cache asset a percorsi relativi ("./")
└── backend/
    ├── api.py                   # Server API Python FastAPI (Login, User Profile, Dashboard Stats)
    ├── start_backend.py         # Script Python per avviare il server API su http://localhost:8000
    └── requirements.txt         # Dipendenze Python del backend API
```

## 🔗 Configurazione Percorsi Relativi (`config.js`)

La WebApp PWA è progettata per poter essere ospitata in **qualsiasi sotto-cartella** (es. `http://dominio.com/pwa/`, `http://localhost:5001/pwa/` o la radice del server `/`):
- **Asset e risorse**: Collegati con prefisso relativo (`./style.css`, `./app.js`, `./config.js`, `./manifest.json`).
- **Service Worker**: Registrato tramite `./sw.js` per supportare qualsiasi percorso di pubblicazione.
- **API Endpoint**: Calcolato dinamicamente tramite `window.PWA_CONFIG.apiBaseUrl` (con fallback su `http://localhost:8000/api` per lo sviluppo locale).

## 🚀 Avvio dei Servizi

### 1. Avvio del Server Backend API (Python)
Dalla cartella principale o da `pwa/backend`:
```bash
python pwa/backend/start_backend.py
```
Il server API sarà in ascolto su: **`http://localhost:8000/api`**
Documentazione interattiva Swagger: **`http://localhost:8000/docs`**

### 2. Fruizione della WebApp PWA (Frontend Ionic SPA)
Aprire il file `pwa/index.html` nel browser oppure servirlo tramite qualsiasi web server HTTP o sotto-percorso relativo.
