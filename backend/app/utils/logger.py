"""
Modulo di configurazione del registro
Fornisci gestione unificata dei log e output su console e file contemporaneamente
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler


def _ensure_utf8_stdout():
    """
    Make sure stdout/stderr uses UTF-8 encoding
    Risolvi il problema dei caratteri cinesi confusi nella console Windows
    """
    if sys.platform == 'win32':
        # Windows Riconfigurare l'output standard come UTF-8
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Directory di registro
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')


def setup_logger(name: str = 'mirofish', level: int = logging.DEBUG) -> logging.Logger:
    """
    Configura il registratore
    
    Args:
        name: Nome del registratore
        level: Livello di registro
        
    Returns:
        Registratore configurato
    """
    # Assicurati che la directory dei log esista
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Crea registratore
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Impedisce la propagazione dei log verso l'alto fino al logger root per evitare output ripetuti
    logger.propagate = False
    
    # Se è già presente un processore, non aggiungerlo nuovamente
    if logger.handlers:
        return logger
    
    # Formato registro
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 1. Elaboratore di file: registro dettagliato (nominato per data, con rotazione）
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # 2. Console Handler - Concise Log (INFO and above）
    # Assicurati di utilizzare la codifica UTF-8 in Windows per evitare caratteri cinesi confusi
    _ensure_utf8_stdout()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # Aggiungi processore
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str = 'mirofish') -> logging.Logger:
    """
    Ottieni il logger (crealo se non esiste)）
    
    Args:
        name: Nome del registratore
        
    Returns:
        Istanza del registratore
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Crea logger predefinito
logger = setup_logger()


# Metodo di convenienza
def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)

