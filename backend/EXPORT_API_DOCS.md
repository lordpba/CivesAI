# API di Esportazione Completa - Documentazione

## Panoramica

Il sistema di esportazione permette di esportare **progetti completi offline** in un archivio ZIP autosufficiente, contenente:

- ✅ Metadati del progetto (project.json)
- ✅ Ontologia generata (ontology.json)
- ✅ Dati della simulazione completi
- ✅ Reality seed (calibration profile con NUTS-2)
- ✅ Personas generate (Twitter CSV + Reddit JSON)
- ✅ Report completo (Markdown + JSON)
- ✅ Timeline degli agenti (agent_log.jsonl)
- ✅ Tutti i system prompts utilizzati
- ✅ Documenti originali
- ✅ README con guida completa

## Endpoints

### 1. POST `/api/export/package`

Crea un archivio ZIP completo offline.

**Richiesta:**
```json
{
  "project_id": "proj_7e9ec9b0b58c",
  "simulation_id": "sim_0150b5e7d64a",  // Opzionale
  "report_id": "report_7e9ec9b0b58c"     // Opzionale
}
```

**Parametri:**
- `project_id` *(required)* - ID del progetto da esportare
- `simulation_id` *(optional)* - ID della simulazione (se eseguita)
- `report_id` *(optional)* - ID del report (se generato)

**Risposta:**
```
File ZIP (application/zip)
Nome: CivesAI_Export_<project_id>.zip
```

**Esempio cURL:**
```bash
curl -X POST http://localhost:5000/api/export/package \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_7e9ec9b0b58c",
    "simulation_id": "sim_0150b5e7d64a",
    "report_id": "report_7e9ec9b0b58c"
  }' \
  -o export.zip
```

**Esempio Python:**
```python
import requests
import json

url = "http://localhost:5000/api/export/package"
payload = {
    "project_id": "proj_7e9ec9b0b58c",
    "simulation_id": "sim_0150b5e7d64a",
    "report_id": "report_7e9ec9b0b58c"
}

response = requests.post(url, json=payload)
with open("export.zip", "wb") as f:
    f.write(response.content)
```

---

### 2. POST `/api/export/status`

Verifica se i dati necessari per l'esportazione sono disponibili.

**Richiesta:**
```json
{
  "project_id": "proj_7e9ec9b0b58c",
  "simulation_id": "sim_0150b5e7d64a",
  "report_id": "report_7e9ec9b0b58c"
}
```

**Risposta (Success):**
```json
{
  "success": true,
  "data": {
    "project_available": true,
    "ontology_available": true,
    "simulation_available": true,
    "report_available": true
  }
}
```

**Risposta (Error):**
```json
{
  "success": false,
  "error": "Messaggio di errore"
}
```

---

## Struttura dell'Archivio ZIP

```
CivesAI_Export_proj_XXXXX.zip
│
├── README.md                           # Guida completa
├── manifest.json                       # Metadati dell'export
│
├── PROJECT/
│   ├── project.json                    # Stato completo del progetto
│   ├── extracted_text.txt              # Testo estratto
│   ├── files_manifest.json             # Elenco file
│   └── files/                          # Documenti originali
│
├── ONTOLOGY/
│   └── ontology.json                   # Entity types + relationship types
│
├── SIMULATION/
│   ├── simulation_config.json          # Configurazione completa
│   ├── state.json                      # Stato finale
│   ├── run_state.json                  # Timeline esecuzione
│   ├── twitter_profiles.csv            # Personas Twitter
│   ├── reddit_profiles.json            # Personas Reddit
│   └── env_status.json                 # Status ambiente
│
├── REPORT/
│   ├── full_report.md                  # Report Markdown completo
│   ├── outline.json                    # Struttura report
│   ├── meta.json                       # Metadati report
│   ├── section_*.md                    # Sezioni individuali
│   └── agent_log.json                  # Timeline agenti
│
├── SYSTEM_PROMPTS/
│   └── prompts.json                    # Tutti i prompts usati
│
└── GRAPH/                              # (Se disponibile)
    └── graph.json                      # Grafo della conoscenza
```

---

## Reality Seed e Calibration

Il **reality seed** (calibrazione NUTS-2) si trova in:

**Percorso:** `SIMULATION/simulation_config.json`

**Struttura:**
```json
{
  "calibration_profile": {
    "nuts2_region": "ITC4",
    "calibration_summary": "...",
    "regional_statistics": {...},
    "demographic_profile": {...}
  },
  "oasis_agent_profiles": [...]
}
```

Contiene tutte le informazioni sulla regione selezionata necessarie per riprodurre la simulazione.

---

## System Prompts

I **system prompts** utilizzati durante tutta la generazione si trovano in:

**Percorso:** `SYSTEM_PROMPTS/prompts.json`

**Categorie incluse:**
- `ontology_generation` - Prompt per la generazione dell'ontologia
- `report_generation` - Prompts per la generazione del report
- `simulation_config` - Prompts per la configurazione della simulazione

Questi prompts sono essenziali per **riprodurre esattamente** gli stessi risultati.

---

## Casi di Uso

### 1. Backup Completo
```bash
curl -X POST http://localhost:5000/api/export/package \
  -H "Content-Type: application/json" \
  -d '{"project_id": "proj_7e9ec9b0b58c"}' \
  -o backup_$(date +%Y%m%d).zip
```

### 2. Condividere un Progetto Completo
Genera l'export e condividi il ZIP - contiene tutto per riprodurre il lavoro offline.

### 3. Archiviazione per Audit
Lo ZIP contiene tutta la cronologia (agent_log) per tracciare il processo completo.

### 4. Importare in un'Altra Istanza
I dati JSON sono autosufficenti per ricaricare il progetto in un'altra istanza di CivesAI.

---

## Codici di Errore

| Codice | Significato |
|--------|-----------|
| 200 | OK - Esportazione riuscita |
| 400 | Bad Request - project_id mancante |
| 404 | Not Found - Progetto/Simulazione/Report non trovato |
| 500 | Server Error - Errore durante l'esportazione |

---

## Note Importanti

⚠️ **Dimensione file:**
- Un'esportazione completa può essere voluminosa (dipende da report size)
- I ZIP sono compressi (ZIP_DEFLATED)

✅ **Compatibilità offline:**
- L'archivio è **completamente offline** - nessuna dipendenza dal server
- Tutti i JSON sono validi per importazioni future

✅ **Conservazione dati:**
- **Nessuna** informazione è persa
- Tutti i log, i prompts, gli stati sono inclusi

⚠️ **Confidenzialità:**
- L'archivio contiene i **system prompts** completi
- Conservare in modo sicuro se contiene informazioni sensibili

---

## Implementazione

I servizi di esportazione sono implementati in:
- **Service:** `/backend/app/services/export_service.py`
- **API:** `/backend/app/api/export.py`

**Classe principale:** `ExportService`
**Metodi pubblici:**
- `create_export_package(project_id, simulation_id, report_id)` - Crea l'archivio ZIP

---

## Esempio Completo

```python
import requests
import zipfile
import io

# 1. Verifica disponibilità
check_url = "http://localhost:5000/api/export/status"
check_response = requests.post(check_url, json={
    "project_id": "proj_7e9ec9b0b58c",
    "simulation_id": "sim_0150b5e7d64a",
    "report_id": "report_7e9ec9b0b58c"
})

if check_response.json()["success"]:
    print("✓ Tutti i dati sono disponibili")
    
    # 2. Esporta
    export_url = "http://localhost:5000/api/export/package"
    export_response = requests.post(export_url, json={
        "project_id": "proj_7e9ec9b0b58c",
        "simulation_id": "sim_0150b5e7d64a",
        "report_id": "report_7e9ec9b0b58c"
    })
    
    # 3. Salva
    with open("export.zip", "wb") as f:
        f.write(export_response.content)
    
    # 4. Leggi contenuto
    with zipfile.ZipFile("export.zip", 'r') as zf:
        print("✓ Archivio creato con successo!")
        print("  Contenuti:")
        for name in zf.namelist()[:10]:  # Primi 10 file
            print(f"    - {name}")
else:
    print("✗ Dati non disponibili:", check_response.json())
```

---

**Versione:** 1.0
**Data:** 2026-04-27
**Status:** Stabile e pronto per l'uso
