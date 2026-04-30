# Issue 5: Notifiche di stato avanzate

## Titolo
**Advanced Export Progress Notifications**

## Descrizione
Durante l'esportazione l'utente non vede il progresso. Serve:
- Progress bar dettagliata
- Log in tempo reale delle operazioni
- Tempo stimato rimanente

## Proposta
- Implementare WebSocket per aggiornamenti in tempo reale
- Aggiungere log dettagliato nel frontend
- Mostrare percentuali per ogni fase (collect, compress, download)

## File da modificare
- `backend/app/services/export_service.py`
- `backend/app/api/export.py`
- `frontend/src/components/ExportPanel.vue`

## Priorità
Media

## Tag
[enhancement] [ux] [real-time]