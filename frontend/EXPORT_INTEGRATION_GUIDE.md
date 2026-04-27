# Guida: Aggiungere il Pannello di Esportazione alla GUI

## Componente Creato

Ho creato il componente Vue per l'esportazione in:
```
frontend/src/components/ExportPanel.vue
```

## Come Integrarlo

### Opzione 1: Nella View Report (Consigliato)

Se usi una view dedicata al report, aggiungi il componente qui:

**File:** `frontend/src/views/ReportView.vue`

```vue
<template>
  <div class="report-view">
    <!-- Tuo contenuto del report -->
    <Step4Report 
      :reportId="reportId"
      :projectId="projectId"
      :simulationId="simulationId"
    />
    
    <!-- Aggiungi questo pannello di export sotto o sopra il report -->
    <ExportPanel 
      :projectId="projectId"
      :simulationId="simulationId"
      :reportId="reportId"
    />
  </div>
</template>

<script setup>
import Step4Report from '../components/Step4Report.vue'
import ExportPanel from '../components/ExportPanel.vue'

defineProps({
  projectId: String,
  simulationId: String,
  reportId: String
})
</script>
```

### Opzione 2: Direttamente in Step4Report

Modifica `frontend/src/components/Step4Report.vue` e aggiungi il pannello:

Cerca la sezione dove è il pulsante "Entra in un'interazione profonda":

```vue
<!-- Next Step Button - Mostra dopo il completamento -->
<button v-if="isComplete" class="next-step-btn" @click="goToInteraction">
  <span>Entra in un'interazione profonda</span>
  <svg>...</svg>
</button>

<!-- AGGIUNGI QUI il pannello di export -->
<ExportPanel 
  v-if="isComplete"
  :projectId="projectId"
  :simulationId="simulationId"
  :reportId="reportId"
/>
```

E nell'`<script setup>`:

```javascript
import ExportPanel from './ExportPanel.vue'
```

### Opzione 3: Nel Process.vue (Processore Principale)

Se `Process.vue` è il componente principale che gestisce tutti i step, aggiungi il pannello lì quando il report è completato.

---

## Cosa Fa il Componente

### 📊 Check dello Stato
Mostra 4 indicatori:
- ✓ Progetto disponibile
- ✓ Ontologia disponibile  
- ✓ Simulazione disponibile
- ✓ Report disponibile

### 🔘 Pulsante di Export
Scarica un ZIP completo offline contenente:
- Metadati del progetto
- Ontologia generata
- Configurazione simulazione + Reality Seed
- Personas generate (Twitter + Reddit)
- Report completo (Markdown + JSON)
- Timeline degli agenti
- System prompts utilizzati
- Documenti originali

### 📈 Progress Bar
Durante l'export, mostra la percentuale di avanzamento.

### ✅ Feedback Visivo
- Messaggio di successo dopo il download
- Messaggio di errore in caso di problema
- Spinner di caricamento durante l'export

---

## Props del Componente

```typescript
interface ExportPanelProps {
  projectId: string      // ID del progetto (obbligatorio)
  simulationId?: string  // ID della simulazione (opzionale)
  reportId?: string      // ID del report (opzionale)
}
```

---

## Verifica che Funzioni

1. **Apri la console del browser** (F12)
2. **Clicca su "Scarica ZIP Completo"**
3. **Dovrebbe**: 
   - Vedere il progresso dell'export (0-100%)
   - Scaricare il file `CivesAI_Export_proj_XXXXX.zip`
   - Mostrare un messaggio di successo

## Soluzione di Problemi

### Il pulsante non fa nulla
- Controlla che l'API backend sia raggiungibile
- Verifica che la porta 5000 sia corretta in `ExportPanel.vue` (linea 85)
- Apri la console del browser per gli errori

### CORS error
Se vedi errore "CORS", il backend potrebbe non permettere le richieste dal frontend.
Il CORS è già configurato nel backend (`app/__init__.py`), ma assicurati che l'URL sia corretto.

### File ZIP vuoto
Verifica che i dati siano disponibili:
- Il progetto deve avere un `project.json`
- Se hai una simulazione, deve avere `simulation_config.json`
- Se hai un report, deve avere `outline.json` e `full_report.md`

---

## Personalizzazione

### Cambiare il colore del pulsante

Nel file `ExportPanel.vue`, modifica:

```css
.btn-export-primary {
  background: linear-gradient(135deg, #YOUR_COLOR_1 0%, #YOUR_COLOR_2 100%);
}
```

### Aggiungere più informazioni nel pannello

Aggiungi più righe nel template `<div class="export-status">` per mostrare metadati aggiuntivi.

### Cambiare il testo o l'icona

Modifica il template nella sezione `<template>` del componente.

---

## Prossimi Passi

Dopo aver integrato il componente:

1. ✅ Verifica che il download funzioni
2. ✅ Estrai il ZIP e controlla il contenuto
3. ✅ Leggi il `README.md` nel ZIP per come usare i dati
4. ✅ (Opzionale) Implementa il sistema di importazione per ricaricare i dati

---

**File di riferimento:** `/home/mario/Scrivania/CivesAI/backend/EXPORT_API_DOCS.md` per la documentazione API completa.
