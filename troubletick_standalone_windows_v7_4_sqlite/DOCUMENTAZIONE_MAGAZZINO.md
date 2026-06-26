# Guida Operativa Funzioni di Magazzino e Logistica

Questa guida descrive in modo approfondito i flussi operativi, le responsabilità e le funzionalità del modulo **Magazzino & Logistica** di Troubletick.

---

## 📋 Indice
1. [Il Flusso Completo: Richiesta e Fornitura di Materiale](#1-il-flusso-completo-richiesta-e-fornitura-di-materiale)
2. [Gestione delle Richieste da parte del Magazziniere](#2-gestione-delle-richieste-da-parte-del-magazziniere)
3. [Operazioni di Scarico e Stampa Ricevute](#3-operazioni-di-scarico-e-stampa-ricevute)
4. [Carico e Scarico Diretto (Senza Ticket)](#4-carico-e-scarico-diretto-senza-ticket)
5. [Lo Scarico Multiplo (Carrello di Consegna)](#5-lo-scarico-multiplo-carrello-di-consegna)
6. [💡 Casi d'Uso Pratici ed Esempi](#6--casi-duso-pratici-ed-esempi)

---

## 1. Il Flusso Completo: Richiesta e Fornitura di Materiale

Il flusso standard di fornitura segue un processo strutturato per garantire tracciabilità e correttezza nelle assegnazioni e nelle giacenze:

```mermaid
graph TD
    A[Utente/Operatore descrive il bisogno nel Ticket] --> B[Operatore del servizio prende in carico il Ticket]
    B --> C{Verifica e Approva?}
    C -- NO --> D[Ticket Rifiutato/Chiuso]
    C -- SI --> E[Operatore aggiunge i Materiali al Ticket]
    E --> F[Operatore seleziona il Magazzino idoneo]
    F --> H[Magazziniere evade la richiesta ed esegue lo scarico]
```

### I Passaggi del Flusso:

1. **La Segnalazione Testuale**: Un utente descrive nel corpo di un ticket la necessità di materiale (es. *"La stampante al secondo piano ha finito il toner"* oppure *"Ho bisogno di una tastiera nuova"*).
2. **Presa in Carico**: L'operatore abilitato al servizio prende in carico la segnalazione e valuta la richiesta dell'utente.
3. **Approvazione e Inserimento**: Se la richiesta è valida, l'operatore clicca su **"Crea Nuova Richiesta"** direttamente all'interno della scheda di dettaglio del ticket per aggiungere i materiali necessari.
4. **Scelta del Magazzino**: Durante la creazione della richiesta, l'operatore seleziona la tipologia di materiale e il **magazzino di prelievo** più idoneo (es. Magazzino Alessandria, Magazzino Milano).
5. **Evasione da parte del Magazzino**: La richiesta compare automaticamente nella coda del magazzino selezionato, così che gli operatori di magazzino abilitati (magazzinieri) possano vederla, preparare il materiale ed eseguire lo scarico.
6. **Chiusura Vincolata del Ticket**: Il ticket non potrà essere chiuso finché rimangono richieste di materiale associate ad esso che non siano state ancora evase o annullate. Gli operatori dovranno quindi evadere o annullare tutte le richieste pendenti per poter procedere alla chiusura del ticket.

---

## 2. Gestione delle Richieste da parte del Magazziniere

L'operatore di magazzino monitora costantemente le richieste in arrivo tramite il menu **Magazzino ➔ Richieste Materiale**:

* **Verifica della Coda**: La vista mostra le richieste filtrate in base ai magazzini a cui l'operatore è abilitato.
* **Controllo della Disponibilità**: 
  - Se il materiale richiesto è **disponibile** in giacenza, lo stato della richiesta passa automaticamente a **"Pronta per Scarico"** (evidenziato in giallo).
  - Se il materiale **non è disponibile**, la richiesta rimane nello stato **"In Attesa"** (evidenziato in azzurro) fino al carico di nuova merce.
* **Tempistica di Evasione**: Il magazziniere può cliccare su **"Esegui Scarico"** per confermare la fornitura del materiale. Questa operazione va eseguita **subito prima o immediatamente dopo** la consegna fisica del bene all'interessato.
* **Vincolo sulla Chiusura del Ticket**: Poiché la presenza di richieste in sospeso ("In Attesa" o "Pronta per Scarico") impedisce la chiusura del relativo ticket di supporto, l'operatore o il magazziniere devono completare l'evasione (o procedere all'annullamento delle richieste non più necessarie) per consentire la corretta chiusura della segnalazione.

---

## 3. Operazioni di Scarico e Stampa Ricevute

Quando si clicca su **"Esegui Scarico"** per una richiesta associata ad un ticket:

* **Campi Bloccati**: Per garantire la conformità con quanto inserito nella richiesta dall'operatore, la **quantità** e la **sede di destinazione** sono pre-compilate dalla richiesta e **non possono essere modificate**. Anche la spedizione/trasferimento ad altri magazzini è disabilitata.
* **Selezione Posizione**: Il magazziniere deve unicamente selezionare la **posizione fisica** (scaffale/lotto) da cui prelevare i pezzi.
* **Note Automatiche**: Il sistema imposta una descrizione predefinita e, ad operazione avvenuta, inserisce in automatico una nota di servizio nel ticket (es. *"Richiesta materiale evasa dal magazzino: 1x Toner HP"*).
* **Verbale di Consegna PDF**: Attivando la spunta **"Crea documento di consegna"** (posizionata all'interno del box **"Ricevente"**), il sistema apre una pagina di stampa ottimizzata in formato A4 che funge da verbale di consegna da far firmare al destinatario al ritiro del materiale.

---

## 4. Carico e Scarico Diretto (Senza Ticket)

Oltre al flusso controllato dai ticket di assistenza, Troubletick consente la gestione diretta della merce per operazioni logistiche di routine (es. inventari, rifornimenti, smaltimenti):

* **Carico Merce**: Dalla pagina **Inventario**, l'operatore clicca su **"Carico"** accanto ad un articolo per registrarne l'entrata. È obbligatorio specificare la quantità e la posizione fisica di stoccaggio. È caldamente consigliato allegare la foto del DDT o del bene.
* **Scarico Diretto**: Usando il tasto **"Scarico"** direttamente sull'inventario, si registra un prelievo manuale slegato dai ticket. Anche in questo caso è possibile generare il modulo di consegna PDF e indicare una sede aziendale di destinazione o avviare un **Trasferimento tra Magazzini** (spedizione tracciata che richiede l'approvazione del magazziniere di arrivo).

---

## 5. Lo Scarico Multiplo (Carrello di Consegna)

Nel caso in cui sia necessario consegnare contemporaneamente più articoli di tipologie differenti a un singolo utente o per una specifica sede (es. allestimento postazione di un nuovo assunto), si utilizza lo **Scarico Multiplo**:

1. Nella pagina **Inventario**, cliccare su **"Scarico Multiplo"** in alto.
2. Aggiungere le righe desiderate selezionando il magazzino, il materiale, la posizione di prelievo e la quantità.
3. Indicare la sede di destinazione, la data e una nota descrittiva unica.
4. Spuntare **"Genera PDF"** per produrre un **Buono di Consegna Cumulativo** che elenca tutti i materiali prelevati su un unico foglio, pronto per essere firmato.

---

## 💡 Casi d'Uso Pratici ed Esempi

### 🏢 Esempio 1: Allestimento Postazione Nuovo Dipendente (Flusso Standard con Ticket)
* **Scenario**: Le Risorse Umane aprono un ticket chiedendo la preparazione del materiale per un nuovo assunto presso la sede di Milano.
* **Operazione dell'Operatore Abilitato**: L'operatore IT abilitato al servizio prende in carico il ticket, verifica la richiesta e aggiunge formalmente ad esso tre richieste di materiale: 1x PC Desktop, 1x Monitor 24", 1x Kit Tastiera/Mouse, impostando come magazzino di prelievo "IT Milano".
* **Operazione del Magazziniere**: L'operatore del magazzino di Milano vede le tre richieste in stato "Pronta per scarico". Prepara il materiale, clicca su "Esegui Scarico" per ciascuno selezionando le rispettive posizioni fisiche, genera i PDF di consegna e fa firmare i fogli al dipendente al momento del ritiro.

### 📦 Esempio 2: Richiesta di Toner Esaurito (Gestione Pendenza/Backorder)
* **Scenario**: La segreteria di Alessandria segnala che la stampante multifunzione ha terminato il toner nero.
* **Operazione dell'Operatore Abilitato**: L'operatore abilitato inserisce la richiesta per 1x Toner Nero nel ticket, assegnando il prelievo al Magazzino Alessandria.
* **Operazione del Magazziniere (Richiesta Pendente)**: Il toner è esaurito nel magazzino di Alessandria. La richiesta compare nella lista in stato **"In Attesa"** (non è presente il tasto "Esegui Scarico").
* **Rifornimento**: Due giorni dopo, arriva il corriere con i nuovi toner. Il magazziniere effettua un **Carico** di 5 toner indicando la posizione `Scaffale B2`.
* **Evasione**: All'istante, la richiesta associata al ticket passa in stato **"Pronta per Scarico"**. Il magazziniere clicca su "Esegui Scarico", preleva 1 pezzo da `Scaffale B2` e consegna il toner. Una volta evasa questa richiesta, se non vi sono altri materiali pendenti, il ticket potrà finalmente essere chiuso.

### 🛠️ Esempio 3: Manutenzione Straordinaria (Scarico Diretto e Trasferimento)
* **Scenario**: Viene riscontrato che un componente di rete nel Magazzino Centrale deve essere spedito al Magazzino Secondario di Torino per sostituire un pezzo guasto.
* **Operazione**: Il responsabile logistica esegue uno **Scarico Diretto** dal Magazzino Centrale per l'articolo desiderato. Nella form di scarico, seleziona come destinazione **"OPPURE Trasferisci a Magazzino"** indicando "Magazzino Torino".
* **Risultato**: La giacenza nel Magazzino Centrale decresce immediatamente. Il sistema crea una spedizione in stato "In Consegna". Quando il pacco arriva a Torino, il magazziniere locale va su "Trasferimenti", verifica la corrispondenza e clicca su "Ricevi", caricando in automatico la giacenza a Torino con tracciabilità completa.
