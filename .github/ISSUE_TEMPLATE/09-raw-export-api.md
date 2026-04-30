# Issue 9: Endpoint API per dati raw

## Titolo
**Raw Data Export API Endpoint**

## Descrizione
Alcuni utenti potrebbero volere i dati senza compressione ZIP, per integrazioni programmatiche.

## Proposta
- Aggiungere endpoint `/api/export/raw/<project_id>`
- Restituire JSON diretto con tutti i dati
- Opzionale: supporto CSV per dati tabulari

## File da modificare
- `backend/app/api/export.py`

## Priorità
Bassa

## Tag
[feature] [api] [data-export]