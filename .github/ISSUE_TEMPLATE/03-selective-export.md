# Issue 3: Esportazione selettiva

## Titolo
**Selective Export: Choose What to Include**

## Descrizione
L'utente può voler esportare solo alcune parti del progetto:
- Solo il report PDF
- Solo il grafo (JSON)
- Solo gli agenti/interazioni
- Solo il reality seed (calibrazione)
- Solo il prompt originale

## Proposta
- Aggiungere checkboxes nell'interfaccia ExportPanel
- Modificare `export_service.py` per accettare parametri di filtro
- Aggiornare l'endpoint API per supportare opzioni

## File da modificare
- `frontend/src/components/ExportPanel.vue`
- `backend/app/services/export_service.py`
- `backend/app/api/export.py`

## Priorità
Media

## Tag
[enhancement] [ux] [export]