# Issue 10: Automatizzazione changelog

## Titolo
**Automated Changelog and Release Notes Generation**

## Descrizione
Ogni export è potenzialmente una release. Manca un sistema per tracciare cosa cambia tra export.

## Proposta
- Generare changelog automatico basato su:
  - Data export
  - Versione progetto
  - File inclusi
  - Metadati (utente, note)
- Includere nel ZIP un `CHANGELOG.md`
- Opzionale: tagging automatico git

## File da modificare
- `backend/app/services/export_service.py`

## Priorità
Bassa

## Tag
[automation] [release] [changelog]