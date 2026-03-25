<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="CivesAI Logo" width="75%"/>

*CivesAI: Il Gemello Digitale e Predittivo per la Pubblica Amministrazione*

</div>

## ⚡ Panoramica del Progetto

**CivesAI** è un motore di simulazione multi-agente e predittivo ideato specificamente per le realtà degli enti pubblici locali italiani (comuni, paesi, città). Estraendo informazioni dal mondo reale (dati demografici, delibere, bilanci, articoli di giornali locali), CivesAI costruisce un mondo digitale parallelo ad alta fedeltà. In questo spazio, migliaia di agenti dotati di personalità indipendente, memoria a lungo termine e logiche comportamentali interagiscono e si evolvono liberamente.

**La Sindaca, il Sindaco o l'Amministratore Locale** può agire dall'alto, inserendo nuove variabili (es. modifiche alla ZTL, rimodulazione della TARI, nuovi cantieri) per prevedere in modo accurato le reazioni dell'opinione pubblica e ottimizzare le politiche pubbliche prima che vengano attuate nel mondo reale.

> Basterà: caricare i documenti di base (analisi anagrafiche, bozze di delibere) e descrivere la simulazione in linguaggio naturale.
> CivesAI restituirà: un report previsionale dettagliato e un ambiente digitale interattivo con cui confrontarsi.

## 🚀 Setup dell'Ambiente Locale (Privacy e Autonomia)

CivesAI è stato pensato per trattare dati dei cittadini e scenari amministrativi. Per questo motivo, **è fondamentale mantenere la totale autonomia e privacy dei dati**. Non inviare mai dati a server cloud di terze parti se contengono informazioni sensibili o riservate della PA.

Per l'esecuzione di CivesAI, raccomandiamo caldamente un **Setup dell'Ambiente Locale** utilizzando:
- **Ollama Locale**: Per l'esecuzione dei modelli linguistici direttamente sui vostri server, garantendo l'assoluta on-premise execution (consigliati modelli leggeri ma efficaci).
- **Infrastruttura Hardware Dedicata**: Invitiamo all'utilizzo di sistemi hardware LocalAI, come i server **DGX** o **AMD ProMaxAI+**, capaci di supportare carichi di lavoro multi-agente pesanti pur mantenendo tempi di risposta rapidi e scalabilità, tutelando la privacy civica.

### Requisiti di Sistema (Locale)
| Strumento | Versione | Descrizione |
|------|---------|------|
| **Node.js** | 18+ | Ambiente frontend |
| **Python** | ≥3.11, ≤3.12 | Ambiente backend |
| **Ollama** | Ultima | Motore LLM Locale |

### Avvio Rapido
1. Installa Ollama e assicurati che il modello prescelto sia scaricato e in esecuzione.
2. Rinomina `.env.example` in `.env` e configura i parametri per puntare al tuo indirizzo locale di Ollama (es: `http://localhost:11434/v1`).
**Nota su Zep**: CivesAI utilizza Zep per gestire la memoria a lungo termine degli agenti. Assicurati di inserire anche la tua `ZEP_API_KEY` (puoi usare il piano gratuito su getzep.com o un'istanza locale se preferisci).
3. Installa le dipendenze con `npm run setup:all`.
4. Avvia CivesAI con `npm run dev` e accedi a `http://localhost:3000`.

## 📄 Licenza e Crediti

Questo progetto nasce come fork e adattamento di [MiroFish](https://github.com/666ghj/MiroFish) e sfrutta l'engine di base originariamente concepito dal team di CAMEL-AI (OASIS).
Ringraziamo i creatori originali per aver rilasciato il codice sotto licenza open-source.

CivesAI evolve l'architettura per creare modelli conformi al tessuto sociale, normativo e amministrativo italiano.
