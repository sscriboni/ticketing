# Troubletick PWA — Ionic Single Page Application (SPA)

Scheletro completo per l'applicazione Web **PWA (Progressive Web App)** sviluppata in architettura **Single Page Application (SPA)** con il framework **Ionic Framework v7**.

## 📁 Struttura della Directory `/pwa`

```
troubletick/pwa/
├── index.html                   # Shell HTML dell'applicazione SPA con le viste Login e Home Page
├── app.js                       # Controller JavaScript SPA (navigazione, autenticazione, API)
├── style.css                    # Personalizzazioni grafiche CSS ed Ionic
├── manifest.json                # Manifest PWA per l'installazione nativa mobile
├── sw.js                        # Service Worker per la gestione della cache offline
└── backend/
    ├── api.py                   # Server API Python FastAPI (Login, User Profile, Dashboard Stats)
    ├── start_backend.py         # Script Python per avviare il server API su http://localhost:8000
    └── requirements.txt         # Dipendenze Python del backend API
```

## 📱 Caratteristiche della Single Page Application (SPA)

- **Ionic Framework v7**: Web Components ed Ionicons tramite CDN per la resa nativa su iOS ed Android.
- **Pagina di Login (`page-login`)**: Form interattivo con input Ionic, checkbox "Ricordami", gestione degli errori ed integrazione API REST `POST /api/login`.
- **Home Page (`page-home`)**: Dashboard con header Ionic, badge del ruolo utente, KPI in tempo reale (ticket aperti, veicoli in flotta, presenze), schede servizi per Carpooling, Helpdesk e Presenze, e pulsante di Logout `POST /api/logout`.
- **Integrazione Backend API Python**: Comunicazione asincrona `fetch()` verso le API REST Python in `/backend/api.py`.
- **PWA Ready**: Manifest PWA e Service Worker per il funzionamento offline.

## 🚀 Avvio dei Servizi

### 1. Avvio del Server Backend API (Python)
Dalla cartella principale o da `pwa/backend`:
```bash
python pwa/backend/start_backend.py
```
Il server API sarà in ascolto su: **`http://localhost:8000/api`**
Documentazione interattiva Swagger: **`http://localhost:8000/docs`**

### 2. Fruizione della WebApp PWA (Frontend Ionic SPA)
Aprire il file `pwa/index.html` nel browser oppure servirlo tramite qualsiasi web server HTTP.
