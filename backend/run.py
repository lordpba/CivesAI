"""
MiroFish Backend Entrata di avvio
"""

import os
import sys

# Risolvi problema codifica Windows: imposta codifica UTF-8 prima di altre importazioni
if sys.platform == 'win32':
    # Imposta la variabile d'ambiente affinché Python utilizzi UTF-8
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # Riconfigura lo stream di output standard su UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Aggiungi directory radice del progetto al percorso
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    """Funzione principale"""
    # Verifica configurazione
    errors = Config.validate()
    if errors:
        print("Errore configurazione:")
        for err in errors:
            print(f"  - {err}")
        print("\nSi prega di verificare la configurazione nel file .env")
        sys.exit(1)
    
    # Crea applicazione
    app = create_app()
    
    # Ottieni configurazione di esecuzione
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG
    
    # Avvia servizio
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()

