# Documentazione Troubletick — Guida Generale

**Troubletick** è un portale di helpdesk, ticketing e gestione risorse aziendali stand-alone, progettato per centralizzare, tracciare e gestire le richieste di supporto interno (IT, Manutenzione, Amministrazione, ecc.), la logistica di magazzino, la copertura del personale e il carpooling aziendale.

L'applicazione è sviluppata su stack moderno (FastAPI, Python 3.9+, Bootstrap 5, Jinja2) e supporta nativamente sia database locali **SQLite** che server di database relazionali **MySQL / MariaDB** e **PostgreSQL**.

---

## 👥 Ruoli Utente e Controllo Accessi (RBAC)

Il sistema implementa un controllo degli accessi basato sui ruoli (**Role-Based Access Control - RBAC**) articolato su **6 livelli di autorizzazione**, ciascuno dotato di dashboard, barra di navigazione e permessi specifici:

### 1. Amministratore (`admin`)
* **Visibilità:** Globale su tutti i moduli, sedi, reparti e dati aziendali.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket, Nuovo Ticket.
  - **Magazzino**: Inventario Magazzini, Richieste Materiale, Trasferimenti tra Magazzini, Log Magazzini.
  - **Avvisi**: Gestione Avvisi.
  - **Presenze**: Calendario Assenze, Calendario Presenze, Verifica Copertura Servizi, Report Copertura Reparto, Calendario di Reparto, Servizi Assegnati.
  - **Carpooling**: Prenotazioni, Elenco Automezzi, Manutenzioni, Rifornimenti, Registro Viaggi.
  - **Configurazione**: Anagrafica Sedi, Reparti, Servizi, Categorie Materiali, Anagrafica Materiali, Gestione Autopark, Gestione Marche Automezzi, Import / Export JSON, Impostazioni Globali.
* **Homepage / Dashboard Dedicata:**
  - Contatori globali in tempo reale: *Ticket Aperti*, *Richieste Materiale*, *Materiali Sotto Soglia*, *Operatori da Approvare*, *Utenti da Approvare*, *Veicoli*.
  - Bacheca avvisi attivi e collegamenti rapidi a tutte le funzioni di configurazione e amministrazione.
* **Permessi e Funzionalità:** Accesso completo e incondizionato, approvazione e gestione utenti, modifica ruoli, reset password, configurazione server SMTP, log di sicurezza, backup/restore JSON, pulizia massiva ticket (GDPR) e gestione esclusioni flotta carpooling su scala globale.

### 2. Responsabile di Reparto (`responsabile`)
* **Visibilità:** Limitata alle informazioni e al personale del proprio Reparto di appartenenza.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket Reparto, Nuovo Ticket.
  - **Magazzino**: Inventario Reparto, Richieste Materiale, Trasferimenti tra Magazzini, Log Magazzini.
  - **Avvisi**: Bacheca.
  - **Presenze**: Calendario Assenze, Calendario Presenze, Verifica Copertura Servizi, Report Copertura Reparto, Calendario di Reparto, Servizi Assegnati.
  - **Carpooling**: Prenotazioni.
  - **Report**: Copertura Personale, Stato Magazzini.
* **Homepage / Dashboard Dedicata:**
  - Cruscotto riassuntivo del reparto con i contatori dei ticket aperti del reparto, delle richieste di materiale per il magazzino di reparto e degli operatori locali in attesa di approvazione.
* **Permessi e Funzionalità:** Gestione del personale e delle presenze/assenze di reparto, approvazione nuovi operatori locali, monitoraggio dei report di copertura servizi e supervisione delle giacenze del magazzino di reparto.

### 3. Operatore di Assistenza (`assistenza`)
* **Visibilità:** Limitata ai ticket e ai servizi di competenza diretta o del proprio reparto.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket Servizi, Nuovo Ticket.
  - **Magazzino**: Inventario Magazzini, Richieste Materiale, Trasferimenti tra Magazzini, Log Magazzini.
  - **Avvisi**: Bacheca.
  - **Presenze**: Calendario Assenze, Calendario Presenze, Verifica Copertura Servizi, Calendario di Reparto, Servizi Assegnati.
  - **Carpooling**: Prenotazioni.
* **Homepage / Dashboard Dedicata:**
  - Cruscotto operativo focalizzato sul carico di lavoro individuale, con contatori dei ticket in carico, nuovi ticket del servizio e richieste merce pendenti.
  - Tabella prioritaria dei **5 ticket più urgenti** da gestire in coda.
* **Permessi e Funzionalità:** Presa in carico, gestione ed evasione dei ticket di supporto; inserimento note operative pubbliche e note interne riservate al team; esecuzione carichi a magazzino, scarichi merce (singoli o multipli) ed evasione richieste materiale.

### 4. Fleet Manager di Reparto (`fleet_manager`)
* **Visibilità:** Limitata al parco automezzi assegnato al proprio reparto.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket, Nuovo Ticket.
  - **Carpooling**: Prenotazioni, Elenco Automezzi, Registro Viaggi.
* **Homepage / Dashboard Dedicata:**
  - Cruscotto di reparto con i contatori dei veicoli (*Disponibili*, *In Uso*, *In Manutenzione*) del proprio reparto e il registro degli ultimi viaggi effettuati.
* **Permessi e Funzionalità:** Monitoraggio dello stato dei veicoli del reparto, annullamento delle prenotazioni per i mezzi di competenza e abilitazione/esclusione dei veicoli aziendali dalle prenotazioni normali (esclusivamente per i mezzi del proprio reparto). Non possiede permessi per modificare l'anagrafica dei veicoli o inserire manutenzioni fisiche.

### 5. Global Fleet Manager (`global_fleet_manager`)
* **Visibilità:** Globale su tutti gli automezzi della flotta aziendale.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket, Nuovo Ticket.
  - **Carpooling**: Prenotazioni, Elenco Automezzi, Manutenzioni, Rifornimenti, Registro Viaggi.
* **Homepage / Dashboard Dedicata:**
  - Cruscotto globale della flotta aziendale con contatori complessivi (*Disponibili*, *In Uso*, *In Manutenzione*), registro viaggi completo e stato manutenzioni.
* **Permessi e Funzionalità:** Gestione completa delle anagrafiche dei veicoli (inserimento nuovi mezzi, modifiche schede), inserimento e tracciamento delle manutenzioni e tagliandi, registro dei rifornimenti carburante e gestione delle esclusioni veicoli dalle prenotazioni a livello globale.

### 6. Utente / Operatore Normale (`normale`)
* **Visibilità:** Circoscritta esclusivamente ai propri ticket aperti e alle proprie prenotazioni di veicoli.
* **Barra di Navigazione (Navbar):**
  - **I Miei Ticket**: Le Mie Segnalazioni, Invia Nuova Richiesta.
  - **Carpooling**: Prenotazioni.
  - **Info**: Guida Utente, Privacy Policy.
* **Homepage / Dashboard Dedicata:**
  - Interfaccia essenziale e pulita con pulsanti per la creazione rapida di segnalazioni (*Invia Nuova Richiesta*), elenco delle proprie segnalazioni (*Le Mie Richieste*), storico dei ticket personali e bacheca avvisi attivi.
* **Permessi e Funzionalità:** Apertura di nuove segnalazioni di supporto, consultazione avanzamento dei propri ticket, registrazione delle proprie assenze/ferie a calendario e prenotazione/gestione autonoma dei veicoli della flotta carpooling.

---

## 🧩 Moduli Funzionali e Funzionalità Disponibili

### 1. Comunicazioni e Bacheca Avvisi Integrata
* **Bacheca Avvisi in Homepage:** Sistema centralizzato di messaggistica visibile a tutti gli utenti direttamente nella pagina principale o nelle dashboard dedicate.
* **Livelli di Gravità:** Classificazione cromatica dell'avviso in Informativo (*Info*), Avvertimento (*Warning*) o Critico (*Danger*), per garantire immediata visibilità.
* **Targetizzazione e Programmazione Temporale:** Gli amministratori possono pubblicare avvisi a livello globale. Gli operatori di assistenza possono pubblicare avvisi targetizzati e visibili solo quando un utente seleziona lo specifico servizio di competenza. Gli avvisi supportano una programmazione temporale con data di inizio e fine validità.

### 2. Modello di Segnalazione Self-Service e Ticketing Helpdesk
* **Apertura Ticket (Self-Service e Autenticata):** Possibilità per qualsiasi utente dipendente di inviare una richiesta sia tramite form pubblica (senza login) che dal proprio profilo autenticato.
* **Classificazione Strutturata:** Selezione obbligatoria della Sede aziendale, del Reparto di destinazione e del Servizio specifico di supporto.
* **Gestione Allegati Sicura:** Caricamento di allegati (immagini, PDF, documenti) con limite massimo di 10MB per file e blocco automatico preventivo dei file eseguibili ed estensioni potenzialmente pericolose.
* **Console Operativa Helpdesk:** Elenco interattivo con filtri rapidi e contatori in tempo reale (*Nuovi*, *Presi in carico*, *I Miei Ticket*, *I Miei Servizi*).
* **Filtri Avanzati e Ricerca:** Filtro per testo libero, codice ticket, stato, priorità, reparto, servizio o presenza di *Richieste Materiale*.
* **Ciclo di Vita e Transizioni di Stato:** Transizioni di stato tracciate (*Nuova* ➔ *Presa in carico* ➔ *Risolta* ➔ *Chiusa* / *Annullata* / *Sospesa*).
* **Vincolo Integrale di Chiusura Ticket:** Un ticket non può essere chiuso finché vi sono richieste di materiale collegate in stato sospeso (*Nuova* o *Pronta per Scarico*). Il sistema disabilita il pulsante di chiusura e mostra un avviso vincolante che richiede l'evasione o l'annullamento delle richieste pendenti.
* **Note Operative e Note Interne Reservate:** Registro degli interventi per ciascun ticket con timestamp e operatore. Supporto per **note interne** (visibili solo al personale di assistenza) per coordinamento tecnico riservato.
* **Riassegnazione e Trasferimento:** Facoltà di trasferire un ticket ad altro reparto o servizio con notifica automatica via email ai nuovi operatori incaricati.

### 3. Logistica, Magazzino e Movimentazione Merce
* **Catalogo Materiali e Categorie:** Classificazione degli articoli per categorie merceologiche (es. *Materiale Informatico*, *Materiale Elettrico*, *Consumabili*).
* **Inventario Magazzini Unificato:** Monitoraggio in tempo reale delle giacenze con segregazione dei permessi in base ai magazzini assegnati.
* **Integrazione Ticket-Magazzino (Richieste Materiale):** Creazione rapida di una richiesta merce direttamente dalla scheda del ticket. Il sistema verifica la giacenza attuale e imposta automaticamente lo stato in *Pronta per Scarico* (se il bene è presente) o *In Attesa* (se la giacenza è zero o insufficiente).
* **Evasione e Scarico Materiale:** Maschera di scarico pre-compilata con indicazione obbligatoria della posizione fisica (scaffale, lotto, vano). L'evasione aggiorna la giacenza a magazzino, varia lo stato della richiesta in *Evasa* e inserisce una nota automatica di riscontro nel ticket.
* **Scarico Multiplo e Buono di Movimento (PDF):** Interfaccia per scarichi simultanei di più prodotti da magazzini e ubicazioni diverse. Supporta controlli di disponibilità dinamici e consente la generazione e la stampa in formato **PDF A4** del **Buono di Movimento** (con date in formato italiano, note operative e spazi per la firma di consegna/ricevuta).
* **Scarico Singolo e Documento di Consegna (PDF):** Possibilità di stampare una ricevuta di scarico immediata per la sottoscrizione autografa del richiedente.
* **Carico Merci e Documenti di Trasporto (DDT):** Registrazione delle entrate merci con quantità, lotto, posizione di stoccaggio e possibilità di allegare la scansione del DDT o la fotografia del bene.
* **Trasferimenti tra Magazzini:** Flusso inter-magazzino guidato con stato *In Consegna* e presa in carico da parte del magazziniere ricevente tramite funzione *Segna Arrivato*, garantendo la perfetta quadratura delle giacenze.
* **Log Magazzini (Registro Immutabile):** Log storico di tutte le operazioni di carico, scarico, rettifica e trasferimento, filtrabile per intervallo di date, operatore, materiale o ricerca testuale (es. numero di matricola/serial number).
* **Monitoraggio Scorte Minime e Report Stato Magazzini:** Avvisi visivi automatici per i prodotti con giacenza inferiore alla soglia minima. Generazione del report mensile e annuale dei movimenti di carico, scarico e giacenza residua.

### 4. Presenze, Assenze e Verifica Copertura Servizi
* **Calendario Assenze e Ferie:** Modulo per la registrazione e il tracciamento delle assenze (ferie, permessi, malattie) di tutto il personale aziendale.
* **Indicatore di Assenza Operatore sul Ticket:** Qualora l'ultimo operatore che ha gestito un ticket sia assente nella giornata corrente, il sistema mostra automaticamente un badge "Assente" per informare il team della sua irreperibilità temporanea.
* **Gestione Festività Nazionali ed Aziendali:** Configurazione da parte degli amministratori delle giornate festive a calendario.
* **Matrice Copertura Servizi e Report Reparto:** Strumento di analisi che incrocia le assenze con le competenze e i servizi assegnati a ciascun operatore, producendo un report mensile che evidenzia la forza lavoro disponibile giorno per giorno per ciascun servizio.

### 5. Parco Automezzi, Carpooling e Rifornimenti (Autopark)
* **Anagrafica Flotta e Marche Automezzi:** Scheda dettagliata dei veicoli con targa, marca, modello, tipo di alimentazione, sede di stazionamento, reparto proprietario, chilometraggio cumulativo e stato (*Disponibile*, *In Uso*, *In Manutenzione*, *Escluso*).
* **Prenotazione Autonoma Self-Service:** Tabellone interattivo delle disponibilità dove gli utenti autenticati possono prenotare un veicolo per specifiche date e orari.
* **Gestione Flusso Viaggio (Check-in / Check-out):**
  - **Partenza:** Il sistema preleva i km iniziali dalla scheda dell'auto.
  - **Rientro:** L'utente inserisce i km finali, l'orario effettivo di riconsegna e la sede di stazionamento. Il chilometraggio dell'auto viene aggiornato automaticamente.
  - **Modifica Viaggi Registrati:** Utenti normali e operatori possono modificare a posteriori i propri viaggi registrati per correggere eventuali errori di inserimento di km, orari o sedi.
* **Registro Rifornimenti Carburante:** Modulo per la tracciabilità delle schede carburante e delle uscite per rifornimento. Permette di registrare data, veicolo, km al momento del rifornimento, litri erogati, importo complessivo (€), tipo di carburante e metodo di pagamento utilizzato.
* **Gestione Manutenzioni e Tagliandi:** Registro delle riparazioni ordinarie e straordinarie con indicazione di costi, officina esecutrice e descrizione degli interventi svolti.
* **Registro Viaggi e Percorrenze:** Storico analitico di tutte le prenotazioni e dei chilometri percorsi da ciascun dipendente con funzioni di modifica e cancellazione tracciate.
* **Esclusioni Flotta dalla Prenotazione:** Funzione per escludere temporaneamente o permanentemente un mezzo dalle prenotazioni pubbliche (es. per guasti, manutenzione o uso esclusivo). I Fleet Manager di reparto possono operare sui mezzi del proprio reparto, mentre i Global Fleet Manager e gli Admin su tutta la flotta aziendale.

### 6. Sistema di Email Transazionali e Scheduler (Morning Recap)
* **Email Transazionali Automatiche:** Invio asincrono di notifiche email per l'apertura di nuovi ticket, la presa in carico, il trasferimento ad altri reparti, l'attivazione di nuovi account utenti e l'invio di link temporizzati per il reset della password.
* **Scheduler Riepilogo Mattutino (Morning Recap):** Servizio in background che invia automaticamente ogni mattina un'email di sintesi ai responsabili e agli operatori con l'elenco dei ticket aperti, in carico o in attesa di risoluzione.

### 7. Amministrazione, Backup e Sicurezza
* **Import / Export JSON Integrale:** Esportazione e importazione a 1-click dell'intero assetto aziendale (sedi, reparti, servizi, magazzini, categorie materiali, materiali, automezzi e account operatori). Include un'opzione di sicurezza per svuotare il database prima del ripristino.
* **Eliminazione Massiva Ticket (GDPR Compliance):** Strumento per la pulizia periodica e selettiva del database che consente all'amministratore di rimuovere massivamente i ticket e le note collegate compresi in un determinato intervallo di date.
* **Gestione Utenti ed Registro Accessi:** Gestione completa delle credenziali e dei ruoli. Tracciamento automatico del timestamp dell'ultimo login (formato italiano) e dell'indirizzo IP del client (`ultimo_ip`).
* **Configurazione Server SMTP ed Impostazioni Globali:** Modulo amministrativo per personalizzare il titolo dell'applicazione, il testo del footer, l'email di supporto e i parametri della connessione SMTP (Host, Porta, TLS/SSL, Utente, Password e Mittente).
* **Recupero Password Sicuro:** Generazione di token temporizzati univoci inviati via email con validità di 1 ora e hashing delle password tramite algoritmo crittografico sicuro (Bcrypt).
* **Log di Sicurezza e Audit:** Registro dei tentativi di accesso falliti (`failed_logins.log`) e log degli eventi di sistema (`app_events.log`).

---

## ⚖️ Licenza d'Uso (EULA)

Il software è distribuito secondo il modello **Freeware Proprietario**, disciplinato dalle condizioni contenute nel file di licenza incluso ([LICENSE.txt](file:///g:/Il%20mio%20Drive/Progetti/ticketing/troubletick/static/LICENSE.txt)):

* **Gratuità d'Uso:** Download ed utilizzo gratuiti per finalità personali o per uso interno aziendale.
* **Proprietà Riservata:** Sono vietate la ridistribuzione a fini commerciali, la rivendita, la modifica non autorizzata e la decompilazione del codice sorgente.
* **Esclusione di Garanzia:** Il software viene fornito "così com'è" (*AS IS*), senza alcuna garanzia esplicita o implicita ed escludendo qualsiasi responsabilità per danni diretti o indiretti.
* **Supporto Tecnico:** Non è incluso alcun servizio di assistenza tecnica gratuita garantita. L'autore si riserva la facoltà di erogare eventuali servizi di supporto professionale o personalizzazioni su richiesta.