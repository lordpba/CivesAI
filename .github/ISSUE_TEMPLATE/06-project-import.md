# Issue 6: Importazione progetto esportato

## Titolo
**Project Import: Restore from ZIP**

## Descrizione
Esportare è utile, ma poter ripristinare un progetto da ZIP è essenziale per:
- Condividere progetti tra utenti
- Backup e restore
- Migrazione tra ambienti

## Proposta
- Creare `import_service.py` nel backend
- Aggiungere endpoint `/api/import/package`
- Creare UI per upload ZIP nel frontend
- Validare il contenuto del ZIP prima dell'import

## File da creare/modificare
- `backend/app/services/import_service.py`
- `backend/app/api/import.py`
- `frontend/src/components/ImportPanel.vue`

## Priorità
Alta

## Tag
[feature] [import] [backup]