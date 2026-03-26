"""
Gestione della configurazione
Unificare dalla directory root del progetto .env Configurazione caricamento file
"""

import os
from dotenv import load_dotenv

# Carica la directory principale del progetto .env Archivio
# percorso: MiroFish/.env (relativo a backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # Se la directory root non ha .env，Prova a caricare le variabili di ambiente (per ambienti di produzione）
    load_dotenv(override=True)


class Config:
    """FlaskClasse di configurazione"""
    
    # FlaskConfigurazione
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSONConfigurazione: disabilita l'escape ASCII e lascia che il cinese venga visualizzato direttamente (invece di \uXXXX Formato）
    JSON_AS_ASCII = False
    
    # LLMConfigurazione (uso unificato del formato OpenAI）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # ZepConfigurazione
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # Configurazione caricamento file
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # Text processing configuration
    DEFAULT_CHUNK_SIZE = 500  # Dimensione di taglio predefinita
    DEFAULT_CHUNK_OVERLAP = 50  # Dimensioni di sovrapposizione predefinite
    
    # OASISConfigurazione della simulazione
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASISConfigurazioni di azioni disponibili sulla piattaforma
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report AgentConfigurazione
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def validate(cls):
        """Verificare la configurazione necessaria"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY Non configurato")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY Non configurato")
        return errors

