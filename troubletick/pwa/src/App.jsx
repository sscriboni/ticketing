import React, { useState, useEffect } from 'react';

export default function App() {
  const [activeRole, setActiveRole] = useState('normale');
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [showInstallBanner, setShowInstallBanner] = useState(false);
  const [currentView, setCurrentView] = useState('courtesy'); // 'courtesy', 'carpooling', 'ticket', 'presenze'

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    const handleBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setShowInstallBanner(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
    };
  }, []);

  const handleInstallApp = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    console.log(`PWA install choice: ${outcome}`);
    setDeferredPrompt(null);
    setShowInstallBanner(false);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between font-sans selection:bg-blue-500 selection:text-white">
      {/* PWA Header Topbar */}
      <header className="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 px-4 py-3.5 flex items-center justify-between shadow-xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-600 via-indigo-600 to-blue-500 flex items-center justify-center text-white shadow-lg shadow-blue-500/25 font-black text-xl tracking-wider">
            T
          </div>
          <div>
            <h1 className="font-bold text-lg leading-tight tracking-tight text-white flex items-center gap-2">
              Troubletick <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30 tracking-wider">PWA</span>
            </h1>
            <p className="text-xs text-slate-400 font-medium">Portale Mobile di Benvenuto</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status Badge Network */}
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
            isOnline 
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
              : 'bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50' : 'bg-amber-400'}`}></span>
            {isOnline ? 'Online' : 'Offline'}
          </span>
        </div>
      </header>

      {/* Main App Container */}
      <main className="flex-1 max-w-4xl w-full mx-auto p-4 sm:p-6 space-y-6 pb-28">
        
        {/* Banner Installazione PWA */}
        {showInstallBanner && (
          <div className="bg-gradient-to-r from-blue-700 via-indigo-700 to-blue-600 rounded-3xl p-5 text-white shadow-2xl shadow-blue-600/30 border border-blue-400/30 flex flex-col sm:flex-row items-center justify-between gap-4 transition-all">
            <div className="flex items-center gap-3.5">
              <div className="p-3 bg-white/10 rounded-2xl backdrop-blur-md text-2xl">
                📱
              </div>
              <div>
                <h3 className="font-bold text-base text-white">Installa Troubletick PWA</h3>
                <p className="text-xs text-blue-100/90 leading-relaxed">Aggiungi la Webapp alla tua schermata Home per accedere rapidamente anche in assenza di rete.</p>
              </div>
            </div>
            <button
              onClick={handleInstallApp}
              className="w-full sm:w-auto px-5 py-2.5 bg-white text-blue-700 font-extrabold text-xs rounded-xl shadow-lg hover:bg-blue-50 active:scale-95 transition-all whitespace-nowrap"
            >
              Installa Ora
            </button>
          </div>
        )}

        {/* HOME PAGE DI CORTESIA / HERO SECTION */}
        {currentView === 'courtesy' && (
          <div className="space-y-6">
            
            {/* Card Hero di Benvenuto */}
            <div className="relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800/80 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl">
              <div className="absolute -right-10 -bottom-10 w-48 h-48 bg-blue-600/10 rounded-full blur-3xl pointer-events-none"></div>
              
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold mb-4">
                <span>👋</span> Benvenuto nel Portale Mobile Troubletick
              </div>

              <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight leading-snug">
                Pagina di Cortesia & Servizi Operativi PWA
              </h2>

              <p className="text-sm text-slate-300 mt-2 max-w-2xl leading-relaxed">
                Questa è la pagina di benvenuto della Webapp PWA. Da qui puoi accedere rapidamente alla prenotazione dei veicoli aziendali (Carpooling), segnalare guasti e richieste di assistenza, o verificare le tue presenze ed il calendario di reparto.
              </p>

              {/* Badges Info Cortesia */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
                <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-3 text-center">
                  <div className="text-xs text-slate-400 font-medium">Stato Servizio</div>
                  <div className="text-sm font-bold text-emerald-400 mt-0.5">Attivo 24/7</div>
                </div>

                <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-3 text-center">
                  <div className="text-xs text-slate-400 font-medium">Flotta Aziendale</div>
                  <div className="text-sm font-bold text-white mt-0.5">376 Veicoli</div>
                </div>

                <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-3 text-center">
                  <div className="text-xs text-slate-400 font-medium">Supporto IT</div>
                  <div className="text-sm font-bold text-blue-400 mt-0.5">Lun–Ven 8–17</div>
                </div>

                <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-3 text-center">
                  <div className="text-xs text-slate-400 font-medium">Modalità</div>
                  <div className="text-sm font-bold text-indigo-400 mt-0.5">PWA Mobile</div>
                </div>
              </div>
            </div>

            {/* Selezione Rapida Ruolo Operativo */}
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 sm:p-6 shadow-xl space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                  <span>⚙️</span> Ruolo Operativo Selezionato
                </h3>
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  {activeRole === 'admin' && '👑 Amministratore'}
                  {activeRole === 'fleet_manager' && '🚗 Fleet Manager'}
                  {activeRole === 'assistenza' && '🛠️ Operatore Assistenza'}
                  {activeRole === 'normale' && '👤 Utente Standard'}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
                {[
                  { id: 'normale', label: 'Utente', icon: '👤' },
                  { id: 'fleet_manager', label: 'Fleet Manager', icon: '🚗' },
                  { id: 'assistenza', label: 'Assistenza', icon: '🛠️' },
                  { id: 'admin', label: 'Admin', icon: '👑' },
                ].map((r) => (
                  <button
                    key={r.id}
                    onClick={() => setActiveRole(r.id)}
                    className={`py-2.5 px-3 rounded-xl text-xs font-bold border transition-all flex items-center justify-center gap-2 ${
                      activeRole === r.id
                        ? 'bg-blue-600 text-white border-blue-500 shadow-md shadow-blue-600/20'
                        : 'bg-slate-800/80 text-slate-400 border-slate-700 hover:bg-slate-800 hover:text-slate-200'
                    }`}
                  >
                    <span>{r.icon}</span>
                    <span>{r.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* SEZIONE SERVIZI PRINCIPALI CORTESIA */}
            <div className="space-y-4">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 px-1">
                Servizi PWA Disponibili
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                
                {/* Card Carpooling & Automezzi */}
                <div 
                  onClick={() => setCurrentView('carpooling')}
                  className="group bg-slate-900 hover:bg-slate-800/90 border border-slate-800 hover:border-blue-500/50 rounded-3xl p-5 shadow-lg transition-all cursor-pointer flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center text-2xl group-hover:scale-110 transition-transform">
                      🚗
                    </div>
                    <div>
                      <h4 className="font-bold text-base text-white group-hover:text-blue-400 transition-colors flex items-center justify-between">
                        Carpooling & Flotta
                        <span className="text-slate-500 group-hover:translate-x-1 transition-transform">→</span>
                      </h4>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        Prenota un automezzo aziendale per i tuoi spostamenti di servizio, consulta le scadenze e la disponibilità in tempo reale.
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                    <span>376 Veicoli in Flotta</span>
                    <span className="text-emerald-400 font-semibold">Disponibile</span>
                  </div>
                </div>

                {/* Card Assistenza & Helpdesk */}
                <div 
                  onClick={() => setCurrentView('ticket')}
                  className="group bg-slate-900 hover:bg-slate-800/90 border border-slate-800 hover:border-indigo-500/50 rounded-3xl p-5 shadow-lg transition-all cursor-pointer flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center text-2xl group-hover:scale-110 transition-transform">
                      🛠️
                    </div>
                    <div>
                      <h4 className="font-bold text-base text-white group-hover:text-indigo-400 transition-colors flex items-center justify-between">
                        Helpdesk & Supporto
                        <span className="text-slate-500 group-hover:translate-x-1 transition-transform">→</span>
                      </h4>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        Invia segnalazioni tecniche, richiedi assistenza informatica ed effettua il tracciamento dei tuoi ticket.
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                    <span>Apertura Nuova Richiesta</span>
                    <span className="text-blue-400 font-semibold">Attivo</span>
                  </div>
                </div>

                {/* Card Calendario Presenze */}
                <div 
                  onClick={() => setCurrentView('presenze')}
                  className="group bg-slate-900 hover:bg-slate-800/90 border border-slate-800 hover:border-emerald-500/50 rounded-3xl p-5 shadow-lg transition-all cursor-pointer flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center text-2xl group-hover:scale-110 transition-transform">
                      📅
                    </div>
                    <div>
                      <h4 className="font-bold text-base text-white group-hover:text-emerald-400 transition-colors flex items-center justify-between">
                        Presenze & Smartworking
                        <span className="text-slate-500 group-hover:translate-x-1 transition-transform">→</span>
                      </h4>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        Segnala ferie, giorni di smartworking, corsi o trasferte e consulta il calendario del tuo reparto.
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                    <span>Matrice Mensile Reparto</span>
                    <span className="text-emerald-400 font-semibold">Sincronizzato</span>
                  </div>
                </div>

                {/* Card Magazzino & Materiali */}
                <div 
                  className="group bg-slate-900 hover:bg-slate-800/90 border border-slate-800 hover:border-amber-500/50 rounded-3xl p-5 shadow-lg transition-all cursor-pointer flex flex-col justify-between opacity-90"
                >
                  <div className="space-y-3">
                    <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center text-2xl group-hover:scale-110 transition-transform">
                      📦
                    </div>
                    <div>
                      <h4 className="font-bold text-base text-white group-hover:text-amber-400 transition-colors flex items-center justify-between">
                        Magazzino & Materiali
                        <span className="text-slate-500 group-hover:translate-x-1 transition-transform">→</span>
                      </h4>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        Consultazione giacenze articoli, richiesta materiale tecnico e componenti di ricambio per l'assistenza.
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                    <span>Giacenze In Tempo Reale</span>
                    <span className="text-amber-400 font-semibold">Consultabile</span>
                  </div>
                </div>

              </div>
            </div>

            {/* Footer Cortesia Informazioni */}
            <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-2xl text-center space-y-2">
              <p className="text-xs text-slate-400">
                Se necessiti di ulteriore supporto o informazioni sul servizio, contatta l'Helpdesk aziendale a <a href="mailto:admin@example.com" className="text-blue-400 underline font-semibold">admin@example.com</a>.
              </p>
              <p className="text-[11px] text-slate-500">
                Troubletick PWA &copy; 2026 ICT — ASL Alessandria
              </p>
            </div>

          </div>
        )}

        {/* VISTA CARPOOLING DETAIL */}
        {currentView === 'carpooling' && (
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
            <button 
              onClick={() => setCurrentView('courtesy')}
              className="text-xs font-bold text-blue-400 hover:underline flex items-center gap-1 mb-2"
            >
              ← Torna alla Home di Cortesia
            </button>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>🚗</span> Prenotazione Automezzi Carpooling
            </h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Interfaccia PWA in React per la ricerca e prenotazione rapida dei veicoli aziendali.
            </p>
            <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800 text-sm text-slate-300">
              Rotta integrata con l'applicazione backend `appautopark.py` su porta 5002.
            </div>
          </div>
        )}

        {/* VISTA TICKET DETAIL */}
        {currentView === 'ticket' && (
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
            <button 
              onClick={() => setCurrentView('courtesy')}
              className="text-xs font-bold text-blue-400 hover:underline flex items-center gap-1 mb-2"
            >
              ← Torna alla Home di Cortesia
            </button>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>🛠️</span> Helpdesk & Segnalazione Ticket
            </h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Compila il modulo di segnalazione guasti o supporto tecnico.
            </p>
          </div>
        )}

        {/* VISTA PRESENZE DETAIL */}
        {currentView === 'presenze' && (
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
            <button 
              onClick={() => setCurrentView('courtesy')}
              className="text-xs font-bold text-blue-400 hover:underline flex items-center gap-1 mb-2"
            >
              ← Torna alla Home di Cortesia
            </button>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>📅</span> Calendario Presenze Operatore
            </h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Gestione presenze, smartworking e ferie aziendali.
            </p>
          </div>
        )}

      </main>

      {/* Fixed Bottom PWA Navigation Bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 bg-slate-900/95 backdrop-blur-xl border-t border-slate-800 px-6 py-2 shadow-2xl">
        <div className="max-w-md mx-auto flex items-center justify-around">
          <button
            onClick={() => setCurrentView('courtesy')}
            className={`flex flex-col items-center gap-1 py-1 px-3.5 rounded-2xl transition-all ${
              currentView === 'courtesy' ? 'text-blue-400 font-extrabold bg-blue-500/10' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="text-xl">🏠</span>
            <span className="text-[10px]">Home Cortesia</span>
          </button>

          <button
            onClick={() => setCurrentView('carpooling')}
            className={`flex flex-col items-center gap-1 py-1 px-3.5 rounded-2xl transition-all ${
              currentView === 'carpooling' ? 'text-blue-400 font-extrabold bg-blue-500/10' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="text-xl">🚗</span>
            <span className="text-[10px]">Flotta</span>
          </button>

          <button
            onClick={() => setCurrentView('ticket')}
            className={`flex flex-col items-center gap-1 py-1 px-3.5 rounded-2xl transition-all ${
              currentView === 'ticket' ? 'text-blue-400 font-extrabold bg-blue-500/10' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="text-xl">🛠️</span>
            <span className="text-[10px]">Supporto</span>
          </button>

          <button
            onClick={() => setCurrentView('presenze')}
            className={`flex flex-col items-center gap-1 py-1 px-3.5 rounded-2xl transition-all ${
              currentView === 'presenze' ? 'text-blue-400 font-extrabold bg-blue-500/10' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="text-xl">📅</span>
            <span className="text-[10px]">Presenze</span>
          </button>
        </div>
      </nav>
    </div>
  );
}
