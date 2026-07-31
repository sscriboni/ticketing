# Guida all'Installazione e Configurazione Iniziale

Benvenuto in **Troubletick**! Questa guida ti accompagnerà passo dopo passo nell'installazione dell'applicativo sul tuo server o computer locale e nella configurazione iniziale del sistema.

## 1. Requisiti di Sistema
* **Sistema Operativo**: Windows (consigliato per l'uso dello script `.bat` incluso), Linux o macOS.
* **Python**: Versione 3.9 o superiore.
* **Database**: Nessun software aggiuntivo richiesto. Il sistema utilizza SQLite per impostazione predefinita (file locale `troubletick.db`), ma supporta nativamente MySQL/MariaDB e PostgreSQL.

## 2. Installazione (Ambiente Windows)
1. Posizionati all'interno della cartella principale del progetto (dove si trova il file `startroubleticket.bat`).
2. Avvia l'applicazione facendo doppio clic sul file **`startroubleticket.bat`**.
   *Al primo avvio, lo script creerà in automatico l'ambiente virtuale, scaricherà tutte le librerie necessarie (dipendenze) e avvierà il server sulla porta 5001.*

*(In caso di errori nella creazione del `venv`, assicurati di aver installato Python e aver spuntato "Add Python to PATH" durante l'installazione).*

## 3. Installazione (Ambiente Linux / macOS)
1. Apri un terminale e posizionati all'interno della cartella principale del progetto.
2. Rendi eseguibili gli script di installazione e avvio (solo la prima volta):
   ```bash
   chmod +x install.sh start.sh
   ```
3. Esegui lo script di installazione per creare l'ambiente virtuale e installare le dipendenze:
   ```bash
   ./install.sh
   ```
4. Avvia l'applicazione eseguendo lo script di avvio:
   ```bash
   ./start.sh
   ```
   *Lo script attiverà in automatico l'ambiente virtuale e avvierà il server sulla porta 5001.*

## 4. Primo Accesso e Credenziali Predefinite
Una volta che la finestra del terminale ti indicherà che *Uvicorn è in esecuzione*, apri un browser e collegati all'indirizzo:
**http://localhost:5001**

1. Clicca sul pulsante **"Area Operatori"** in alto a destra.
2. Il sistema al primissimo avvio crea automaticamente un account Amministratore (con visibilità globale) per permetterti di accedere. Utilizza le seguenti credenziali:
   * **Username:** `admin`
   * **Password:** `admin`

> ⚠️ **IMPORTANTE:** Per motivi di sicurezza, ti consigliamo di cambiare subito la password dell'amministratore. Vai in **Admin > Operatori**, cerca l'utente *admin*, clicca su "Modifica" e digita una nuova password.

## 5. Configurazione Iniziale (Importazione Massiva)
Troubletick è dotato di un sistema di importazione massiva tramite JSON che ti permette di creare e collegare tutta la struttura aziendale (Sedi, Comuni, Categorie, Reparti, Servizi, Magazzini, Prodotti e Operatori) in un solo clic, senza doverli inserire a mano uno per uno.

1. Dopo aver effettuato l'accesso come `admin`, clicca sul bottone blu **"Admin"** in alto a destra.
2. Clicca sul riquadro **"⚙️ Impostazioni"** (Parametri globali app).
3. Scorri la pagina fino in fondo, alla sezione **"Import / Export Massivo"**.
4. Clicca sul bottone **"📄 JSON d'Esempio"**. Verrà scaricato un file di nome `configurazione_iniziale_esempio.json`.
5. Apri questo file con Blocco Note (o Visual Studio Code) e **modificalo** inserendo i dati reali della tua azienda. 
   * *Nota: La struttura JSON risolve i collegamenti tramite il nome, assicurati di scrivere i nomi in modo identico quando crei delle dipendenze (es. associa correttamente il nome di una Categoria al Prodotto desiderato).*
6. Salva il file.
7. Torna sulla pagina delle Impostazioni, seleziona il file appena salvato e metti la spunta su **"Svuota prima di importare"** (questo cancellerà eventuali dati fittizi residui garantendoti un'installazione pulita).
8. Clicca su **"Importa Dati"**.

Il sistema importerà in modo incrociato e sicuro tutto il tuo assetto organizzativo!

## 6. Impostazioni Globali Aggiuntive
Sempre all'interno della pagina **"⚙️ Impostazioni"** potrai configurare:
* Il **Nome dell'Azienda** e l'indirizzo email di supporto.
* I **parametri SMTP** per l'eventuale invio di notifiche via email.
* I parametri di connessione al **Database** (se desideri migrare da SQLite a MySQL o PostgreSQL per carichi di lavoro maggiori). *Ricorda che i cambi ai parametri del database richiedono il riavvio del server (chiudi e riapri il file `.bat` o lo script `.sh`)!*

## 7. Sviluppo e Troubleshooting
* Se il server non si avvia correttamente, controlla di avere installato tutte le dipendenze Python richieste nel tuo `venv`.
* I file caricati dagli utenti (allegati nei ticket o nei movimenti di magazzino) vengono salvati nella cartella **`app/uploads`**. Non cancellare questa cartella se vuoi mantenere i file.
* I log per i tentativi di accesso falliti vengono salvati nel file di testo `failed_logins.log` nella radice del progetto per ragioni di audit.