# Documentazione Troubletick (v7.4)

**Troubletick** è un portale di helpdesk e ticketing aziendale stand-alone progettato per centralizzare, tracciare e risolvere le richieste di supporto interno (IT, Manutenzione, Amministrazione, ecc.) e per gestire le richieste di materiali a magazzino.

## 👥 Ruoli Utente

Il sistema prevede un controllo degli accessi basato su **4 livelli di ruolo**, ciascuno con permessi e visibilità specifici:

1. **Amministratore (`admin`)**
   * **Visibilità:** Globale.
   * **Permessi:** Accesso completo al "Pannello Amministrativo". Può creare/modificare operatori, reparti, servizi, sedi, magazzini, categorie e materiali. Gestisce importazione/esportazione massiva in JSON, l'eliminazione massiva di ticket per data, le festività a calendario e gli avvisi globali in homepage.
   * **Esempio pratico:** L'Amministratore esporta la configurazione anagrafica aziendale in JSON per backup, inserisce una nuova Festività nel calendario (es. "Festa Patronale"), e invia un Avviso in bacheca con gravità "Danger" ("Server offline per manutenzione") visibile a tutti.

2. **Responsabile di Reparto (`responsabile`)**
   * **Visibilità:** Limitata al proprio Reparto di appartenenza.
   * **Permessi:** Può visualizzare tutti i ticket assegnati al proprio reparto (anche se non assegnati direttamente ai suoi servizi), monitorare le performance, vedere l'elenco degli operatori del proprio team e accedere al "Report di Copertura" mensile per incrociare le presenze/assenze con i servizi coperti. Gestisce la merce del proprio magazzino.
   * **Esempio pratico:** Il Responsabile IT controlla il Report di Copertura di Agosto per assicurarsi che il servizio "Assistenza PC" sia sempre presidiato da almeno un operatore, organizzando così i turni di ferie del proprio team.

3. **Operatore di Assistenza (`assistenza`)**
   * **Visibilità:** Limitata ai ticket del proprio Reparto o specifici per i Servizi a lui assegnati.
   * **Permessi:** È il ruolo operativo standard. Può prendere in carico i ticket, inserire note operative (anche interne/nascoste all'utente), gestire magazzino e trasferimenti merce, trasferire ticket ad altri reparti/servizi e pubblicare avvisi legati ai propri servizi.
   * **Esempio pratico:** Mario Rossi riceve un ticket per un toner esaurito. Effettua uno "scarico" dal suo Magazzino, allega una foto della bolla di prelievo, chiude il ticket e crea un "Trasferimento" di toner verso la filiale di Milano. Inoltre, pubblica un avviso in Home Page: "I toner per la stampante X sono in ritardo di consegna".

4. **Operatore Normale (`normale`)**
   * **Visibilità:** Nessuna sui ticket.
   * **Permessi:** Ruolo base, usato per utenti che non devono gestire l'helpdesk ma necessitano di un account per altre funzioni (es. inserimento ferie nel calendario, visualizzazione della bacheca avvisi).
   * **Esempio pratico:** Un dipendente amministrativo accede al sistema esclusivamente per dichiarare 3 giorni di ferie nel calendario, in modo che l'amministratore possa tenere traccia della sua assenza.

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
* **Log Movimenti (Scatola Nera):** Ogni carico, scarico o aggiornamento fotografico genera un log immutabile. La pagina "Log Magazzini" permette di filtrare l'intero storico aziendale per data, operatore, materiale o ricerca testuale (es. matricola).
* **Trasferimenti Tra Magazzini:** Se in fase di "Scarico" si seleziona come destinazione un altro magazzino anziché una sede, il sistema genera un trasferimento "In Consegna". L'operatore del magazzino destinatario visualizzerà un avviso e dovrà confermare fisicamente la ricezione cliccando su "Segna Arrivato", allineando le due giacenze in modo sicuro e tracciato.

### 4. Gestione Organizzativa (HR / Struttura)
* **Sedi:** Anagrafica delle sedi aziendali (es. filiali, uffici, smart working).
* **Reparti & Servizi:** Struttura ad albero. Ogni Reparto (es. *IT*) contiene N Servizi (es. *Assistenza PC*, *Credenziali*).
* **Calendario Assenze e Festività:** Modulo integrato per registrare ferie, malattie e permessi. Il sistema incrocia le date per mostrare a video un badge "Assente" qualora l'ultimo operatore che ha gestito il ticket fosse irreperibile quel giorno. Gli amministratori possono inoltre configurare festività globali a calendario.

### 5. Reportistica e Statistiche
* **Cruscotto Globale:** Grafico a torta degli stati di tutti i ticket (aperti, chiusi, ecc.).
* **Report di Copertura:** Matrice mensile generata automaticamente che incrocia le competenze degli operatori (servizi assegnati) con il calendario assenze, fornendo per ogni giorno del mese il numero di operatori attivi in ogni singolo servizio.

### 6. Sicurezza e Amministrazione
* **Export / Import JSON Completo:** Funzionalità a 1-click per esportare l'intera anagrafica aziendale (comuni, sedi, reparti, servizi, magazzini, categorie, materiali, operatori) in un file JSON. Permette backup, migrazioni veloci o il popolamento istantaneo in caso di prima installazione. Include l'opzione per svuotare preventivamente il database.
* **Eliminazione Massiva Ticket:** Utilità GDPR-compliant per la pulizia selettiva dei database. L'amministratore può selezionare un intervallo di date ed eliminare in blocco tutti i ticket, le note e gli allegati ad essi associati.
* **Impostazioni Globali:** Modifica del nome dell'azienda e dell'email di supporto (salvati in modo persistente su file JSON).
* **Sicurezza Login:** Supporto login tramite *Username* o *Email*. Implementazione di un Log testuale automatico (`failed_logins.log`) per tracciare orario, IP e utente dei tentativi di accesso falliti.
* **Recupero Password ed Email Transazionali:** Sistema sicuro per la rigenerazione di password dimenticate tramite link temporizzato via email (scadenza 1 ora) e crittografia password (Bcrypt). Notifica asincrona via email anche in caso di abilitazione di un nuovo account da parte dell'Admin.
