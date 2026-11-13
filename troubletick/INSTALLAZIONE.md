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

## 3. Installazione ed Esecuzione Manuale (Linux / macOS)
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

## 4. Configurazione come Servizio di Sistema su Oracle Linux (Systemd)

In ambienti di produzione basati su **Oracle Linux** (compatibile con RHEL, Rocky Linux e AlmaLinux), è vivamente consigliato eseguire Troubletick come servizio di sistema in background gestito da **Systemd**, garantendo l'avvio automatico all'accensione del server e il riavvio automatico in caso di imprevisti.

### A. Installazione Prerequisiti di Sistema
Installa Python 3, il gestore pacchetti `pip` e gli strumenti di compilazione tramite `dnf`:
```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip python3-devel git
```
*(Nota: su Oracle Linux 8 e 9 è possibile installare versioni specifiche come Python 3.11 con `sudo dnf install -y python3.11 python3.11-pip`).*

### B. Creazione dell'Utente Dedicato e Directory Applicativa
Per motivi di sicurezza (principio del minor privilegio), non eseguire il servizio come `root`. Crea un utente di sistema dedicato senza shell di login:
```bash
sudo useradd -r -s /sbin/nologin -d /opt/troubletick troubletick
```

Posiziona i file dell'applicativo nella cartella di destinazione (es. `/opt/troubletick`):
```bash
# Copia o clona la cartella del progetto in /opt/troubletick
sudo cp -r /percorso/sorgente/ticketing/troubletick /opt/troubletick

# Assegna la proprietà all'utente dedicato
sudo chown -R troubletick:troubletick /opt/troubletick
```

### C. Creazione del Virtual Environment e Installazione Dipendenze
Genera l'ambiente virtuale ed esegui l'installazione dei requisiti con l'utente `troubletick`:
```bash
cd /opt/troubletick
sudo -u troubletick python3 -m venv venv
sudo -u troubletick /opt/troubletick/venv/bin/pip install --upgrade pip
sudo -u troubletick /opt/troubletick/venv/bin/pip install -r app/requirements.txt
```

### D. Creazione del File di Servizio Systemd (`troubletick.service`)
Crea un nuovo file unit in `/etc/systemd/system/`:
```bash
sudo nano /etc/systemd/system/troubletick.service
```

Inserisci la configurazione seguente (adatta i percorsi se differenti da `/opt/troubletick`):
```ini
[Unit]
Description=Troubletick Helpdesk Service
After=network.target

[Service]
Type=simple
User=troubletick
Group=troubletick
WorkingDirectory=/opt/troubletick/app
ExecStart=/opt/troubletick/venv/bin/uvicorn main:app --host 0.0.0.0 --port 5001 --workers 2
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

# Hardening di sicurezza
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/troubletick

[Install]
WantedBy=multi-user.target
```

### E. Attivazione e Gestione del Servizio
Ricarica le configurazioni di systemd, abilita il servizio all'avvio del server e avvialo:
```bash
# Ricarica i file di configurazione dei servizi
sudo systemctl daemon-reload

# Abilita l'avvio automatico al boot
sudo systemctl enable troubletick.service

# Avvia il servizio
sudo systemctl start troubletick.service

# Controlla lo stato di esecuzione
sudo systemctl status troubletick.service
```

#### Comandi Rapidi di Gestione e Manutenzione:
* **Riavviare il servizio:**
  ```bash
  sudo systemctl restart troubletick.service
  ```
* **Arrestare il servizio:**
  ```bash
  sudo systemctl stop troubletick.service
  ```
* **Seguire i log in tempo reale:**
  ```bash
  sudo journalctl -u troubletick.service -f
  ```
* **Visualizzare gli ultimi log dettagliati:**
  ```bash
  sudo journalctl -u troubletick.service -e -x --no-pager
  ```

### F. Configurazione del Firewall (`firewalld`)
Su Oracle Linux il firewall di sistema (`firewalld`) è attivo di default. Se desideri raggiungere Troubletick direttamente sulla porta `5001`, aprila con:
```bash
sudo firewall-cmd --permanent --add-port=5001/tcp
sudo firewall-cmd --reload
```

### G. Configurazione di SELinux
Su Oracle Linux **SELinux** è attivo in modalità restrittiva (`Enforcing`). Per garantire il corretto funzionamento:

1. **Permessi di accesso ai file applicativi:**
   ```bash
   sudo semanage fcontext -a -t usr_t "/opt/troubletick(/.*)?"
   sudo restorecon -Rv /opt/troubletick
   ```
2. **Abilitazione connessioni di rete per eventuale Reverse Proxy:**
   Se utilizzi Apache o Nginx come frontend, consenti la connessione proxy verso la porta interna di Troubletick:
   ```bash
   sudo setsebool -P httpd_can_network_connect 1
   ```

### H. Integrazione con Apache HTTPD come Reverse Proxy (Consigliato per Produzione)
Se desideri esporre Troubletick tramite le porte standard `80` (HTTP) o `443` (HTTPS) con dominio dedicato:

1. Installa Apache HTTP Server:
   ```bash
   sudo dnf install -y httpd
   ```
2. Crea la configurazione del VirtualHost, ad esempio `/etc/httpd/conf.d/troubletick.conf`:
   ```apache
   <VirtualHost *:80>
       ServerName ticket.tua-azienda.it

       ProxyPreserveHost On
       ProxyPass / http://127.0.0.1:5001/
       ProxyPassReverse / http://127.0.0.1:5001/

       ErrorLog /var/log/httpd/troubletick_error.log
       CustomLog /var/log/httpd/troubletick_access.log combined
   </VirtualHost>
   ```
3. Verifica la configurazione e ricarica il server web:
   ```bash
   sudo httpd -t
   sudo systemctl enable --now httpd
   sudo systemctl reload httpd
   ```

## 5. Primo Accesso e Credenziali Predefinite
Una volta che la finestra del terminale ti indicherà che *Uvicorn è in esecuzione*, apri un browser e collegati all'indirizzo:
**http://localhost:5001**

1. Clicca sul pulsante **"Area Operatori"** in alto a destra.
2. Il sistema al primissimo avvio crea automaticamente un account Amministratore (con visibilità globale) per permetterti di accedere. Utilizza le seguenti credenziali:
   * **Username:** `admin`
   * **Password:** `admin`

> ⚠️ **IMPORTANTE:** Per motivi di sicurezza, ti consigliamo di cambiare subito la password dell'amministratore. Vai in **Admin > Operatori**, cerca l'utente *admin*, clicca su "Modifica" e digita una nuova password.

## 6. Configurazione Iniziale (Importazione Massiva)
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

## 7. Configurazione e Scelta del Database
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

## 8. Altre Impostazioni Globali
All'interno della pagina **"⚙️ Impostazioni"** potrai inoltre configurare:
* Il **Nome dell'Azienda** e l'indirizzo email di supporto.
* I **parametri SMTP** per l'eventuale invio di notifiche via email ai richiedenti e agli operatori.
* L'eventuale logo aziendale e i parametri visivi.

## 9. Sviluppo e Troubleshooting
* Se il server non si avvia correttamente, controlla di avere installato tutte le dipendenze Python richieste nel tuo `venv`.
* I file caricati dagli utenti (allegati nei ticket o nei movimenti di magazzino) vengono salvati nella cartella **`app/uploads`**. Non cancellare questa cartella se vuoi mantenere i file.
* I log per i tentativi di accesso falliti vengono salvati nel file di testo `failed_logins.log` nella radice del progetto per ragioni di audit.