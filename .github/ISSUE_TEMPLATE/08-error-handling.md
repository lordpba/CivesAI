# Issue 8: Miglioramento gestione errori di rete

## Titolo
**Enhanced Network Error Handling and User Feedback**

## Descrizione
Gli errori di rete mostrano messaggi criptici. L'utente non capisce cosa fare quando fallisce.

## Proposta
- Mappare errori comuni a messaggi user-friendly
- Suggerire azioni correttive (es. "Backend non raggiungibile")
- Aggiungere pulsante "Riprova"
- Loggare errori dettagliati per debug

## File da modificare
- `frontend/src/components/ExportPanel.vue`
- `backend/app/api/export.py`

## Priorità
Alta

## Tag
[bug] [ux] [error-handling]