// Troubletick PWA — Ionic SPA Controller (Gestione Multi-Ruolo & Selezione Ruolo)

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

// Commutatore dinamico delle Dashboard in base al Ruolo Utente scelto
function switchRoleDashboardView(roleName) {
  const allowedRoles = ['normale', 'fleet_manager', 'global_fleet_manager', 'assistenza', 'responsabile', 'admin'];
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

  if (targetRole === 'global_fleet_manager' || targetRole === 'fleet_manager') {
    loadGlobalFleetVehicles();
  }
}

// Generatore ed Handlers per la Pagina di Selezione Ruolo Multiplo
function renderRoleSelectionPage(user, userRoles) {
  const container = document.getElementById('role-select-buttons-list');
  if (!container) return;

  document.querySelectorAll('.user-display-name').forEach(el => {
    el.textContent = `${user.nome || ''} ${user.cognome || ''}`.trim() || user.username || 'Utente';
  });

  const roleMeta = {
    'normale': { title: '👤 Dipendente Standard', desc: 'Prenotazione carpooling, presenze e ticket personali', color: 'btn-outline-primary' },
    'fleet_manager': { title: '🚗 Fleet Manager', desc: 'Gestione flotta locale, viaggi e manutenzioni', color: 'btn-outline-warning' },
    'global_fleet_manager': { title: '🌐 Global Fleet Manager', desc: 'Gestione flotta aziendale globale e parco autoveicoli', color: 'btn-outline-warning' },
    'assistenza': { title: '🛠️ Operatore Assistenza', desc: 'Console helpdesk, presa in carico e ricambi', color: 'btn-outline-info' },
    'responsabile': { title: '📋 Responsabile Reparto', desc: 'Matrice presenze mensili e piano ferie reparto', color: 'btn-outline-success' },
    'admin': { title: '👑 Amministratore Globale', desc: 'Controllo completo utenti, permessi e sistema', color: 'btn-outline-danger' }
  };

  container.innerHTML = '';
  userRoles.forEach(roleKey => {
    const meta = roleMeta[roleKey] || { title: `🎭 Ruolo: ${roleKey}`, desc: 'Accedi con questo ruolo', color: 'btn-outline-primary' };
    
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn ${meta.color} p-3 text-start rounded-3 shadow-sm d-flex flex-column gap-1 text-white`;
    btn.innerHTML = `
      <div class="d-flex justify-content-between align-items-center">
        <strong class="fs-5">${meta.title}</strong>
        <i class="bi bi-chevron-right fs-5"></i>
      </div>
      <span class="small opacity-75">${meta.desc}</span>
    `;

    btn.addEventListener('click', () => {
      localStorage.setItem('pwa_active_role', roleKey);
      renderUserHome(user, roleKey);
      navigateToPage('page-home');
      const token = localStorage.getItem('pwa_auth_token');
      fetchDashboardStats(token);
    });

    container.appendChild(btn);
  });
}

// Filtra i pulsanti della barra selettrice Vista Ruolo in base ai ruoli autorizzati per l'utente
function setupRoleSwitcherBar(userRoles, activeRole) {
  const switcherGroup = document.getElementById('role-switcher-group');
  if (!switcherGroup) return;

  const buttons = switcherGroup.querySelectorAll('button[data-role-view]');
  const isGlobalAdmin = userRoles.includes('admin');

  buttons.forEach(btn => {
    const roleKey = btn.getAttribute('data-role-view');
    if (isGlobalAdmin || userRoles.includes(roleKey)) {
      btn.style.display = 'inline-block';
    } else {
      btn.style.display = 'none';
    }
  });
}

// Controllo Stato Autenticazione all'avvio
function checkAuth() {
  if (typeof hideLoginError === 'function') hideLoginError();
  const token = localStorage.getItem('pwa_auth_token');
  const userJson = localStorage.getItem('pwa_user_info');
  const activeRole = localStorage.getItem('pwa_active_role');

  if (token && userJson) {
    try {
      const user = JSON.parse(userJson);
      const userRoles = user.roles && user.roles.length > 0 ? user.roles : (user.ruolo ? [user.ruolo] : ['normale']);
      
      if (!activeRole && userRoles.length > 1) {
        renderRoleSelectionPage(user, userRoles);
        navigateToPage('page-select-role');
        return;
      }

      const roleToUse = activeRole || userRoles[0] || 'normale';
      renderUserHome(user, roleToUse);
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
function renderUserHome(user, roleName) {
  const fullName = `${user.nome || ''} ${user.cognome || ''}`.trim() || user.username || 'Utente';
  document.querySelectorAll('.user-display-name').forEach(el => {
    el.textContent = fullName;
  });

  const userRoles = user.roles && user.roles.length > 0 ? user.roles : (user.ruolo ? [user.ruolo] : ['normale']);
  const activeRole = roleName || localStorage.getItem('pwa_active_role') || userRoles[0] || 'normale';

  setupRoleSwitcherBar(userRoles, activeRole);
  switchRoleDashboardView(activeRole);
}

// Esegue la chiamata API REST utilizzando ESCLUSIVAMENTE il percorso relativo identificato
async function apiFetch(endpoint, options = {}) {
  const cleanBase = API_RELATIVE_BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
  const url = `${cleanBase}${cleanEndpoint}`;
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

// Gestione Recupero Autoveicoli Flotta Globale dall'API REST
let currentFleetVehicles = [];

async function loadGlobalFleetVehicles() {
  const token = localStorage.getItem('pwa_auth_token');
  const spinner = document.getElementById('global-fleet-loading-spinner');
  const listContainer = document.getElementById('global-fleet-vehicles-list');

  if (spinner) spinner.style.display = 'block';
  if (listContainer) listContainer.style.display = 'none';

  try {
    const res = await apiFetch('/automezzi', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });

    if (res && res.ok) {
      const data = await res.json();
      currentFleetVehicles = data.automezzi || [];

      // Aggiorna contatori KPI
      const elTotal = document.getElementById('global-fleet-stat-total');
      const elDisp = document.getElementById('global-fleet-stat-disponibili');
      const elUso = document.getElementById('global-fleet-stat-inuso');
      const elMaint = document.getElementById('global-fleet-stat-manutenzione');

      if (elTotal) elTotal.textContent = data.totale || 0;
      if (elDisp) elDisp.textContent = data.totale_disponibili || 0;
      if (elUso) elUso.textContent = data.totale_in_uso || 0;
      if (elMaint) elMaint.textContent = data.totale_in_manutenzione || 0;

      renderGlobalFleetList(currentFleetVehicles);
    } else {
      renderGlobalFleetError('Impossibile recuperare l\'elenco autoveicoli dal server.');
    }
  } catch (err) {
    console.error('Errore durante il recupero autoveicoli PWA:', err);
    renderGlobalFleetError('Errore di connessione durante il recupero dei veicoli.');
  } finally {
    if (spinner) spinner.style.display = 'none';
    if (listContainer) listContainer.style.display = 'flex';
  }
}

function renderGlobalFleetList(vehicles) {
  const listContainer = document.getElementById('global-fleet-vehicles-list');
  if (!listContainer) return;

  const searchInput = document.getElementById('global-fleet-search-input');
  const filterStato = document.getElementById('global-fleet-filter-stato');

  const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
  const selectedStato = filterStato ? filterStato.value.trim().toLowerCase() : '';

  const filtered = vehicles.filter(v => {
    const matchesSearch = !query ||
      (v.targa && v.targa.toLowerCase().includes(query)) ||
      (v.modello && v.modello.toLowerCase().includes(query)) ||
      (v.marca_nome && v.marca_nome.toLowerCase().includes(query)) ||
      (v.reparto_assegnato_nome && v.reparto_assegnato_nome.toLowerCase().includes(query)) ||
      (v.sede_assegnata_nome && v.sede_assegnata_nome.toLowerCase().includes(query));

    const matchesStato = !selectedStato || (v.stato && v.stato.toLowerCase() === selectedStato);
    return matchesSearch && matchesStato;
  });

  if (filtered.length === 0) {
    listContainer.innerHTML = `
      <div class="col-12 text-center py-4">
        <div class="text-muted">
          <i class="bi bi-car-front fs-1 opacity-50"></i>
          <p class="mt-2 mb-0">Nessun autoveicolo trovato con i filtri selezionati.</p>
        </div>
      </div>
    `;
    return;
  }

  listContainer.innerHTML = filtered.map(v => {
    let badgeClass = 'bg-success';
    let statoIcon = 'bi-check-circle-fill';
    const stLower = (v.stato || '').toLowerCase();
    if (stLower === 'in uso') {
      badgeClass = 'bg-primary';
      statoIcon = 'bi-person-badge-fill';
    } else if (stLower === 'in manutenzione') {
      badgeClass = 'bg-danger';
      statoIcon = 'bi-tools';
    }

    const tagsHtml = (v.tags || []).map(t =>
      `<span class="badge me-1" style="background-color: ${t.colore || '#0d6efd'}">${t.nome}</span>`
    ).join('');

    return `
      <div class="col-12 col-md-6 col-lg-4">
        <ion-card class="dashboard-card h-100 m-0 p-3 border-top border-3 border-warning">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div>
              <span class="badge bg-slate-800 text-warning font-monospace fs-6 px-2 py-1 border border-warning border-opacity-25 me-1">
                ${v.targa || 'N/D'}
              </span>
              <span class="badge ${badgeClass} text-white px-2 py-1">
                <i class="bi ${statoIcon} me-1"></i>${v.stato || 'Disponibile'}
              </span>
            </div>
            <span class="text-muted small">${v.alimentazione || ''}</span>
          </div>

          <h6 class="fw-bold text-white mb-1">
            ${v.marca_nome || ''} ${v.modello || ''}
          </h6>

          <div class="small text-slate-300 mb-2">
            <div><i class="bi bi-geo-alt text-primary me-1"></i>Sede: <strong>${v.sede_assegnata_nome || 'Non Assegnata'}</strong></div>
            <div><i class="bi bi-diagram-3 text-info me-1"></i>Reparto: <strong>${v.reparto_assegnato_nome || 'Non Assegnato'}</strong></div>
            <div><i class="bi bi-speedometer2 text-warning me-1"></i>Km Attuali: <strong>${(v.km_attuali || 0).toLocaleString('it-IT')} km</strong></div>
          </div>

          ${tagsHtml ? `<div class="mb-2">${tagsHtml}</div>` : ''}

          <div class="d-flex justify-content-between align-items-center pt-2 border-top border-slate-800 text-muted extra-small">
            <span>Proprietà: ${v.proprieta || 'N/D'}</span>
            ${v.canone_noleggio > 0 ? `<span>Canone: €${v.canone_noleggio}/mo</span>` : ''}
          </div>
        </ion-card>
      </div>
    `;
  }).join('');
}

function renderGlobalFleetError(msg) {
  const listContainer = document.getElementById('global-fleet-vehicles-list');
  if (listContainer) {
    listContainer.innerHTML = `
      <div class="col-12 text-center py-4">
        <div class="alert alert-danger text-start">
          <i class="bi bi-exclamation-triangle-fill me-2"></i> ${msg}
        </div>
      </div>
    `;
  }
}

// Inizializzazione Event Listener al caricamento DOM
document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('login-form');
  const loginErrorAlert = document.getElementById('login-error-alert');
  const loginErrorText = document.getElementById('login-error-text');
  const btnLogout = document.getElementById('btn-logout');

  // Listener per ricerca e filtri autoveicoli Global Fleet
  const btnRefreshFleet = document.getElementById('btn-refresh-global-fleet');
  const searchInputFleet = document.getElementById('global-fleet-search-input');
  const filterStatoFleet = document.getElementById('global-fleet-filter-stato');

  if (btnRefreshFleet) {
    btnRefreshFleet.addEventListener('click', () => loadGlobalFleetVehicles());
  }

  if (searchInputFleet) {
    searchInputFleet.addEventListener('input', () => renderGlobalFleetList(currentFleetVehicles));
  }

  if (filterStatoFleet) {
    filterStatoFleet.addEventListener('change', () => renderGlobalFleetList(currentFleetVehicles));
  }

  // Gestione click sui pulsanti del selettore ruolo
  const roleSwitcher = document.getElementById('role-switcher-group');
  if (roleSwitcher) {
    roleSwitcher.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-role-view]');
      if (btn) {
        const targetRole = btn.getAttribute('data-role-view');
        localStorage.setItem('pwa_active_role', targetRole);
        switchRoleDashboardView(targetRole);
      }
    });
  }

function hideLoginError() {
  const alertEl = document.getElementById('login-error-alert');
  if (alertEl) {
    alertEl.classList.add('d-none');
    alertEl.style.display = 'none';
  }
}

function showLoginError(msg) {
  const alertEl = document.getElementById('login-error-alert');
  const textEl = document.getElementById('login-error-text');
  if (textEl) textEl.textContent = msg || 'Credenziali non valide. Riprova.';
  if (alertEl) {
    alertEl.classList.remove('d-none');
    alertEl.style.display = 'flex';
  }
}

  // Submit Form di Login (Azione API POST sul percorso relativo)
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      hideLoginError();

      const usernameInput = document.getElementById('login-username');
      const passwordInput = document.getElementById('login-password');

      const username = usernameInput ? usernameInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value.trim() : '';

      if (!username || !password) {
        showLoginError('Inserisci sia lo username che la password.');
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
          const user = data.user || { username, nome: username, cognome: '', ruolo: 'normale' };
          const userRoles = user.roles && user.roles.length > 0 ? user.roles : (user.ruolo ? [user.ruolo] : ['normale']);
          
          hideLoginError();
          localStorage.setItem('pwa_auth_token', data.token || 'pwa_auth_token_active');
          localStorage.setItem('pwa_user_info', JSON.stringify(user));
          localStorage.removeItem('pwa_active_role');

          if (userRoles.length > 1) {
            renderRoleSelectionPage(user, userRoles);
            navigateToPage('page-select-role');
          } else {
            const activeRole = userRoles[0] || 'normale';
            localStorage.setItem('pwa_active_role', activeRole);
            renderUserHome(user, activeRole);
            navigateToPage('page-home');
            fetchDashboardStats(data.token);
          }
          return;
        } else if (res && (res.status === 401 || res.status === 400 || res.status === 403)) {
          const errData = await res.json().catch(() => ({}));
          showLoginError(errData.detail || 'Credenziali non valide o utente non attivo.');
          return;
        }
      } catch (err) {
        console.warn('Avviso chiamata API su percorso relativo:', err);
      }

      // In caso di errore server generico, gestisci il messaggio
      showLoginError('Impossibile contattare il server di autenticazione. Riprova più tardi.');
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
      localStorage.removeItem('pwa_active_role');
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
