"""
MiroFish Backend - Flaskfabbrica di applicazioni
"""

import os
import warnings

# inibire multiprocessing resource_tracker warnings (da librerie di terze parti come transformers）
# Deve essere impostato prima di tutte le altre importazioni
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """FlaskApply factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Imposta la codifica JSON: assicurati che il cinese venga visualizzato direttamente (invece di \uXXXX Formato）
    # Flask >= 2.3 Utilizzare app.json.ensure_ascii，Utilizza versioni precedenti JSON_AS_ASCII Configurazione
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # Registro di installazione
    logger = setup_logger('mirofish')
    
    # Stampa solo le informazioni di avvio nel sottoprocesso del reloader (evita di stampare due volte in modalità debug)）
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend Inizio...")
        logger.info("=" * 50)
    
    # abilitareCORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Funzione di pulizia del processo di simulazione del registro (garantisce che tutti i processi di simulazione vengano terminati quando il server viene spento）
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Funzione di pulizia del processo di simulazione registrata")
    
    # Richiedi il middleware di registro
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Richiesta: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Richiedi corpo: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"risposta: {response.status_code}")
        return response
    
    # Progetto di registrazione
    from .api import graph_bp, simulation_bp, report_bp, export_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(export_bp, url_prefix='/api/export')
    
    # controllo sanitario
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}
    
    if should_log_startup:
        logger.info("MiroFish Backend Avvio completato")
    
    return app

