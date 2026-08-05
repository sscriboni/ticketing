export function registerSW() {
  if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js')
        .then((registration) => {
          console.log('ServiceWorker registrato con successo su scope:', registration.scope);
        })
        .catch((error) => {
          console.error('Registrazione ServiceWorker fallita:', error);
        });
    });
  }
}
