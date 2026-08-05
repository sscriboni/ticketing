# Troubletick PWA — React & Tailwind CSS Skeleton

Questo progetto contiene lo scheletro completo di una **Progressive Web App (PWA)** sviluppata con **React**, **Tailwind CSS** e **Vite**.

## 📁 Struttura del Progetto

```
troubletick/pwa/
├── index.html                   # Entry point HTML con configurazione PWA, meta tag e font
├── package.json                 # Dipendenze React, Tailwind, Vite e script npm
├── vite.config.js               # Configurazione Vite (porta 5003)
├── tailwind.config.js           # Configurazione palette e temi Tailwind CSS
├── postcss.config.js            # Configurazione PostCSS
├── public/
│   ├── manifest.json            # Manifest PWA (colori, icone, modalità standalone)
│   └── sw.js                    # Service Worker per la gestione della cache offline
└── src/
    ├── main.jsx                 # Bootstrapping React
    ├── App.jsx                  # Componente UI principale con dashboard, PWA install banner ed indicatore online/offline
    ├── index.css                # Importazioni direttive Tailwind CSS
    └── registerServiceWorker.js # Registrazione del Service Worker PWA
```

## 🚀 Avvio del Progetto

### Prerequisiti
Assicurarsi di avere **Node.js** (v18+) ed **npm** installati.

### 1. Installazione Dipendenze
```bash
cd pwa
npm install
```

### 2. Avvio del Server di Sviluppo
```bash
npm run dev
```
La Webapp PWA sarà accessibile all'indirizzo: `http://localhost:5003`

### 3. Build di Produzione PWA
```bash
npm run build
```
I file ottimizzati per il rilascio in produzione verranno generati nella cartella `dist/`.
