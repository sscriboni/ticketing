/**
 * Troubletick PWA — Configurazione Percorsi Relativi
 * Definizione esclusiva del percorso relativo per asset ed API REST.
 */
window.PWA_CONFIG = (function() {
  return {
    // Percorso relativo di base per asset e risorse
    basePath: './',

    // Percorso relativo esclusivo per le API REST
    apiBaseUrl: window.PWA_CUSTOM_API_URL || './api',

    // Modalità percorsi relativi puri abilitata
    useRelativePaths: true
  };
})();
