# Guida alla Gestione di Presenze, Assenze e Copertura Servizi

Questa guida descrive il funzionamento e il flusso di lavoro per la pianificazione delle presenze e delle assenze degli operatori di reparto, con l'obiettivo di monitorare e garantire la costante copertura dei servizi.

---

## 1. Le Pagine Disponibili

Il modulo è composto da tre schermate principali, accessibili tramite il menu **Servizi** della barra di navigazione:

### A. Calendario di Reparto (Matrice Mensile)
* **Destinazione**: `/assenze-mese`
* **Accesso**: *Servizi* &rarr; *Calendario di Reparto*
* **Scopo**: Fornisce una visualizzazione d'insieme, in formato tabellare mensile, degli operatori del proprio reparto.
* **Funzionalità principali**:
  - **Griglia Mensile**: Mostra per ciascun giorno del mese lo stato dell'operatore (se presente in ufficio, assente o in modalità di lavoro alternativa).
  - **Filtri di Visualizzazione (Switch client-side)**: In alto nella pagina sono presenti due controlli switch (**Assenze** e **Presenze**). Cliccando su di essi, la tabella nasconderà o mostrerà istantaneamente i badge colorati corrispondenti senza dover ricaricare la pagina. Questo permette di isolare a colpo d'occhio chi è assente da chi lavora da remoto o fuori sede.
  - **Selettore Reparto**: Per gli utenti con ruolo di *Amministratore*, è visibile un menu a discesa per cambiare il reparto visualizzato.
  - **Navigazione Temporale**: Pulsanti rapidi per scorrere al mese precedente o successivo.

### B. Calendario Presenze (Pianificazione Operativa)
* **Destinazione**: `/calendario-presenze`
* **Accesso**: *Servizi* &rarr; *Calendario Presenze*
* **Scopo**: Consente agli operatori di pianificare i propri giorni di presenza specificando la tipologia e le note descrittive.
* **Funzionalità principali**:
  - **Visualizzazione Doppia**: Possibilità di alternare la vista tra una griglia calendario interattiva (FullCalendar con visualizzazione mensile o settimanale) e un elenco in formato tabella.
  - **Inserimento Nuova Presenza**: Modulo per inserire una presenza selezionando un intervallo di date, la tipologia e una nota descrittiva (lunghezza massima di **20 caratteri**).
  - **Cancellazione**: Un operatore (o un amministratore) può rimuovere una propria pianificazione futura tramite l'icona di eliminazione (cestino).

### C. Gestione Assenze (Richiesta e Pianificazione Congedi)
* **Destinazione**: `/calendario`
* **Accesso**: *Servizi* &rarr; *Calendario Assenze*
* **Scopo**: Consente di registrare i periodi di assenza dal lavoro degli operatori.
* **Funzionalità principali**:
  - **Inserimento Assenza**: Modulo per registrare l'assenza specificando data inizio, data fine e il motivo (Ferie, Malattia, Permesso, ecc.).
  - **Calendario Eventi**: Mappa visivamente le assenze per facilitare la comprensione dei congedi programmati.

---

## 2. Legenda dei Codici e dei Colori

Per garantire una lettura rapida, i diversi stati sono identificati da abbreviazioni e colori specifici:

### Assenze (Absences)
| Codice | Significato | Colore Badge |
|:---:|---|---|
| **F** | Ferie | Verde Scuro |
| **M** | Malattia | Rosso |
| **P** | Permesso | Giallo |
| **FS** | Fuori Sede | Blu |
| **A** | Altro / Non specificato | Grigio |

### Presenze (Presences)
| Codice | Significato | Colore Badge | Descrizione |
|:---:|---|---|---|
| **SW** | Smartwork | Verde Chiaro | Lavoro da remoto/smartworking |
| **CO** | Corsi | Viola | Partecipazione a corsi di formazione |
| **TR** | Trasferta | Blu Chiaro | Attività di lavoro fuori sede/presso clienti |
| **AS** | Altra Sede | Arancione | Lavoro temporaneo presso un'altra sede aziendale |

### Giorni Speciali
- **S / D** (Grigio Chiaro): Fine settimana (Sabato e Domenica).
- **Festa** (Rosa Chiaro): Festività nazionali italiane (es. 2 Giugno, 25 Aprile).

---

## 3. Flusso di Lavoro per la Copertura dei Servizi

Per garantire che un servizio sia sempre presidiato, si consiglia di adottare il seguente flusso operativo:

1. **Pianificazione Anticipata**: Ciascun operatore inserisce le proprie assenze (ferie o permessi) nella pagina **Gestione Assenze** e pianifica i propri giorni di lavoro da remoto o in trasferta nella pagina **Calendario Presenze**.
2. **Verifica della Copertura**: Il responsabile o l'amministratore apre il **Calendario di Reparto** all'inizio del mese o della settimana.
3. **Analisi tramite Switch**:
   - Disattivando lo switch **Presenze**, l'amministratore vede solo chi è assente (F, M, P) per identificare i periodi di carenza di organico.
   - Disattivando lo switch **Assenze**, l'amministratore vede solo chi lavora in modalità speciale (SW, CO, TR, AS) per contare quanti operatori saranno fisicamente presenti in sede.
4. **Risoluzione Sovrapposizioni**: Se in un determinato giorno il numero di persone in ufficio scende sotto la soglia minima di sicurezza, il responsabile può concordare variazioni sulle presenze pianificate (es. revocando temporaneamente lo smartworking o ripianificando un corso).
