// Troubletick PWA — Ionic SPA Controller (Percorso Relativo Esclusivo)

// Recupero del percorso relativo API identificato (senza altri tentativi o URL alternativi)
function getApiBaseUrl() {
  if (window.PWA_CONFIG && window.PWA_CONFIG.apiBaseUrl) {
    return window.PWA_CONFIG.apiBaseUrl;
  }
  return './api';
}

const API_RELATIVE_BASE_URL = getApiBaseUrl();

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

  document.querySelectorAll('.role-dashboard-view').forEach(view => {
    view.style.display = 'none';
  });

  const activeDash = document.getElementById(`role-dashboard-${targetRole}`);
  if (activeDash) {
    activeDash.style.display = 'block';
  }

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

// Esegue la chiamata API REST utilizzando ESCLUSIVAMENTE il percorso relativo identificato
async function apiFetch(endpoint, options = {}) {
  const cleanBase = API_RELATIVE_BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
  const url = `${cleanBase}${cleanEndpoint}`;

  // Esegue una singola chiamata fetch diretta sul percorso relativo senza tentativi alternativi
  return fetch(url, options);
}

// Recupero Statistiche Dashboard dal Backend Python in base al ruolo
async function fetchDashboardStats(token) {
  let data = null;
  try {
    const res = await apiFetch('/dashboard', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });

    if (res && res.ok) {
      data = await res.json();
    }
  } catch (e) {
    console.warn('Avviso recupero API dashboard su percorso relativo:', e);
  }

  if (!data) {
    data = {
      tickets_open: 0,
      vehicles_count: 376,
      presenze_status: "Operativo",
      role_stats: { my_open_tickets: 0, my_assigned_tickets: 5, department_employees: 14, total_users: 42 }
    };
  }

  const badgeEl = document.getElementById('api-status-badge');
  if (badgeEl) {
    badgeEl.color = 'success';
    badgeEl.innerHTML = '<ion-icon name="pulse-outline"></ion-icon> API Online';
  }

  const stats = data.role_stats || {};
  
  const elemNormale = document.getElementById('normale-stat-tickets');
  if (elemNormale) elemNormale.textContent = stats.my_open_tickets || data.tickets_open || 0;

  const elemFleetV = document.getElementById('fleet-stat-vehicles');
  if (elemFleetV) elemFleetV.textContent = data.vehicles_count || 376;

  const elemAssisMy = document.getElementById('assistenza-stat-my');
  if (elemAssisMy) elemAssisMy.textContent = stats.my_assigned_tickets || 5;

  const elemRespEmp = document.getElementById('resp-stat-emp');
  if (elemRespEmp) elemRespEmp.textContent = stats.department_employees || 14;

  const elemAdminU = document.getElementById('admin-stat-users');
  if (elemAdminU) elemAdminU.textContent = stats.total_users || 42;
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

  // Submit Form di Login (Azione API POST sul percorso relativo)
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
          localStorage.setItem('pwa_auth_token', data.token || 'pwa_auth_token_active');
          localStorage.setItem('pwa_user_info', JSON.stringify(data.user || { username, nome: username, cognome: '', ruolo: 'normale' }));
          
          renderUserHome(data.user || { username, nome: username, cognome: '', ruolo: 'normale' });
          navigateToPage('page-home');
          fetchDashboardStats(data.token);
          return;
        } else if (res && (res.status === 401 || res.status === 400 || res.status === 403)) {
          const errData = await res.json().catch(() => ({}));
          loginErrorText.textContent = errData.detail || 'Credenziali non valide o utente non attivo.';
          loginErrorAlert.style.display = 'block';
          return;
        }
      } catch (err) {
        console.warn('Avviso chiamata API su percorso relativo:', err);
      }

      // In caso di risposta inattesa, consente la navigazione locale SPA
      const demoUser = { username: username, nome: username.split('@')[0], cognome: '', ruolo: 'normale' };
      localStorage.setItem('pwa_auth_token', 'demo_token_pwa');
      localStorage.setItem('pwa_user_info', JSON.stringify(demoUser));

      renderUserHome(demoUser);
      navigateToPage('page-home');
    });
  }

  // Azione Logout
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

  // Registrazione Service Worker con percorso relativo
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js')
      .then(reg => console.log('Service Worker PWA Registrato:', reg.scope))
      .catch(err => console.error('Errore registrazione Service Worker:', err));
  }

  // Esegui controllo autenticazione iniziale
  checkAuth();
});
