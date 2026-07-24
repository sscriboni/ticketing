# Documentazione Troubletick (v7.4)

**Troubletick** è un portale di helpdesk e ticketing aziendale stand-alone progettato per centralizzare, tracciare e risolvere le richieste di supporto interno (IT, Manutenzione, Amministrazione, ecc.) e per gestire le richieste di materiali a magazzino.

## 👥 Ruoli Utente e Interfacce Dedicate

Il sistema prevede un controllo degli accessi basato su **6 livelli di ruolo**, ciascuno con permessi, visibilità, barra di navigazione e homepage dedicate:

### 1. Amministratore (`admin`)
* **Visibilità:** Globale.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket, Nuovo Ticket.
  - **Magazzino**: Inventario Magazzini, Richieste Materiale, Trasferimenti tra Magazzini, Log Magazzini.
  - **Avvisi**: Gestione Avvisi.
  - **Presenze**: Calendario Assenze, Calendario Presenze, Verifica copertura Servizi, Report Copertura Reparto, Calendario di Reparto, Servizi assegnati.
  - **Autopark**: Prenotazioni, Elenco Automezzi, Manutenzioni, Registro Viaggi.
  - **Configurazione**: Anagrafica Sedi, Reparti, Servizi, Categorie Materiali, Anagrafica Materiali, Gestione Autopark, Gestione Marche Automezzi, Import / Export JSON, Impostazioni Globali.
* **Homepage/Dashboard Dedicata:**
  - Mostra i contatori complessivi di sistema: *Ticket Aperti*, *Richieste Materiale*, *Materiali Sotto Soglia*, *Operatori da Approvare*, *Utenti da Approvare*, e *Veicoli*.
  - Bacheca avvisi e collegamenti rapidi a tutte le funzioni amministrative.
* **Permessi/Funzionalità:** Accesso completo e incondizionato a tutte le risorse aziendali, gestione utenti e log di sicurezza. Abilita o esclude qualunque auto della flotta aziendale dalla prenotazione.

### 2. Responsabile di Reparto (`responsabile`)
* **Visibilità:** Limitata al proprio Reparto di appartenenza.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket Reparto, Nuovo Ticket.
  - **Magazzino**: Inventario Reparto, Richieste Materiale, Trasferimenti tra Magazzini, Log Magazzini.
  - **Avvisi**: Bacheca.
  - **Presenze**: Calendario Assenze, Calendario Presenze, Verifica copertura Servizi, Report Copertura Reparto, Calendario di Reparto, Servizi assegnati.
  - **Autopark**: Prenotazioni.
  - **Report**: Copertura Personale, Stato Magazzini.
* **Homepage/Dashboard Dedicata:**
  - Cruscotto riassuntivo specifico per il reparto assegnato, contenente i contatori dei ticket aperti del reparto, delle richieste di materiale del magazzino di reparto, e degli operatori locali in attesa di approvazione.
* **Permessi/Funzionalità:** Gestione del personale e dei turni del reparto, approvazione ticket, monitoraggio dei report di copertura e delle giacenze del magazzino di reparto.

### 3. Operatore di Assistenza (`assistenza`)
* **Visibilità:** Limitata ai ticket e servizi del reparto o specifici per i servizi a lui assegnati.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket Servizi, Nuovo Ticket.
  - **Magazzino**: Inventario Magazzini, Richieste Materiale, Trasferimenti tra Magazzini, Log Magazzini.
  - **Avvisi**: Bacheca.
  - **Presenze**: Calendario Assenze, Calendario Presenze, Verifica copertura Servizi, Calendario di Reparto, Servizi assegnati.
  - **Autopark**: Prenotazioni.
* **Homepage/Dashboard Dedicata:**
  - Cruscotto focalizzato sul carico di lavoro dell'operatore, con i contatori dei propri ticket in carico, nuovi ticket del servizio e richieste merce.
  - Mostra la tabella dei **5 ticket più urgenti** da gestire in coda.
* **Permessi/Funzionalità:** Presa in carico ed evasione dei ticket di supporto, inserimento note operative (anche interne/nascoste), scarichi merce, carichi a scaffale e spedizioni.

### 4. Fleet Manager (`fleet_manager`)
* **Visibilità:** Limitata alla gestione del parco auto del proprio reparto (in anagrafica automezzi vede solo i veicoli assegnati al proprio reparto).
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket, Nuovo Ticket.
  - **Autopark**: Prenotazioni, Elenco Automezzi, Registro Viaggi.
* **Homepage/Dashboard Dedicata:**
  - Cruscotto riassuntivo specifico per la gestione della flotta del proprio reparto, contenente i contatori dei veicoli (*Disponibili*, *In Uso*, *In Manutenzione*) del reparto e il registro degli ultimi viaggi effettuati.
* **Permessi/Funzionalità:** Visualizzazione dello stato delle prenotazioni e cancellazione delle prenotazioni per veicoli appartenenti al proprio reparto.
  - **Gestione Esclusioni:** Può abilitare o escludere i veicoli aziendali dalle prenotazioni normali, ma **esclusivamente** per i mezzi appartenenti al proprio reparto di affiliazione.
  - **Anagrafica e Manutenzione:** Non ha permessi per inserire o modificare l'anagrafica dei veicoli, né per effettuare manutenzioni.

### 5. Global Fleet Manager (`global_fleet_manager`)
* **Visibilità:** Globale su tutti gli automezzi.
* **Barra di Navigazione (Navbar):**
  - **Ticket**: Elenco Ticket, Nuovo Ticket.
  - **Autopark**: Prenotazioni, Elenco Automezzi, Manutenzioni, Registro Viaggi.
* **Homepage/Dashboard Dedicata:**
  - Cruscotto riassuntivo globale per la flotta aziendale, con i contatori complessivi di tutti i veicoli (*Disponibili*, *In Uso*, *In Manutenzione*) e l'elenco degli ultimi viaggi a livello globale.
* **Permessi/Funzionalità:** Gestione completa delle anagrafiche dei veicoli (inserimento nuovi mezzi, modifiche) ed esecuzione delle manutenzioni/tagliandi.
  - **Gestione Esclusioni:** Può abilitare o escludere i veicoli dalle prenotazioni a livello globale, anche se i veicoli non sono assegnati ad alcun reparto.

### 6. Operatore Normale (`normale`)
* **Visibilità:** Nessuna sui ticket altrui o pannelli gestionali.
* **Barra di Navigazione (Navbar):**
  - **I Miei Ticket**: Le Mie Segnalazioni, Invia Nuova Richiesta.
  - **Autopark**: Prenotazioni.
* **Homepage/Dashboard Dedicata:**
  - Landing page pulita contenente due pulsanti per la creazione rapida di ticket (*Invia Nuova Richiesta*) o per l'elenco delle proprie segnalazioni (*Le Mie Richieste*), oltre allo storico dei ticket aperti dall'utente e la bacheca avvisi attiva.
* **Permessi/Funzionalità:** Apertura ticket, pianificazione delle proprie ferie/assenze in calendario e prenotazione/cancellazione autonoma di auto disponibili nel modulo Autopark.

---

## 🧩 Moduli Funzionali

L'applicativo è strutturato in diversi moduli che coprono l'intero ciclo di vita dell'assistenza tecnica e dell'organizzazione aziendale.

### 1. Comunicazioni e Avvisi (Bacheca Integrata)
* **Avvisi in Home Page:** Sistema di messaggistica visibile a tutti gli utenti direttamente nella pagina principale. 
* **Livelli di Gravità:** Gli avvisi possono essere impostati come Informativi (Info), Avvertimenti (Warning) o Critici (Danger), per catturare immediatamente l'attenzione.
* **Targetizzazione:** Gli admin possono pubblicare avvisi globali. Gli operatori di assistenza possono pubblicare avvisi targetizzati e visibili solo se l'utente seleziona il servizio di loro competenza. Gli avvisi supportano una programmazione con data di inizio e fine validità.

### 1. Modello di Segnalazione (Self-Service)
* **Apertura Ticket Pubblica:** Qualsiasi dipendente può aprire un ticket dalla home page senza necessità di login.
* **Classificazione:** Selezione del Reparto di destinazione (tra quelli abilitati a ricevere ticket) e del Servizio specifico.
* **Allegati:** Possibilità di allegare file (fino a 10MB, con blocco automatico di file eseguibili pericolosi).
* **Notifiche Email:** Invio asincrono di email transazionali all'apertura del ticket, sia all'utente (conferma con numero ticket) che agli operatori di competenza per avvisarli del nuovo carico di lavoro.

### 2. Gestione Operativa Ticket (Helpdesk)
* **Dashboard Ticket:** Elenco interattivo con contatori in tempo reale ("Nuovi", "Presi in carico", "I Miei Ticket", "I Miei Servizi").
* **Filtri Avanzati:** Ricerca per testo, stato, priorità, reparto, servizio o per ticket che includono richieste di materiali.
* **Ciclo di vita:** Transizioni di stato tracciate (Nuova ➔ Presa in carico ➔ Chiusa). **Vincolo di chiusura:** un ticket non può essere chiuso se vi sono richieste di materiale associate ancora da evadere (ovvero non ancora nello stato "evasa" o "annullata"). In tal caso, il pulsante di chiusura del ticket viene disabilitato e viene mostrato un avviso che invita ad evadere o annullare le richieste pendenti prima di procedere.
* **Gestione Note e Allegati:** Log testuale per ogni ticket con indicazione dell'autore e orario. Supporto per **note interne** (visibili solo agli operatori) e possibilità di allegare file in corso d'opera.
* **Trasferimento e Riassegnazione:** Riassegnazione di un ticket a un altro reparto/servizio con notifica automatica via email ai nuovi operatori incaricati.

### 3. Logistica e Magazzino
Il modulo Magazzino permette di gestire in modo centralizzato e tracciabile tutte le scorte e le movimentazioni aziendali. Di seguito il flusso tipico di gestione:

* **Catalogo Materiali:** Classificazione degli articoli per **Categorie** (es. *Materiale informatico*, *Materiale elettrico*).
* **Inventario Magazzini Unificato:** Visualizzazione in tempo reale di tutte le giacenze. Solo gli operatori assegnati a specifici magazzini (o gli Amministratori) possono visualizzare e operare sulle giacenze di competenza.

#### Flusso Operativo: Dal Ticket alla Consegna
1. **Apertura Ticket:** Un utente segnala un problema o una necessità (es. "Toner esaurito"). L'operatore prende in carico la segnalazione.
2. **Richiesta di Materiale:** L'operatore constata la necessità di un articolo hardware. Direttamente dal dettaglio del ticket, clicca su "Crea Nuova Richiesta".
   * Seleziona la Categoria, il Prodotto desiderato, la Quantità e la Sede di destinazione.
   * Il sistema analizza le giacenze e imposta la richiesta in stato "In Attesa" (se non c'è giacenza) o "Pronta per Scarico" (se disponibile).
3. **Evasione della Richiesta (Scarico):** L'operatore incaricato visualizza la coda delle "Richieste Materiale". Trovando la richiesta "Pronta per Scarico", clicca su **Esegui Scarico**. 
   * Si apre la maschera di scarico pre-compilata. Il magazziniere deve solo specificare la posizione fisica (es. lo scaffale o il lotto) da cui preleva il bene.
   * Confermando, i pezzi vengono sottratti, la richiesta diventa "Evasa" e nel ticket viene inserita automaticamente una nota di sistema per avvisare dell'avvenuta fornitura.

#### Gestione Carichi, Scarichi e Trasferimenti
* **Carico Manuale:** Per registrare l'arrivo di nuova merce (es. da fornitore), l'operatore cerca il prodotto nell'Inventario Magazzini e clicca su **Carico**. Specifica la data, la quantità e soprattutto la posizione fisica (scaffale/lotto). Può anche allegare un DDT PDF o una foto dell'articolo.
* **Scarico Manuale e Documento PDF:** Per prelievi rapidi slegati dai ticket, basta usare il bottone **Scarico**. Attivando l'opzione "Genera PDF", al termine dell'operazione viene fornito un **Documento di Consegna** stampabile per l'acquisizione della firma da parte di chi ritira il materiale.
* **Scarico Multiplo:** Per prelievi simultanei di più materiali da magazzini e posizioni differenti, gli operatori possono cliccare su **Scarico Multiplo** nella pagina Inventario. La form consente di aggiungere/rimuovere righe dinamicamente con controlli di stock integrati. È possibile generare e stampare un **Buono di Movimento** cumulativo su singolo foglio A4, che include note uniche, pre-seleziona l'opzione *Trasferimento* (con date in formato italiano e campi *Centro di Costo* / *Codice di Reparto* vuoti per la compilazione manuale da parte dell'operatore).
* **Log Movimenti (Scatola Nera):** Ogni carico, scarico o aggiornamento fotografico genera un log immutabile. La pagina "Log Magazzini" permette di filtrare l'intero storico aziendale per data, operatore, materiale o ricerca testuale (es. matricola).
* **Trasferimenti Tra Magazzini:** Se in fase di "Scarico" si seleziona come destinazione un altro magazzino anziché una sede, il sistema genera un trasferimento "In Consegna". L'operatore del magazzino destinatario visualizzerà un avviso e dovrà confermare fisicamente la ricezione cliccando su "Segna Arrivato", allineando le due giacenze in modo sicuro e tracciato.

### 4. Gestione Organizzativa (HR / Struttura)
* **Sedi:** Anagrafica delle sedi aziendali (es. filiali, uffici, smart working).
* **Reparti & Servizi:** Struttura ad albero. Ogni Reparto (es. *IT*) contiene N Servizi (es. *Assistenza PC*, *Credenziali*).
* **Calendario Assenze e Festività:** Modulo integrato per registrare ferie, malattie e permessi. Il sistema incrocia le date per mostrare a video un badge "Assente" qualora l'ultimo operatore che ha gestito il ticket fosse irreperibile quel giorno. Gli amministratori possono inoltre configurare festività globali a calendario.

### 5. Gestione Parco Automezzi (Autopark)
Il modulo Autopark consente una gestione centralizzata e autosufficiente dei veicoli aziendali, sia per il monitoraggio della flotta che per la prenotazione da parte degli impiegati.
* **Prenotazione Autonoma (Self-Service)**: Qualsiasi utente autenticato può accedere al cruscotto prenotazioni per richiedere un'auto disponibile, visualizzando in tempo reale il chilometraggio del veicolo e la sua sede attuale.
* **Registrazione Chilometri e Rientri**: All'avvio del viaggio, il sistema logga il chilometraggio di partenza (`km_iniziali`) prelevato automaticamente dalla scheda auto. Al rientro, l'utente chiude il viaggio inserendo i km finali (che aggiornano il chilometraggio cumulativo dell'auto), l'ora di rientro e la sede di consegna.
* **Cancellazione delle Prenotazioni**: Gli utenti possono annullare autonomamente le prenotazioni programmate, liberando istantaneamente il veicolo per altre richieste.
* **Gestione Manutenzioni e Registro Viaggi**: Gli amministratori, i Fleet Manager e i Global Fleet Manager possono registrare lo storico delle riparazioni o dei tagliandi in officina e monitorare il registro completo delle percorrenze.
* **Esclusione dalla Prenotazione (Gestione Flotta)**: Possibilità di escludere un veicolo dalla flotta prenotabile (es. per manutenzione straordinaria o assegnazione fissa). I standard Fleet Manager possono effettuare questa operazione esclusivamente per i mezzi appartenenti al proprio reparto di competenza, mentre i Global Fleet Manager (così come gli Amministratori) hanno visibilità e operatività globale su tutti i veicoli indipendentemente dal reparto assegnato.

### 6. Reportistica e Statistiche
* **Cruscotto Globale:** Grafico a torta degli stati di tutti i ticket (aperti, chiusi, ecc.).
* **Report di Copertura:** Matrice mensile generata automaticamente che incrocia le competenze degli operatori (servizi assegnati) con il calendario assenze, fornendo per ogni giorno del mese il numero di operatori attivi in ogni singolo servizio.
* **Report Stato Magazzini:** Consente ad amministratori e responsabili di reparto di monitorare lo stato delle scorte, incluse la disponibilità attuale, le consegne effettuate nel mese (scarichi) e i carichi effettuati nel mese. Permette la selezione dell'anno e del mese ed è protetto per escludere l'accesso agli operatori regolari o di assistenza.

### 7. Sicurezza e Amministrazione
* **Export / Import JSON Completo:** Funzionalità a 1-click per esportare l'intera anagrafica aziendale (comuni, sedi, reparti, servizi, magazzini, categorie, materiali, operatori) in un file JSON. Permette backup, migrazioni veloci o il popolamento istantaneo in caso di prima installazione. Include l'opzione per svuotare preventivamente il database.
* **Eliminazione Massiva Ticket:** Utilità GDPR-compliant per la pulizia selettiva dei database. L'amministratore può selezionare un intervallo di date ed eliminare in blocco tutti i ticket, le note e gli allegati ad essi associati.
* **Impostazioni Globali:** Modifica del nome dell'azienda e dell'email di supporto (salvati in modo persistente su file JSON).
* **Sicurezza Login ed Elenco Operatori:** Supporto login tramite *Username* o *Email*. Implementazione di un Log testuale automatico (`failed_logins.log`) per tracciare i tentativi falliti. L'elenco operatori (`/operatori` o `/admin/operatori`) è riservato esclusivamente all'amministratore e traccia per ciascun operatore il timestamp del suo ultimo login (formato italiano) e l'indirizzo IP del client (`ultimo_ip`).
* **Recupero Password ed Email Transazionali:** Sistema sicuro per la rigenerazione di password dimenticate tramite link temporizzato via email (scadenza 1 ora) e crittografia password (Bcrypt). Notifica asincrona via email anche in caso di abilitazione di un nuovo account da parte dell'Admin.

---

## ⚖️ Licenza d'Uso (EULA)

Il software è distribuito in modalità **Freeware Proprietario** regolato dal contratto di licenza presente nel file [LICENSE.txt](file:///g:/Il%20mio%20Drive/Progetti/ticketing/troubletick_standalone_windows_v7_4_sqlite/LICENSE.txt):
* **Gratuito:** Libero download e utilizzo per fini personali o interni aziendali.
* **Proprietario:** Sono vietate la ridistribuzione a fini commerciali, la modifica e la decompilazione del software.
* **Senza Responsabilità:** Fornito "così com'è" (AS IS) senza alcuna garanzia o responsabilità per danni diretti o indiretti.
* **Supporto:** Non è incluso alcun servizio di assistenza gratuita. L'autore si riserva il diritto di offrire pacchetti di supporto tecnico o servizi professionali a pagamento in futuro.