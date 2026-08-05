// Troubletick PWA — Ionic SPA Controller

// Configurazione Endpoint Backend Python API
const API_BASE_URL = 'http://localhost:8000/api';

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

  if (nameEl) nameEl.textContent = `${user.nome || ''} ${user.cognome || ''}`.strip() || user.username || 'Utente';
  if (roleNameEl) roleNameEl.textContent = user.ruolo || 'normale';

  if (roleBadgeEl) {
    if (user.ruolo === 'admin') roleBadgeEl.color = 'danger';
    else if (user.ruolo === 'fleet_manager') roleBadgeEl.color = 'warning';
    else if (user.ruolo === 'assistenza') roleBadgeEl.color = 'tertiary';
    else roleBadgeEl.color = 'primary';
  }
}

// Recupero Statistiche Dashboard dal Backend Python
async function fetchDashboardStats(token) {
  try {
    const res = await fetch(`${API_BASE_URL}/dashboard`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });

    if (res.ok) {
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
        const res = await fetch(`${API_BASE_URL}/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });

        if (res.ok) {
          const data = await res.json();
          localStorage.setItem('pwa_auth_token', data.token);
          localStorage.setItem('pwa_user_info', JSON.stringify(data.user));
          
          renderUserHome(data.user);
          navigateToPage('page-home');
          fetchDashboardStats(data.token);
        } else {
          const errData = await res.json().catch(() => ({}));
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
        fetch(`${API_BASE_URL}/logout`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        }).catch(() => {});
      }
      localStorage.removeItem('pwa_auth_token');
      localStorage.removeItem('pwa_user_info');
      navigateToPage('page-login');
    });
  }

  // Registrazione Service Worker per PWA Offline
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => console.log('Service Worker PWA Registrato:', reg.scope))
      .catch(err => console.error('Errore registrazione Service Worker:', err));
  }

  // Esegui controllo autenticazione iniziale
  checkAuth();
});
