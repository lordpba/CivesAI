<div align="center">

<img src="./static/image/civesai_logo.png" alt="CivesAI Logo" width="65%"/>

### **CivesAI: Il Gemello Digitale e Predittivo per la Pubblica Amministrazione**

*Simulazione multi-agente ad alta fedeltà per l'ottimizzazione delle politiche pubbliche e l'ascolto dei cittadini.*

[![License](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://opensource.org/licenses/AGPL-3.0)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-brightgreen.svg)](https://nodejs.org/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama%20Locale-orange.svg)](https://ollama.ai/)

[Italiano](./README.md) | [English](./README-EN.md)

</div>

---

## ⚡ Panoramica del Progetto

**CivesAI** è un motore di simulazione multi-agente e predittivo ideato specificamente per le realtà degli enti pubblici locali italiani (comuni, province, città). Estraendo informazioni dal mondo reale — come dati demografici, delibere, bilanci e articoli di cronaca — CivesAI costruisce un **mondo digitale parallelo** ad alta fedeltà.

In questo ecosistema, migliaia di agenti dotati di personalità indipendente, memoria a lungo termine e logiche comportamentali interagiscono e si evolvono autonomamente. **Amministratori e decisori politici** possono agire in questo "sandbox" digitale, inserendo nuove variabili (es. modifiche alla ZTL, rimodulazione delle tasse locali, nuovi cantieri) per:

- **Prevedere le reazioni** dell'opinione pubblica in modo accurato.
- **Ottimizzare le politiche** prima della loro attuazione reale.
- **Identificare criticità** sommerse o potenziali conflitti sociali.

## ✨ Caratteristiche Principali

- 🤖 **Motore Multi-Agente Avanzato**: Basato sull'engine OASIS, permette la simulazione di interazioni sociali complesse tra migliaia di agenti con tratti psicologici unici.
- 🧠 **Memoria a Lungo Termine**: Integrazione con **Zep** per permettere agli agenti di ricordare interazioni passate, evolvendo la propria opinione nel tempo in base agli eventi della simulazione.
- 📄 **Seeding da Documenti Reali**: Carica PDF, file di testo o markdown per addestrare il contesto della simulazione su dati amministrativi reali.
- 🔒 **Privacy First (Local LLM)**: Supporto nativo per **Ollama**, consentendo l'esecuzione di modelli linguistici direttamente on-premise, garantendo che i dati sensibili della PA non lascino mai i server locali.
- 📊 **Reportistica Automatica**: Generazione di report dettagliati sull'andamento della simulazione, impatto sociale e suggerimenti strategici tramite un Report Agent dedicato.
- 💬 **Interazione Diretta**: Possibilità di "scendere in campo" e dialogare direttamente con gli agenti simulati per sondarne umori e motivazioni.

## 🚀 Avvio Rapido

### Requisiti di Sistema
- **Node.js**: v18.0.0 o superiore
- **Python**: 3.11 o 3.12 (consigliato l'uso di `uv` per la gestione pacchetti)
- **Ollama**: Per l'esecuzione locale dei modelli (optional se si usano API Cloud)
- **Zep**: Per la gestione della memoria degli agenti (cloud o locale)

### Installazione

1. **Configurazione Ambiente**:
   Rinomina il file `.env.example` in `.env` e inserisci le tue chiavi API e gli endpoint locali.
   ```bash
   LLM_BASE_URL=http://localhost:11434/v1 # Esempio per Ollama
   LLM_MODEL_NAME=llama3 # O altro modello installato
   ZEP_API_KEY=tua_chiave_zep
   ```

2. **Setup Automatico**:
   Installa tutte le dipendenze (frontend e backend) con un unico comando:
   ```bash
   npm run setup:all
   ```

3. **Esecuzione**:
   Avvia i server di sviluppo per backend e frontend simultaneamente:
   ```bash
   npm run dev
   ```
   L'applicazione sarà accessibile all'indirizzo `http://localhost:3000`.

## 🏗️ Architettura

Il sistema è composto da tre pilastri fondamentali:
- **Frontend (Vite + Vue.js)**: Una dashboard interattiva per visualizzare la simulazione e i report.
- **Backend (Flask)**: Gestisce la logica di business, l'elaborazione dei documenti e l'orchestrazione degli agenti.
- **Simulation Engine (Camel-AI/OASIS)**: Il cuore pulsante che governa le interazioni sociali e l'evoluzione degli agenti.

## 📄 Licenza e Crediti

Questo progetto è distribuito sotto licenza **AGPL-3.0**.

**CivesAI** nasce come adattamento e evoluzione di [MiroFish](https://github.com/666ghj/MiroFish) e sfrutta l'engine di simulazione originariamente concepito dal team di **CAMEL-AI (OASIS)**. Ringraziamo profondamente la comunità open-source per queste basi tecnologiche straordinarie.

---

<div align="center">
Creato con passione per rendere la Pubblica Amministrazione più smart, predittiva e vicina ai cittadini.
</div>
