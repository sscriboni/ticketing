// Troubletick PWA — Ionic SPA Controller (Configurazione Percorsi Relativi)

// Calcolo Dinamico dell'URL API dal Config Relativo (window.PWA_CONFIG)
function getApiBaseUrl() {
  if (window.PWA_CONFIG && window.PWA_CONFIG.apiBaseUrl) {
    return window.PWA_CONFIG.apiBaseUrl;
  }
  const currentPath = window.location.pathname;
  const baseFolder = currentPath.substring(0, currentPath.lastIndexOf('/') + 1) || './';
  return window.location.origin + baseFolder.replace(/\/$/, '') + '/api';
}

const API_PRIMARY_URL = getApiBaseUrl();
const API_FALLBACK_URL = (window.PWA_CONFIG && window.PWA_CONFIG.apiFallbackUrl) ? window.PWA_CONFIG.apiFallbackUrl : 'http://localhost:8000/api';

// Gestione Navigazione SPA tra Pagine
function navigateToPage(pageId) {
  document.querySelectorAll('.page-view').forEach(p => {
    p.classList.remove('active');
  });
  const target = document.getElementById(pageId);
  if (target) {
    target.classList.add('active');
    window.scrollTo(0, 0);
  }
}

// Controllo Stato Autenticazione all'avvio
function checkAuth() {
  const token = localStorage.getItem('pwa_auth_token');
  const userJson = localStorage.getItem('pwa_user_info');

  if (token && userJson) {
    try {
      const user = JSON.parse(userJson);
      renderUserHome(user);
      navigateToPage('page-home');
      fetchDashboardStats(token);
      return;
    } catch (e) {
      console.error('Errore parsing user info:', e);
    }
  }
  navigateToPage('page-login');
}

// Renderizzatore dati Utente nella Home Page
function renderUserHome(user) {
  const nameEl = document.getElementById('user-display-name');
  const roleNameEl = document.getElementById('user-role-name');
  const roleBadgeEl = document.getElementById('user-role-badge');

  if (nameEl) nameEl.textContent = `${user.nome || ''} ${user.cognome || ''}`.trim() || user.username || 'Utente';
  if (roleNameEl) roleNameEl.textContent = user.ruolo || 'normale';

  if (roleBadgeEl) {
    if (user.ruolo === 'admin') roleBadgeEl.color = 'danger';
    else if (user.ruolo === 'fleet_manager') roleBadgeEl.color = 'warning';
    else if (user.ruolo === 'assistenza') roleBadgeEl.color = 'tertiary';
    else roleBadgeEl.color = 'primary';
  }
}

// Helper Fetch flessibile con tentativo primario (relativo) e fallback su server locale
async function apiFetch(endpoint, options = {}) {
  const primaryUrl = `${API_PRIMARY_URL}${endpoint}`;
  try {
    const res = await fetch(primaryUrl, options);
    if (res.ok || res.status === 401 || res.status === 400 || res.status === 403) {
      return res;
    }
  } catch (e) {
    console.warn(`Impossibile contattare l'endpoint primario (${primaryUrl}), proseguo con il fallback...`);
  }

  // Tenta con l'URL di fallback
  const fallbackUrl = `${API_FALLBACK_URL}${endpoint}`;
  return fetch(fallbackUrl, options);
}

// Recupero Statistiche Dashboard dal Backend Python
async function fetchDashboardStats(token) {
  try {
    const res = await apiFetch('/dashboard', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });

    if (res && res.ok) {
      const data = await res.json();
      document.getElementById('stat-tickets').textContent = data.tickets_open || 0;
      document.getElementById('stat-vehicles').textContent = data.vehicles_count || 376;
      document.getElementById('stat-presenze').textContent = data.presenze_status || 'Attivo';
      document.getElementById('api-status-badge').color = 'success';
      document.getElementById('api-status-badge').innerHTML = '<ion-icon name="pulse-outline"></ion-icon> API Online';
    }
  } catch (e) {
    console.warn('Backend API non raggiungibile, utilizzo dati locali cached:', e);
    document.getElementById('api-status-badge').color = 'medium';
    document.getElementById('api-status-badge').innerHTML = '<ion-icon name="cloud-offline-outline"></ion-icon> Standalone';
  }
}

// Inizializzazione Event Listener al caricamento DOM
document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('login-form');
  const loginErrorAlert = document.getElementById('login-error-alert');
  const loginErrorText = document.getElementById('login-error-text');
  const btnLogout = document.getElementById('btn-logout');

  // Submit Form di Login (Azione API POST /api/login)
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      loginErrorAlert.style.display = 'none';

      const usernameInput = document.getElementById('login-username');
      const passwordInput = document.getElementById('login-password');

      const username = usernameInput ? usernameInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value.trim() : '';

      if (!username || !password) {
        loginErrorText.textContent = 'Inserisci sia lo username che la password.';
        loginErrorAlert.style.display = 'block';
        return;
      }

      try {
        const res = await apiFetch('/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });

        if (res && res.ok) {
          const data = await res.json();
          localStorage.setItem('pwa_auth_token', data.token);
          localStorage.setItem('pwa_user_info', JSON.stringify(data.user));
          
          renderUserHome(data.user);
          navigateToPage('page-home');
          fetchDashboardStats(data.token);
        } else {
          const errData = await (res ? res.json() : Promise.resolve({})).catch(() => ({}));
          loginErrorText.textContent = errData.detail || 'Credenziali non valide o utente non attivo.';
          loginErrorAlert.style.display = 'block';
        }
      } catch (err) {
        console.warn('Backend offline, consentito accesso demo offline:', err);
        // Fallback demo per fruizione offline SPA
        const demoUser = { username: username, nome: 'Utente', cognome: 'Demo', ruolo: 'normale' };
        localStorage.setItem('pwa_auth_token', 'demo_token_pwa');
        localStorage.setItem('pwa_user_info', JSON.stringify(demoUser));

        renderUserHome(demoUser);
        navigateToPage('page-home');
      }
    });
  }

  // Azione Logout (API POST /api/logout)
  if (btnLogout) {
    btnLogout.addEventListener('click', async () => {
      const token = localStorage.getItem('pwa_auth_token');
      if (token) {
        apiFetch('/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        }).catch(() => {});
      }
      localStorage.removeItem('pwa_auth_token');
      localStorage.removeItem('pwa_user_info');
      navigateToPage('page-login');
    });
  }

  // Registrazione Service Worker per PWA Offline con percorso relativo
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js')
      .then(reg => console.log('Service Worker PWA Registrato con percorso relativo:', reg.scope))
      .catch(err => console.error('Errore registrazione Service Worker:', err));
  }

  // Esegui controllo autenticazione iniziale
  checkAuth();
});
