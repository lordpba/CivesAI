# Issue 2: Test automatici per la funzione di esportazione

## Titolo
**Add Automated Tests for Export Functionality**

## Descrizione
Manca copertura di test per:
- Backend: `export_service.py`, endpoint `/api/export/*`
- Frontend: `ExportPanel.vue`, download ZIP

## Proposta
- Aggiungere test unitari per `ExportService`
- Aggiungere test di integrazione per gli endpoint API
- Aggiungere test E2E per il flusso di esportazione (Playwright/Cypress)
- Verificare che il ZIP contenga tutti i file attesi

## File da modificare
- `backend/tests/test_export.py` (da creare)
- `frontend/tests/export.spec.js` (da creare)

## Priorità
Alta

## Tag
[testing] [backend] [frontend] [ci/cd]