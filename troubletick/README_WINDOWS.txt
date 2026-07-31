Troubletick (SQLite) — Stand-alone, persistente

1) Installazione dipendenze
   cd app
   pip install -r requirements.txt

2) Avvio server
   cd app
   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

3) Accesso
   Home:  http://localhost:8000
   Login: http://localhost:8000/login
   Utenti demo:
     - admin / admin (superuser)
     - it_operator / it123 (reparto IT)
     - manut_operator / manut123 (Manutenzione)

4) Configurazione testi
   Modifica app/config.json (UTF-8 o UTF-8 senza BOM) e riavvia.
