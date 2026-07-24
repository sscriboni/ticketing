# Guida alla Gestione del Parco Auto (Autopark)

Questa guida descrive il funzionamento, i ruoli e le procedure operative del modulo **Autopark**, il sistema per la prenotazione e il monitoraggio dei veicoli aziendali (auto e furgoni).

Il sistema gestisce l'intero ciclo di vita di un viaggio: dalla prenotazione (standard o istantanea) alla registrazione della partenza, della pausa, fino alla riconsegna fisica del mezzo con aggiornamento dello stato dell'auto e dei chilometri percorsi.

---

## 🛠️ Architettura e Avvio dell'Applicazione

L'applicazione Autopark è configurata per funzionare in parallelo con l'applicazione web principale (Helpdesk/Troubleticket):
* **File di Erogazione**: La webapp dell'Autopark è erogata in modo indipendente dal file [appautopark.py](file:///g:/Il%20mio%20Drive/Progetti/ticketing/troubletick_standalone_windows_v7_4_sqlite/app/appautopark.py).
* **Porta e Avvio**: Viene eseguita in parallelo all'applicazione principale ed erogata su una porta di rete diversa (solitamente la porta **`5002`**, avviata tramite Uvicorn con `uvicorn appautopark:app --host 0.0.0.0 --port 5002`). L'applicazione principale di troubleticket gira invece sulla propria porta dedicata (porta `5000` o `5001`).
* **Database Condiviso**: Entrambe le applicazioni si collegano allo stesso database SQLite locale (`troubletick.db`), garantendo la sincronia in tempo reale delle tabelle utenti, reparti, sedi e dei viaggi della flotta.
* **Script di Avvio**: Su Windows, l'avvio in parallelo è facilitato dal file batch dedicato [startautopark.bat](file:///g:/Il%20mio%20Drive/Progetti/ticketing/troubletick_standalone_windows_v7_4_sqlite/startautopark.bat).

---

## 1. Sezione Utilizzatore (Dipendenti e Conducenti)
Ogni utente abilitato nel sistema (con ruoli come `normale`, `assistenza` o `responsabile`) ha accesso alla console di prenotazione e di viaggio per gestire i propri spostamenti di lavoro.

### A. Prenotazione Standard (Pianificata)
La prenotazione consente di bloccare un veicolo in anticipo per un viaggio futuro:
1. **Selezione Sede di Partenza**: L'utilizzatore sceglie da quale sede aziendale desidera ritirare l'auto.
2. **Selezione Data e Ora**: Vengono inserite la data del viaggio, l'ora di partenza prevista e l'ora di riconsegna prevista (la data e l'ora di partenza devono essere obbligatoriamente nel futuro rispetto al momento attuale, e l'ora di riconsegna deve essere successiva a quella di partenza).
3. **Selezione Veicolo**: In base alla sede selezionata, il sistema mostra solo i veicoli **attualmente presenti in quella sede** e contrassegnati come **Disponibili**. 
   * Vengono visualizzati i km attuali e la posizione.
   * I veicoli occupati in quella fascia oraria o esclusi dalla flotta non sono selezionabili.
4. **Convalida Sovrapposizioni**: Il sistema impedisce automaticamente le prenotazioni se:
   * Il veicolo è già prenotato da un altro utente nella stessa fascia oraria.
   * Il conducente indicato ha già un'altra prenotazione attiva contemporaneamente.

### B. Prenotazione Istantanea (Partenza Immediata)
Se l'utilizzatore ha la necessità di partire immediatamente senza aver prenotato in anticipo:
1. Può attivare la modalità **Prenotazione Istantanea** cliccando su *Registra Viaggio* &rarr; *Avvia Viaggio Istantaneo*.
2. Il sistema imposta la data odierna e l'orario attuale come ora di partenza effettiva.
3. L'utilizzatore sceglie il veicolo disponibile nella propria sede, indica l'ora di riconsegna prevista, le note di destinazione e avvia subito il viaggio.

### C. Gestione del Viaggio (In Corso, Pausa e Chiusura)
Quando la prenotazione diventa attiva, l'utilizzatore gestisce lo stato tramite la bacheca:
* **Avvio Viaggio**: Cliccando su **Registra Viaggio**, il sistema registra l'ora esatta di partenza effettiva. Lo stato del viaggio passa a *In Corso*.
* **Pausa / Ripresa**: Durante il tragitto, il conducente può mettere in pausa il viaggio (da utilizzare obbligatoriamente nel caso in cui il veicolo debba rimanere parcheggiato o fermo per più di un'ora) contrassegnando il veicolo come *In Pausa*. Lo stato può essere ripristinato a *In Corso* con un click. Il sistema calcola e accumula automaticamente la durata complessiva delle pause (in minuti), mostrandola poi nel registro dei viaggi storici.
* **Annulla Viaggio (Errore di Avvio)**: Se l'utilizzatore ha avviato il viaggio per errore, può cliccare su **Annulla**. Questo resetta l'ora di partenza effettiva e l'eventuale stato di pausa, ripristinando il viaggio allo stato di semplice prenotazione attiva/futura.
* **Termina Viaggio (Chiusura)**: Al rientro, l'utilizzatore clicca su **Termina** e compila il modulo di rientro obbligatorio:
  * **Ora Rientro**: L'orario effettivo di riconsegna (deve essere inserito dall'utente e non può essere inferiore o uguale a quello di partenza).
  * **KM Finali**: L'odometro finale registrato (il sistema verifica che non sia inferiore ai km iniziali registrati alla partenza).
  * **Sede di Rientro**: La sede in cui viene parcheggiato il veicolo (se diversa da quella di partenza, la posizione attuale del veicolo viene aggiornata automaticamente nel database).
  * **Note Rientro**: Note facoltative su problemi riscontrati, rifornimento o anomalie.
  * **Controllo Data**: Se l'utente termina il viaggio in una data diversa rispetto a quella di partenza, il sistema mostra un avviso, registrando comunque la data di fine uguale alla data di partenza. Lo stato dell'automezzo viene riportato a *Disponibile*.

---

## 2. Sezione Fleet Manager
Il ruolo `fleet_manager` gestisce e coordina il parco veicoli assegnato al proprio specifico reparto di appartenenza.

### A. Limitazione di Visibilità e Reparto
* Un Fleet Manager ha visibilità ed operatività circoscritta al proprio reparto: nell'anagrafica automezzi e nel registro prenotazioni può visualizzare e gestire esclusivamente i veicoli e i viaggi associati al proprio reparto.

### B. Operatività del Fleet Manager
* **Gestione Schede Automezzi (Reparto)**: Può inserire nuovi veicoli (che verranno automaticamente assegnati al suo reparto), nonché modificare ed eliminare le schede degli automezzi assegnati al proprio reparto.
* **Prenotazione per Terzi (Reparto)**: Può inserire prenotazioni a nome di altri colleghi appartenenti al suo stesso reparto. In fase di prenotazione, compilerà il campo *Email Conducente* con l'indirizzo del dipendente interessato. Il sistema convalida che il conducente appartenga allo stesso reparto del Fleet Manager.
* **Esclusione Veicoli di Reparto**: Può escludere temporaneamente i veicoli assegnati al suo reparto dalle prenotazioni degli utenti comuni (es. per fermi tecnici o assegnazioni speciali), oppure riabilitarli quando tornano idonei.
* **Annullamento Prenotazioni**: Ha la facoltà di cancellare o eliminare le prenotazioni programmate o i viaggi passati esclusivamente per gli utenti del proprio reparto.

---

## 3. Sezione Global Fleet Manager e Amministratore
L'Amministratore (`admin`) e il `global_fleet_manager` hanno il controllo completo, incondizionato e globale su tutta la flotta aziendale e su tutte le prenotazioni del sistema.

### A. Gestione Globale e Anagrafiche
* **Nessun Limite di Reparto**: Hanno visibilità su tutti i veicoli e le prenotazioni a livello aziendale, indipendentemente dal reparto assegnato.
* **Prenotazione per Qualsiasi Utente**: Possono effettuare prenotazioni per conto di qualsiasi dipendente attivo nel sistema inserendo la sua email, senza alcuna restrizione di reparto.
* **Anagrafica Flotta**: Hanno i permessi esclusivi per creare, modificare ed eliminare le schede dei veicoli, impostando targa, modello, alimentazione, tipo di proprietà (proprietà o noleggio a lungo termine), canone mensile, chilometri iniziali e sede/reparto di assegnazione.
* **Gestione Tipi Manutenzione**: Hanno l'esclusiva per creare, modificare e rimuovere i tipi di manutenzione e le relative regole di scadenza, associandoli poi ai diversi veicoli della flotta.

### B. Gestione Manutenzioni e Fermo Tecnico
* Solo questi ruoli possono registrare le **Manutenzioni** (tagliandi, cambio gomme, riparazioni d'officina):
  * All'apertura di una manutenzione, viene registrata la data/ora di inizio, il luogo e i km registrati.
  * **Manutenzione Bloccante**: Se contrassegnata come *Bloccante*, lo stato del veicolo passa automaticamente a **In Manutenzione**, impedendone la prenotazione o il ritiro da parte di qualsiasi utilizzatore.
  * **Chiusura Manutenzione**: Al ritiro del veicolo dall'officina, viene registrata la data/ora di fine e i km finali dell'intervento, riallineando lo stato dell'automezzo a *Disponibile*.

### C. Gestione Esclusioni ed Eliminazioni
* **Esclusioni Globali**: Possono escludere o includere qualunque veicolo della flotta aziendale dal pannello prenotazioni.
* **Eliminazione Prenotazioni e Storico**: Possono cancellare o rettificare qualunque prenotazione attiva o viaggio già completato nello storico per liberare la flotta o correggere errori di inserimento.

---

## 4. Legenda Stati del Veicolo e del Viaggio

### Stati del Veicolo (`automezzi.stato`)
*   **Disponibile**: Il veicolo è pronto per essere prenotato ed utilizzato presso la sede indicata come posizione attuale.
*   **In Uso**: Il veicolo ha un viaggio attivo in corso (partito e non ancora riconsegnato).
*   **In Manutenzione**: Il veicolo è fermo in officina per una manutenzione bloccante registrata a sistema.

### Stati del Viaggio (`viaggi_automezzi`)
| Stato Viaggio | Condizioni nel Database | Descrizione Visiva |
|:---:|---|---|
| **Prenotato** | Ora partenza effettiva `NULL`, Ora arrivo `NULL`, data futura | Il veicolo è riservato ma il viaggio non è ancora iniziato. |
| **In Corso** | Ora partenza effettiva compilata, Ora arrivo `NULL`, `in_pausa = 0` | Il viaggio è iniziato e il conducente è alla guida del veicolo. |
| **In Pausa** | Ora partenza effettiva compilata, Ora arrivo `NULL`, `in_pausa = 1` | Il viaggio è in corso ma momentaneamente fermo. |
| **Completato**| Ora arrivo compilata | Il veicolo è stato riconsegnato nella sede indicata e i km sono stati aggiornati. |
