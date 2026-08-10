// ============================================================================
// TROUBLETICK PWA — NUMERO DI VERSIONE CENTRALIZZATO
// Modifica ESCLUSIVAMENTE questo valore per aggiornare tutta l'applicazione,
// invalidare le vecchie cache e forzare il download del nuovo codice sui client.
// ============================================================================
const APP_VERSION = '1.3.1';

// Condivisione della versione sia nel browser (window) che nel Service Worker (self)
if (typeof self !== 'undefined') {
  self.APP_VERSION = APP_VERSION;
}
if (typeof window !== 'undefined') {
  window.APP_VERSION = APP_VERSION;
}
