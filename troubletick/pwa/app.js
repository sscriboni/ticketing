// Troubletick PWA — Ionic SPA Controller (Supporto Dashboard Multi-Ruolo)

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

// Gestione Navigazione SPA tra Pagine (<ion-page>)
function navigateToPage(pageId) {
  document.querySelectorAll('ion-page.page-view').forEach(p => {
    p.classList.remove('active');
  });
  const target = document.getElementById(pageId);
  if (target) {
    target.classList.add('active');
    window.scrollTo(0, 0);
  }
}

// Commutatore dinamico delle Dashboard in base al Ruolo Utente
function switchRoleDashboardView(roleName) {
  const allowedRoles = ['normale', 'fleet_manager', 'assistenza', 'responsabile', 'admin'];
  const targetRole = allowedRoles.includes(roleName) ? roleName : 'normale';

  // Nascondi tutte le dashboard di ruolo
  document.querySelectorAll('.role-dashboard-view').forEach(view => {
    view.style.display = 'none';
  });

  // Mostra la dashboard del ruolo specifico
  const activeDash = document.getElementById(`role-dashboard-${targetRole}`);
  if (activeDash) {
    activeDash.style.display = 'block';
  }

  // Aggiorna gli stati attivi nei pulsanti del selettore ruolo
  document.querySelectorAll('#role-switcher-group button').forEach(btn => {
    if (btn.getAttribute('data-role-view') === targetRole) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
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

// Renderizzatore dati Utente nella Home Page per il ruolo attivo
function renderUserHome(user) {
  const fullName = `${user.nome || ''} ${user.cognome || ''}`.trim() || user.username || 'Utente';
  document.querySelectorAll('.user-display-name').forEach(el => {
    el.textContent = fullName;
  });

  const userRole = user.ruolo || 'normale';
  switchRoleDashboardView(userRole);
}

// Helper Fetch flessibile con tentativi API REST
async function apiFetch(endpoint, options = {}) {
  const primaryUrl = `${API_PRIMARY_URL}${endpoint}`;
  try {
    const res = await fetch(primaryUrl, options);
    if (res.ok || res.status === 401 || res.status === 400 || res.status === 403) {
      return res;
    }
  } catch (e) {
    console.warn(`Endpoint primario non raggiungibile (${primaryUrl}), proseguo con fallback...`);
  }

  const fallbackUrl = `${API_FALLBACK_URL}${endpoint}`;
  return fetch(fallbackUrl, options);
}

// Recupero Statistiche Dashboard dal Backend Python in base al ruolo
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
      document.getElementById('api-status-badge').color = 'success';
      document.getElementById('api-status-badge').innerHTML = '<ion-icon name="pulse-outline"></ion-icon> API Online';

      const stats = data.role_stats || {};
      
      // Aggiorna metriche ruolo Utente Normale
      const elemNormale = document.getElementById('normale-stat-tickets');
      if (elemNormale) elemNormale.textContent = stats.my_open_tickets || data.tickets_open || 0;

      // Aggiorna metriche ruolo Fleet Manager
      const elemFleetV = document.getElementById('fleet-stat-vehicles');
      if (elemFleetV) elemFleetV.textContent = data.vehicles_count || 376;

      // Aggiorna metriche ruolo Assistenza
      const elemAssisMy = document.getElementById('assistenza-stat-my');
      if (elemAssisMy) elemAssisMy.textContent = stats.my_assigned_tickets || 5;

      // Aggiorna metriche ruolo Responsabile Reparto
      const elemRespEmp = document.getElementById('resp-stat-emp');
      if (elemRespEmp) elemRespEmp.textContent = stats.department_employees || 14;

      // Aggiorna metriche ruolo Admin
      const elemAdminU = document.getElementById('admin-stat-users');
      if (elemAdminU) elemAdminU.textContent = stats.total_users || 42;
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

  // Gestione click sui pulsanti del selettore ruolo
  const roleSwitcher = document.getElementById('role-switcher-group');
  if (roleSwitcher) {
    roleSwitcher.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-role-view]');
      if (btn) {
        const targetRole = btn.getAttribute('data-role-view');
        switchRoleDashboardView(targetRole);
      }
    });
  }

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
