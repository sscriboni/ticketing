# Guida all'Installazione e Configurazione Iniziale

Benvenuto in **Troubletick**! Questa guida ti accompagnerà passo dopo passo nell'installazione dell'applicativo sul tuo server o computer locale e nella configurazione iniziale del sistema.

## 1. Prerequisiti del Server

Prima di procedere all'installazione, assicurati che il server o il computer ospitante soddisfi i seguenti requisiti:

### A. Python (Prerequisito Fondamentale)
* **Versione richiesta**: **Python 3.9 o superiore** (consigliato Python 3.11 o 3.12).
* **Installazione su Windows**:
  * Scarica l'installer ufficiale da [python.org](https://www.python.org/downloads/).
  * ⚠️ **Durante l'installazione, spunta obbligatoriamente la casella `"Add Python to PATH"`** (o `"Add python.exe to PATH"`), altrimenti gli script di avvio non riusciranno a individuare l'interprete.
* **Installazione su Linux (Debian / Ubuntu)**:
  * Assicurati di installare sia Python che i moduli per la gestione dei virtual environment e dei pacchetti:
    ```bash
    sudo apt update
    sudo apt install python3 python3-pip python3-venv
    ```
* **Installazione su Linux (RHEL / AlmaLinux / Rocky Linux / CentOS)**:
  ```bash
  sudo dnf install python3 python3-pip
  ```

### B. Database
* **SQLite (Incluso)**: ideale per **piccole installazioni**, ambienti di prova, sviluppo o dimostrativi. È la configurazione predefinita e non richiede alcun software aggiuntivo (i dati vengono salvati nel file locale `troubletick.db`).
* **MySQL / MariaDB (Consigliato per ambienti di produzione e più strutturati)**: raccomandato per installazioni aziendali multi-utente ad alto volume. 
  > ⚠️ **Nota su MySQL:** Il server MySQL/MariaDB deve essere **preinstallato** e deve essere **già stato creato un database dedicato insieme a un utente applicativo** con i necessari permessi di lettura, scrittura e gestione schema (es. `CREATE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `INDEX`, `ALTER`). L'applicazione provvederà poi a inizializzare automaticamente tutte le tabelle al primo avvio.

### C. Risorse Hardware del Server (Consigliate)
* **Processore (CPU)**: Minimo 1 vCPU (Consigliati 2 o più Core).
* **Memoria RAM**:
  * Minimo: **1 GB** (per installazioni base con SQLite).
  * Consigliata: **2 - 4 GB** (per ambienti aziendali strutturati con MySQL e molti operatori concorrenti).
* **Spazio su Disco**: Minimo **5 - 10 GB** liberi (per l'ambiente virtuale Python, i file di database e la cartella degli allegati/documenti `app/uploads`).

### D. Rete, Firewall e Connettività
* **Accesso a Internet**: necessario al primissimo avvio per consentire il download automatico delle dipendenze Python tramite `pip`.
* **Porta TCP di ascolto**: per impostazione predefinita l'applicazione risponde sulla porta **`5001`**. Assicurati che il firewall del server consenta il traffico in ingresso su tale porta (oppure sulle porte `80`/`443` se utilizzi un Reverse Proxy come Nginx/Apache).

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

## 6. Configurazione e Scelta del Database
È possibile configurare il database sia modificando il file `config.json` prima del primo avvio, sia successivamente dall'interfaccia grafica in **"⚙️ Impostazioni" > "Database"**:
* **SQLite (Predefinito)**:
  * Non richiede alcuna configurazione: il file `troubletick.db` viene gestito in autonomia nella cartella del progetto.
* **MySQL / MariaDB (Consigliato per ambienti strutturati)**:
  * Assicurati che il server MySQL sia in esecuzione.
  * Crea il database e l'utente dedicato (es. tramite MySQL CLI o phpMyAdmin):
    ```sql
    CREATE DATABASE troubletick CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    CREATE USER 'troubletick_user'@'%' IDENTIFIED BY 'TuaPasswordSicura';
    GRANT ALL PRIVILEGES ON troubletick.* TO 'troubletick_user'@'%';
    FLUSH PRIVILEGES;
    ```
  * Inserisci i parametri di connessione (Host, Porta, Nome Database, Utente, Password) in **⚙️ Impostazioni** oppure direttamente nella sezione `database` di `config.json`.
  * *Ricorda che i cambi ai parametri del database richiedono il riavvio del server (chiudi e riapri lo script di avvio).*

## 7. Altre Impostazioni Globali
All'interno della pagina **"⚙️ Impostazioni"** potrai inoltre configurare:
* Il **Nome dell'Azienda** e l'indirizzo email di supporto.
* I **parametri SMTP** per l'eventuale invio di notifiche via email ai richiedenti e agli operatori.
* L'eventuale logo aziendale e i parametri visivi.

## 8. Sviluppo e Troubleshooting
* Se il server non si avvia correttamente, controlla di avere installato tutte le dipendenze Python richieste nel tuo `venv`.
* I file caricati dagli utenti (allegati nei ticket o nei movimenti di magazzino) vengono salvati nella cartella **`app/uploads`**. Non cancellare questa cartella se vuoi mantenere i file.
* I log per i tentativi di accesso falliti vengono salvati nel file di testo `failed_logins.log` nella radice del progetto per ragioni di audit.