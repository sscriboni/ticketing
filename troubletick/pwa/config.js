/**
 * Troubletick PWA — Configurazione Percorsi Relativi
 * Questo file permette di configurare la WebApp per funzionare su qualsiasi sotto-cartella o dominio
 * tramite percorsi relativi.
 */
window.PWA_CONFIG = (function() {
  // Calcolo dinamico del percorso relativo di base della pagina corrente
  const currentPath = window.location.pathname;
  const baseFolder = currentPath.substring(0, currentPath.lastIndexOf('/') + 1) || './';

  return {
    // Percorso relativo di base per asset e risorse
    basePath: './',

    // URL base per le chiamate API REST (può essere un percorso relativo './api' o un URL completo)
    apiBaseUrl: window.PWA_CUSTOM_API_URL || (window.location.origin + baseFolder.replace(/\/$/, '') + '/api'),

    // URL di fallback API locale se il backend è su porta separata (es. 8000)
    apiFallbackUrl: 'http://localhost:8000/api',

    // Abilita la modalità percorsi relativi puri per PWA
    useRelativePaths: true
  };
})();
