# Documentazione Modulo Carpooling & Gestione Flotta Automezzi — Guida Operatori

Benvenuto nella documentazione operativa avanzata per la **Gestione della Flotta Aziendale e Carpooling** in **Troubletick**. Questa guida è rivolta agli Amministratori, ai Global Fleet Manager, ai Fleet Manager di Reparto e agli Operatori di Assistenza incaricati di gestire l'anagrafica dei veicoli, i rifornimenti, le manutenzioni ed il tabellone delle prenotazioni.

---

## 👥 Ruoli e Permessi sulla Flotta

L'accesso alle funzionalità del modulo Carpooling è regolato dalla matrice dei ruoli dell'applicazione:

* **Amministratore (`admin`):** Accesso illimitato e globale su tutta la flotta. Gestisce anagrafica marche, modelli, automezzi, dislocazioni, rifornimenti, manutenzioni, tipi manutenzione, viaggi ed esclusioni dalla prenotazione.
* **Global Fleet Manager (`global_fleet_manager`):** Gestione operativa ed anagrafica completa su tutti i veicoli aziendali (inserimento nuovi mezzi, manutenzioni, rifornimenti, registro viaggi ed esclusioni su scala globale).
* **Fleet Manager di Reparto (`fleet_manager`):** Gestione circoscritta al parco automezzi assegnato al proprio reparto. Può consultare il registro viaggi, registrare i rifornimenti, ed attivare/disattivare l'esclusione dalla prenotazione per i veicoli del proprio reparto. Non può modificare le anagrafiche base o i tipi manutenzione.
* **Operatore di Assistenza (`assistenza`):** Visualizzazione dello stato dei veicoli, prenotazione mezzi per trasferte operative, avvio e chiusura delle sessioni di guida.
* **Utente Normale (`normale`):** Consultazione disponibilità, prenotazione autonoma di un veicolo, avvio viaggio e registrazione rientro con km finali.

---

## 🚘 1. Anagrafica Automezzi e Gestione Flotta

### 1.1 Scheda Tecnico-Amministrativa dell'Automezzo

Ogni veicolo presente nel parco auto aziendale è identificato da una scheda dettagliata accessibile da **Carpooling ➔ Elenco Automezzi** (`/admin/automezzi`):

* **Dati Identificativi:**
  - **Targa:** Identificativo univoco del veicolo (obbligatorio).
  - **Marca:** Selezionabile dall'anagrafica centralizzata marche (es. *Fiat*, *Volkswagen*, *Ford*, *Toyota*, *Renault*).
  - **Modello:** Nome commerciale del modello (es. *Panda*, *Golf*, *Transit*, *Yaris*).
  - **Tipologia:** Classificazione in *Auto* o *Furgone / Veicolo Commerciale*.
* **Caratteristiche Tecniche ed Ambientali:**
  - **Alimentazione:** *Benzina*, *Diesel*, *GPL*, *Metano*, *Ibrida*, *Elettrica*.
  - **Classe Euro:** Normativa antinquinamento (es. *Euro 6d-Temp*, *Euro 5*).
  - **Note / Colore:** Eventuali dettagli estetici o dotazioni particolari (es. *Bianco - Dotata di gancio traino e barre porta tutto*).
* **Gestione Proprietà e Contabilità:**
  - **Proprietà:** *Proprietà aziendale* o *Noleggio a lungo termine*.
  - **Fornitore / Società di Noleggio:** Ragione sociale della società di leasing/noleggio (es. *LeasePlan*, *Arval*, *ALD Automotive*).
  - **Canone Noleggio (€):** Importo del canone mensile per il calcolo dei costi di gestione.
  - **Data Immatricolazione:** Data di prima immatricolazione del mezzo.
* **Stato e Chilometraggio:**
  - **Km Attuali:** Chilometraggio cumulativo aggiornato automaticamente da viaggi e rifornimenti.
  - **Stato Operativo:** *Disponibile*, *In Uso*, *In Manutenzione*.

---

### 1.2 Dislocazioni, Sedi e Reparti Assegnati

Per garantire la tracciabilità logistica delle vetture su più sedi aziendali:

* **Sede Assegnata:** La sede aziendale principale di appartenenza del veicolo (es. *Sede Centrale Milano*).
* **Sede Attuale:** La posizione fisica reale dove si trova attualmente il mezzo (aggiornata in automatico se un viaggio si conclude in una sede diversa da quella di partenza).
* **Reparto Assegnato:** Il reparto aziendale a cui è in carico il veicolo (es. *Reparto IT*, *Assistenza Tecnica*, *Direzione Commerciale*).
* **Gestione Dislocazioni (`/admin/automezzi/dislocazioni`):** Maschera operativa per trasferire fisicamente la sede di stazionamento attuale di un veicolo o riassegnarlo ad un altro reparto.

---

### 1.3 Gestione Marche Automezzi

Accessibile da **Amministrazione ➔ Gestione Marche Automezzi** (`/admin/automezzi/marche`), permette agli Amministratori di gestire la tabella delle marche automobilistiche selezionabili nelle schede dei veicoli.

---

### 1.4 Esclusione dalla Prenotazione (Gestione Flotta Riservata)

La funzionalità **Escludi da Prenotazione** (`escluso_prenotazione = 1`) consente di rimuovere un automezzo dal tabellone delle prenotazioni pubbliche, rendendolo invisibile agli utenti normali.

* **Casi d'Uso:** Veicolo in riparazione straordinaria prolungata, mezzo guasto in attesa di rottamazione, auto riservata alla Direzione o assegnata in uso esclusivo.
* **Regole di Autorizzazione (RBAC):**
  - I **Fleet Manager di Reparto** possono attivare o rimuovere l'esclusione **esclusivamente** per gli automezzi assegnati al proprio reparto.
  - I **Global Fleet Manager** e gli **Amministratori** possono attivare o rimuovere l'esclusione su qualsiasi veicolo della flotta aziendale.

---

## ⛽ 2. Gestione Rifornimenti Carburante

Il modulo Rifornimenti (`/admin/automezzi/rifornimenti`) consente di tracciare le spese per carburante e le schede petrolifere aziendali.

### 2.1 Tracciamento dei Rifornimenti Carburante

Per ciascuna erogazione di carburante vengono registrate le seguenti informazioni:

* **Dati Veicolo & Utilizzo:** Targa del veicolo e chilometraggio rilevato al momento della sosta alla pompa (`km`).
* **Scheda / Carta Carburante:** Numero PAN o identificativo della carta utilizzata (`pan_carta`).
* **Timestamp:** Data e ora dell'erogazione.
* **Carburante & Volumi:** Prodotto erogato (*Gasolio*, *Benzina SP*, *GPL*, *Metano*, *AdBlue*, *Ricarica Elettrica*), quantitativo in litri/kWh (`volume`) e prezzo unitario al litro (`prezzo_eur_l`).
* **Dettaglio Economico:** Importo totale lordo (`imp_intero`), importo al netto dell'IVA, aliquota IVA ed eventuale sconto applicato (€/L).
* **Stazione di Servizio:** Codice impianto, codice terminale, indirizzo e città della stazione di rifornimento.

---

### 2.2 Aggiornamento Automatico dei Chilometri

Ogni volta che viene inserito un nuovo rifornimento:
1. Viene creata una riga di tracciamento nel registro storico dei chilometri (`registro_km_automezzi`) con sorgente `"Rifornimento"`.
2. Se i chilometri indicati nel rifornimento superano il chilometraggio attuale della scheda auto, il valore `km_attuali` del veicolo viene aggiornato automaticamente.

---

### 2.3 Importazione ed Esportazione Dati Rifornimenti

* **Importazione CSV:** Gli amministratori possono importare i file flussi mensili o settimanali forniti dai gestori di carte carburante aziendali (es. *ENI RouteEX*, *IP Pay*, *Q8 Corporate*, *DKV*, *UTA*).
* **Esportazione Report:** Possibilità di esportare lo storico filtrato dei rifornimenti in formato CSV o Excel per verifiche contabili e calcolo dei consumi medi (L/100 km).

---

## 🔧 3. Gestione Manutenzioni e Tagliandi

Il modulo Manutenzioni (`/admin/automezzi/manutenzioni`) gestisce la manutenzione ordinaria, straordinaria e le scadenze dei veicoli.

### 3.1 Tipi di Manutenzione e Scadenziario

Gli amministratori possono configurare le tipologie di intervento in **Amministrazione ➔ Tipi Manutenzione** (`/admin/automezzi/tipi-manutenzione`):

* **Tipologie Esempio:** *Tagliando Ordinario*, *Cambio Gomme Stagionale (Estive/Invernali)*, *Revisione Ministeriale MCTC*, *Riparazione Meccanica*, *Riparazione Carrozzeria*, *Sanificazione ed Igiene*.
* **Impostazione Scadenze:** È possibile definire intervalli di manutenzione in mesi (es. *Revisione ogni 24 mesi*) e/o in chilometri (es. *Tagliando ogni 15.000 km*).

---

### 3.2 Stati della Manutenzione e Workflow

1. **Manutenzione Programmata:**
   - Pianificazione di un intervento futuro. L'auto rimane prenotabile ed utilizzabile fino alla data stabilita.
2. **Manutenzione In Corso (Bloccante):**
   - Quando il veicolo entra fisicamente in officina, l'operatore imposta lo stato su **"In Corso"**.
   - Il sistema aggiorna automaticamente lo stato dell'auto in **"In Manutenzione"**.
   - Eventuali tentativi di prenotazione nel periodo di manutenzione vengono **bloccati automaticamente** per evitare conflitti.
3. **Manutenzione Conclusa (Rilascio Mezzo):**
   - Al ritiro dell'auto dall'officina, l'operatore chiude la scheda manutenzione inserendo: data/ora effettiva di fine, km finali registrati, importo totale della fattura (€) e descrizione dei lavori eseguiti.
   - Il sistema ripristina lo stato dell'automezzo in **"Disponibile"** ed aggiorna i chilometri attuali del mezzo.
4. **Manutenzione Annullata:**
   - Annullamento dell'intervento programmato con ripristino immediato della disponibilità dell'auto.

---

### 3.3 Scheda Dettagliata dell'Intervento

Ogni scheda di manutenzione traccia: officina o carrozzeria esecutrice, indirizzo/luogo, spesa complessiva sostenuta (€), lista dei ricambi o parti sostituite (es. *Filtro olio, pastiglie freni anteriori*), note tecniche e flag *bloccante*.

---

## 📅 4. Gestione Carpooling, Prenotazioni e Registro Viaggi

### 4.1 Tabellone delle Prenotazioni

Dal menu **Carpooling ➔ Prenotazioni Mezzi** (`/autopark`), gli operatori e i dipendenti consultano il calendario della flotta.

* **Filtri di Ricerca:** Filtro per Sede di stazionamento, Reparto assegnato, Tipologia (*Auto/Furgone*) ed Alimentazione.
* **Verifica Disponibilità:** Il sistema incrocia in tempo reale le date/ore richieste ed inibisce la selezione di veicoli già occupati o in manutenzione.

---

### 4.2 Ciclo di Vita del Viaggio (Check-in / Check-out)

#### 1. Inserimento Prenotazione
L'utente o l'operatore inserisce: veicolo desiderato, conducente, data/ora inizio, data/ora fine prevista, sede di ritiro, sede di consegna e scopo del viaggio.

#### 2. Avvio Viaggio (Partenza / Check-in)
Al momento del ritiro delle chiavi:
- Viene avviata la sessione di guida.
- Il sistema propone i `km_iniziali` sincronizzati con il valore attuale dell'automezzo.
- Registrazione dell'ora di partenza effettiva.

#### 3. Chiusura Viaggio (Riconsegna / Check-out)
Al rientro della vettura:
- Inserimento dei **Km Finali** mostrati sul contachilometri.
- Inserimento dell'**ora di rientro effettiva** e della **sede di riconsegna reale**.
- **Calcolo Automatico:** Il sistema calcola la percorrenza netta del viaggio (`km_finali - km_iniziali`), aggiorna il totale chilometrico dell'auto e registra l'evento nel registro storico dei chilometri.
- Se l'auto è stata riconsegnata in una sede diversa da quella di partenza, il sistema aggiorna la `sede_attuale_id` del veicolo.

#### 4. Annullamento Prenotazione
Qualora una trasferta venga cancellata, l'utente o un Fleet Manager può annullare la prenotazione liberando istantaneamente il mezzo.

#### 5. Modifica dei Viaggi Registrati (Self-Service & Admin)
Sia gli utenti normali che gli operatori di assistenza hanno la facoltà di modificare a posteriori i dati dei propri viaggi registrati o completati. I campi modificabili sono:
- **Orario di Partenza** e **Orario di Arrivo / Rientro**
- **Chilometri di Arrivo** (KM Finali)
- **Note del Viaggio**

*I campi relativi a Data del Viaggio, KM di Partenza e Sedi di Partenza/Arrivo rimangono bloccati per preservare l'integrità e la coerenza del registro.* Gli Amministratori ed i Fleet Manager possono intervenire sui viaggi di propria competenza direttamente dal registro viaggi `/admin/automezzi/viaggi` o dal pannello Carpooling `/autopark`. All'aggiornamento dei chilometri finali, il sistema ricalcola automaticamente il chilometraggio attuale del veicolo e aggiorna lo storico km.

---

### 4.3 Registro Viaggi (`/admin/automezzi/viaggi`)

Accessibile ai Fleet Manager e agli Amministratori per il monitoraggio e il controllo a posteriori:

* **Archivio Analitico:** Elenco storico di tutti i viaggi effettuati dalla flotta aziendale.
* **Filtri Avanzati:** Ricerca per targa, conducente, reparto o intervallo di date.
* **Modifica e Rettifica Viaggi:** Facoltà di rettificare orari, km finali e note dei viaggi registrati con aggiornamento automatico del contachilometri dell'auto.
* **Gestione ed Interventi Straordinari:** Facoltà per i Fleet Manager di rettificare km inseriti erroneamente dagli utenti o di chiudere d'ufficio viaggi non conclusi regolarmente.

---

## 📊 5. Monitoraggio Costi e KPI Flotta

### 5.1 Cruscotto Operativo
Nella dashboard amministrazione/fleet manager sono sempre visibili i contatori in tempo reale:
* **Veicoli Disponibili:**Pronti per la prenotazione.
* **Veicoli In Uso:** Attualmente in viaggio con un conducente.
* **Veicoli In Manutenzione:** In officina per riparazioni o tagliandi.
* **Veicoli Esclusi:** Fuori flotta o riservati.

### 5.2 Indicatori Economici e TCO (Total Cost of Ownership)
Attraverso l'incrocio dei dati presenti nei moduli:
- **Costo Canoni Noleggio:** Somma dei canoni mensili per i veicoli in leasing.
- **Costo Manutenzioni:** Totale delle spese per tagliandi, riparazioni e ricambi.
- **Costo Carburante:** Totale delle spese di rifornimento registrate.

Gli operatori possono calcolare il costo totale d'esercizio di ogni singolo veicolo ed il costo al chilometro (€/km) dell'intera flotta aziendale.
