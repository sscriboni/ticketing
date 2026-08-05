import React, { useState, useEffect } from 'react';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [showInstallBanner, setShowInstallBanner] = useState(false);

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
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between font-sans">
      {/* PWA Header Topbar */}
      <header className="sticky top-0 z-40 bg-slate-900/80 backdrop-blur-md border-b border-slate-800 px-4 py-3.5 flex items-center justify-between shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-blue-400 flex items-center justify-center text-white shadow-md shadow-brand-500/20 font-black text-xl">
            T
          </div>
          <div>
            <h1 className="font-bold text-lg leading-tight tracking-tight text-white flex items-center gap-2">
              Troubletick <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-400 border border-brand-500/30">PWA React</span>
            </h1>
            <p className="text-xs text-slate-400">Portale Mobile Operativo</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status Badge Network */}
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
            isOnline 
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
              : 'bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400' : 'bg-amber-400'}`}></span>
            {isOnline ? 'Online' : 'Offline'}
          </span>
        </div>
      </header>

      {/* Main App Content Area */}
      <main className="flex-1 max-w-3xl w-full mx-auto p-4 space-y-6 pb-24">
        {/* Banner Installazione PWA se disponibile */}
        {showInstallBanner && (
          <div className="bg-gradient-to-r from-brand-700 to-blue-600 rounded-2xl p-4 text-white shadow-xl shadow-brand-600/20 border border-brand-500/40 flex flex-col sm:flex-row items-center justify-between gap-3 animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-white/10 rounded-xl backdrop-blur-sm">
                📱
              </div>
              <div>
                <h3 className="font-bold text-base">Installa Troubletick PWA</h3>
                <p className="text-xs text-blue-100">Aggiungi la Webapp alla schermata Home del tuo smartphone per l'accesso rapido ed offline.</p>
              </div>
            </div>
            <button
              onClick={handleInstallApp}
              className="w-full sm:w-auto px-4 py-2 bg-white text-brand-700 font-bold text-xs rounded-xl shadow hover:bg-blue-50 transition-colors whitespace-nowrap"
            >
              Installa Ora
            </button>
          </div>
        )}

        {/* Tab Dashboard View */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* KPI Cards Grid */}
            <div className="grid grid-cols-2 gap-3 sm:gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-700 transition-all">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-slate-400">Ticket Aperti</span>
                  <span className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400">🎫</span>
                </div>
                <div className="text-2xl font-black text-white">4</div>
                <p className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1">
                  <span>↓ 2 rispetto a ieri</span>
                </p>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-700 transition-all">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-slate-400">Veicoli In Uso</span>
                  <span className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400">🚘</span>
                </div>
                <div className="text-2xl font-black text-white">12 / 376</div>
                <p className="text-[11px] text-slate-400 mt-1">
                  Flotta Aziendale Attiva
                </p>
              </div>
            </div>

            {/* Quick Actions Panel */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
              <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <span>⚡</span> Azioni Rapide Operatore
              </h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <button className="flex items-center justify-between p-3.5 bg-slate-800/80 hover:bg-slate-800 rounded-xl border border-slate-700/60 transition-all text-left group">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">🚗</span>
                    <div>
                      <div className="font-semibold text-sm text-slate-100 group-hover:text-brand-400 transition-colors">Prenota Veicolo</div>
                      <div className="text-xs text-slate-400">Carpooling & Flotta</div>
                    </div>
                  </div>
                  <span className="text-slate-500 group-hover:translate-x-1 transition-transform">→</span>
                </button>

                <button className="flex items-center justify-between p-3.5 bg-slate-800/80 hover:bg-slate-800 rounded-xl border border-slate-700/60 transition-all text-left group">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">🛠️</span>
                    <div>
                      <div className="font-semibold text-sm text-slate-100 group-hover:text-brand-400 transition-colors">Apri Ticket</div>
                      <div className="text-xs text-slate-400">Segnalazione Guasto</div>
                    </div>
                  </div>
                  <span className="text-slate-500 group-hover:translate-x-1 transition-transform">→</span>
                </button>
              </div>
            </div>

            {/* Recent Items List */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-3">
              <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
                Ultime Notifiche & Stato
              </h2>

              <div className="divide-y divide-slate-800">
                <div className="py-3 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-sm text-slate-200">Revisione Programmata Fiat Panda</div>
                    <div className="text-xs text-slate-400">Targa: FE123XY &bull; Scadenza tra 14 giorni</div>
                  </div>
                  <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    In Scadenza
                  </span>
                </div>

                <div className="py-3 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-sm text-slate-200">Presenza Smartworking Confermata</div>
                    <div className="text-xs text-slate-400">Data: Domani 8:00–17:00</div>
                  </div>
                  <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    Approvato
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab Carpooling / Flotta */}
        {activeTab === 'flotta' && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg space-y-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <span>🚘</span> Automezzi & Flotta Aziendale
            </h2>
            <p className="text-xs text-slate-400">Scheletro React + Tailwind per la gestione PWA del parco veicoli e prenotazioni Carpooling.</p>

            <div className="p-4 bg-slate-800/60 rounded-xl border border-slate-700/60 text-sm text-slate-300">
              Pronto per l'integrazione API con le rotte automezzi backend di Troubletick!
            </div>
          </div>
        )}

        {/* Tab Profilo */}
        {activeTab === 'profile' && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg space-y-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <span>👤</span> Profilo Operatore PWA
            </h2>
            <p className="text-xs text-slate-400">Informazioni account ed impostazioni notifiche push PWA.</p>
          </div>
        )}
      </main>

      {/* Fixed Bottom PWA Navigation Bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 bg-slate-900/90 backdrop-blur-lg border-t border-slate-800 px-6 py-2 shadow-2xl">
        <div className="max-w-md mx-auto flex items-center justify-around">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`flex flex-col items-center gap-1 py-1 px-3 rounded-xl transition-colors ${
              activeTab === 'dashboard' ? 'text-brand-400 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="text-xl">📊</span>
            <span className="text-[10px]">Dashboard</span>
          </button>

          <button
            onClick={() => setActiveTab('flotta')}
            className={`flex flex-col items-center gap-1 py-1 px-3 rounded-xl transition-colors ${
              activeTab === 'flotta' ? 'text-brand-400 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="text-xl">🚘</span>
            <span className="text-[10px]">Flotta</span>
          </button>

          <button
            onClick={() => setActiveTab('profile')}
            className={`flex flex-col items-center gap-1 py-1 px-3 rounded-xl transition-colors ${
              activeTab === 'profile' ? 'text-brand-400 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="text-xl">👤</span>
            <span className="text-[10px]">Profilo</span>
          </button>
        </div>
      </nav>
    </div>
  );
}
