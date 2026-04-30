# Issue 1: Configurazione dinamica API Base URL

## Titolo
**Dynamic API Base URL Configuration for Frontend**

## Descrizione
Attualmente l'URL dell'API backend è hardcoded in `ExportPanel.vue`. Questo causa problemi quando:
- Frontend e backend sono su macchine diverse
- Si cambia ambiente (dev/staging/prod)
- Si usa un IP diverso per il backend

## Proposta
- Usare variabili d'ambiente o file di configurazione
- Leggere l'URL da un file `config.json` o `.env`
- Implementare fallback automatico

## File da modificare
- `frontend/src/components/ExportPanel.vue`
- Creare `frontend/src/config.js` o usare `.env`

## Priorità
Media

## Tag
[enhancement] [configuration] [frontend]