"""
OASIS Script preimpostato per la simulazione parallela a doppia piattaforma
Esegui simulazioni Twitter e Reddit contemporaneamente, leggendo gli stessi file di configurazione

Caratteristiche:
- Simulazione parallela su doppia piattaforma (Twitter + Reddit).
- Non chiudere l'ambiente immediatamente dopo aver completato la simulazione ed entrare nella modalità di comando in attesa
- Supporta la ricezione di comandi di intervista tramite IPC
-Supporta interviste a singolo agente e interviste batch
-Supporta il comando dell'ambiente di spegnimento remoto

Utilizzo:
    python run_parallel_simulation.py --config simulation_config.json
    python run_parallel_simulation.py --config simulation_config.json --no-wait  # Chiudere immediatamente una volta terminato
    python run_parallel_simulation.py --config simulation_config.json --twitter-only
    python run_parallel_simulation.py --config simulation_config.json --reddit-only

Struttura del registro:
    sim_xxx/
    ├── twitter/
    │   └── actions.jsonl    # Twitter Registro delle azioni della piattaforma
    ├── reddit/
    │   └── actions.jsonl    # Reddit Registro delle azioni della piattaforma
    ├── simulation.log       # Registro principale del processo di simulazione
    └── run_state.json       # Stato di esecuzione (per query API）
"""

# ============================================================
# Risolvi i problemi di codifica di Windows: imposta la codifica UTF-8 prima di tutte le importazioni
# Questo serve per risolvere il problema che la codifica non viene specificata quando la libreria di terze parti OASIS legge i file
# ============================================================
import sys
import os

if sys.platform == 'win32':
    # Imposta la codifica I/O predefinita di Python su UTF-8
    # Ciò influisce su tutte le codifiche non specificate open() chiamare
    os.environ.setdefault('PYTHONUTF8', '1')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    
    # Riconfigura il flusso di output standard su UTF-8 (risolvi i caratteri cinesi confusi sulla console)）
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    # Forza una codifica predefinita (influenza open() Codifica predefinita per le funzioni）
    # Nota: è necessario impostarlo all'avvio di Python e l'impostazione del runtime potrebbe non avere effetto.
    # Quindi abbiamo bisogno anche della funzione open integrata di Monkey-Patch
    import builtins
    _original_open = builtins.open
    
    def _utf8_open(file, mode='r', buffering=-1, encoding=None, errors=None, 
                   newline=None, closefd=True, opener=None):
        """
        imballaggio open() funzione, che utilizza la codifica UTF-8 per impostazione predefinita per la modalità testo
        Ciò risolve un problema per cui le librerie di terze parti (come OASIS) leggono file senza specificare la codifica
        """
        # Imposta la codifica predefinita solo per la modalità testo (non binaria) e non è specificata alcuna codifica
        if encoding is None and 'b' not in mode:
            encoding = 'utf-8'
        return _original_open(file, mode, buffering, encoding, errors, 
                              newline, closefd, opener)
    
    builtins.open = _utf8_open

import argparse
import asyncio
import json
import logging
import multiprocessing
import random
import signal
import sqlite3
import warnings
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple


# Variabili globali: utilizzate per l'elaborazione del segnale
_shutdown_event = None
_cleanup_done = False

# Aggiungi la directory back-end al percorso
# Lo script si trova nella directory backend/scripts/
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, '..'))
_project_root = os.path.abspath(os.path.join(_backend_dir, '..'))
sys.path.insert(0, _scripts_dir)
sys.path.insert(0, _backend_dir)

# Carica la directory principale del progetto .env file (contenenti LLM_API_KEY e altre configurazioni）
from dotenv import load_dotenv
_env_file = os.path.join(_project_root, '.env')
if os.path.exists(_env_file):
    load_dotenv(_env_file)
    print(f"Configurazione dell'ambiente caricata: {_env_file}")
else:
    # prova a caricare backend/.env
    _backend_env = os.path.join(_backend_dir, '.env')
    if os.path.exists(_backend_env):
        load_dotenv(_backend_env)
        print(f"Configurazione dell'ambiente caricata: {_backend_env}")


class MaxTokensWarningFilter(logging.Filter):
    """Filtra camel-ai Informazioni max_tokens avviso (non impostiamo intenzionalmente max_tokens，Lasciamo che il modello decida da solo）"""
    
    def filter(self, record):
        # filtrare contiene max_tokens registro degli avvisi
        if "max_tokens" in record.getMessage() and "Invalid or missing" in record.getMessage():
            return False
        return True


# Aggiungi il filtro immediatamente quando il modulo viene caricato per assicurarti che abbia effetto prima che il codice camel venga eseguito
logging.getLogger().addFilter(MaxTokensWarningFilter())


def disable_oasis_logging():
    """
    Disabilita l'output di registrazione dettagliato per la libreria OASIS
    I log di OASIS sono troppo ridondanti (registrano le osservazioni e le azioni di ciascun agente), utilizziamo i nostri action_logger
    """
    # Disabilita tutti i logger per OASIS
    oasis_loggers = [
        "social.agent",
        "social.twitter", 
        "social.rec",
        "oasis.env",
        "table",
    ]
    
    for logger_name in oasis_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)  # Registra solo gli errori gravi
        logger.handlers.clear()
        logger.propagate = False


def init_logging_for_simulation(simulation_dir: str):
    """
    Inizializza la configurazione del registro simulato
    
    Args:
        simulation_dir: Percorso della directory di simulazione
    """
    # Disabilita la registrazione dettagliata di OASIS
    disable_oasis_logging()
    
    # Pulisci la vecchia directory di registro (se esiste）
    old_log_dir = os.path.join(simulation_dir, "log")
    if os.path.exists(old_log_dir):
        import shutil
        shutil.rmtree(old_log_dir, ignore_errors=True)


from action_logger import SimulationLogManager, PlatformActionLogger

try:
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    import oasis
    from oasis import (
        ActionType,
        LLMAction,
        ManualAction,
        generate_twitter_agent_graph,
        generate_reddit_agent_graph
    )
except ImportError as e:
    print(f"Errore: Dipendenze mancanti {e}")
    print("Si prega di installare prima: pip install oasis-ai camel-ai")
    sys.exit(1)


# TwitterLe azioni disponibili (escluso INTERVISTA, INTERVISTA possono essere attivate solo manualmente tramite Azione Manuale）
TWITTER_ACTIONS = [
    ActionType.CREATE_POST,
    ActionType.LIKE_POST,
    ActionType.REPOST,
    ActionType.FOLLOW,
    ActionType.DO_NOTHING,
    ActionType.QUOTE_POST,
]

# RedditLe azioni disponibili (escluso INTERVISTA, INTERVISTA possono essere attivate solo manualmente tramite Azione Manuale）
REDDIT_ACTIONS = [
    ActionType.LIKE_POST,
    ActionType.DISLIKE_POST,
    ActionType.CREATE_POST,
    ActionType.CREATE_COMMENT,
    ActionType.LIKE_COMMENT,
    ActionType.DISLIKE_COMMENT,
    ActionType.SEARCH_POSTS,
    ActionType.SEARCH_USER,
    ActionType.TREND,
    ActionType.REFRESH,
    ActionType.DO_NOTHING,
    ActionType.FOLLOW,
    ActionType.MUTE,
]


# IPCCostanti correlate
IPC_COMMANDS_DIR = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE = "env_status.json"

class CommandType:
    """Tipo di comando costante"""
    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"


class ParallelIPCHandler:
    """
    Processore di comandi IPC a doppia piattaforma
    
    Gestisci l'ambiente di entrambe le piattaforme ed elabora i comandi di intervista
    """
    
    def __init__(
        self,
        simulation_dir: str,
        twitter_env=None,
        twitter_agent_graph=None,
        reddit_env=None,
        reddit_agent_graph=None
    ):
        self.simulation_dir = simulation_dir
        self.twitter_env = twitter_env
        self.twitter_agent_graph = twitter_agent_graph
        self.reddit_env = reddit_env
        self.reddit_agent_graph = reddit_agent_graph
        
        self.commands_dir = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file = os.path.join(simulation_dir, ENV_STATUS_FILE)
        
        # Assicurati che la directory esista
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
    
    def update_status(self, status: str):
        """Aggiorna lo stato dell'ambiente"""
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "twitter_available": self.twitter_env is not None,
                "reddit_available": self.reddit_env is not None,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def poll_command(self) -> Optional[Dict[str, Any]]:
        """Interrogazione per comandi in sospeso"""
        if not os.path.exists(self.commands_dir):
            return None
        
        # Ottieni i file di comando (ordinati per ora）
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))
        
        command_files.sort(key=lambda x: x[1])
        
        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
        
        return None
    
    def send_response(self, command_id: str, status: str, result: Dict = None, error: str = None):
        """Invia risposta"""
        response = {
            "command_id": command_id,
            "status": status,
            "result": result,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response, f, ensure_ascii=False, indent=2)
        
        # Elimina il file di comando
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass
    
    def _get_env_and_graph(self, platform: str):
        """
        Ottieni l'ambiente e l'ambiente della piattaforma specificataagent_graph
        
        Args:
            platform: Nome della piattaforma ("twitter" o "reddit")
            
        Returns:
            (env, agent_graph, platform_name) o (None, None, None)
        """
        if platform == "twitter" and self.twitter_env:
            return self.twitter_env, self.twitter_agent_graph, "twitter"
        elif platform == "reddit" and self.reddit_env:
            return self.reddit_env, self.reddit_agent_graph, "reddit"
        else:
            return None, None, None
    
    async def _interview_single_platform(self, agent_id: int, prompt: str, platform: str) -> Dict[str, Any]:
        """
        Esegui su un'unica piattaformaInterview
        
        Returns:
            un dizionario contenente risultati o un dizionario contenente errori
        """
        env, agent_graph, actual_platform = self._get_env_and_graph(platform)
        
        if not env or not agent_graph:
            return {"platform": platform, "error": f"{platform}La piattaforma non è disponibile"}
        
        try:
            agent = agent_graph.get_agent(agent_id)
            interview_action = ManualAction(
                action_type=ActionType.INTERVIEW,
                action_args={"prompt": prompt}
            )
            actions = {agent: interview_action}
            await env.step(actions)
            
            result = self._get_interview_result(agent_id, actual_platform)
            result["platform"] = actual_platform
            return result
            
        except Exception as e:
            return {"platform": platform, "error": str(e)}
    
    async def handle_interview(self, command_id: str, agent_id: int, prompt: str, platform: str = None) -> bool:
        """
        Gestione di un singolo comando di intervista dell'agente
        
        Args:
            command_id: comandoID
            agent_id: Agent ID
            prompt: domande dell'intervista
            platform: Specifica la piattaforma (facoltativo)）
                - "twitter": Intervista solo su piattaforma Twitter
                - "reddit": Intervista solo su piattaforma Reddit
                - Nessuno/non specificare: Intervista due piattaforme contemporaneamente e restituisci i risultati integrati
            
        Returns:
            True indica il successo, falso esprimerefallito
        """
        # Se viene specificata una piattaforma, verrà intervistata solo quella piattaforma
        if platform in ("twitter", "reddit"):
            result = await self._interview_single_platform(agent_id, prompt, platform)
            
            if "error" in result:
                self.send_response(command_id, "failed", error=result["error"])
                print(f"  Interviewfallito: agent_id={agent_id}, platform={platform}, error={result['error']}")
                return False
            else:
                self.send_response(command_id, "completed", result=result)
                print(f"  InterviewCompleto: agent_id={agent_id}, platform={platform}")
                return True
        
        # Piattaforma non specificata: intervista su due piattaforme contemporaneamente
        if not self.twitter_env and not self.reddit_env:
            self.send_response(command_id, "failed", error="Nessun ambiente di simulazione disponibile")
            return False
        
        results = {
            "agent_id": agent_id,
            "prompt": prompt,
            "platforms": {}
        }
        success_count = 0
        
        # Interviste parallele su due piattaforme
        tasks = []
        platforms_to_interview = []
        
        if self.twitter_env:
            tasks.append(self._interview_single_platform(agent_id, prompt, "twitter"))
            platforms_to_interview.append("twitter")
        
        if self.reddit_env:
            tasks.append(self._interview_single_platform(agent_id, prompt, "reddit"))
            platforms_to_interview.append("reddit")
        
        # Esecuzione parallela
        platform_results = await asyncio.gather(*tasks)
        
        for platform_name, platform_result in zip(platforms_to_interview, platform_results):
            results["platforms"][platform_name] = platform_result
            if "error" not in platform_result:
                success_count += 1
        
        if success_count > 0:
            self.send_response(command_id, "completed", result=results)
            print(f"  InterviewCompleto: agent_id={agent_id}, Numero di piattaforme di successo={success_count}/{len(platforms_to_interview)}")
            return True
        else:
            errors = [f"{p}: {r.get('error', 'errore sconosciuto')}" for p, r in results["platforms"].items()]
            self.send_response(command_id, "failed", error="; ".join(errors))
            print(f"  Interviewfallito: agent_id={agent_id}, Tutte le piattaforme falliscono")
            return False
    
    async def handle_batch_interview(self, command_id: str, interviews: List[Dict], platform: str = None) -> bool:
        """
        Elabora comandi di intervista in batch
        
        Args:
            command_id: comandoID
            interviews: [{"agent_id": int, "prompt": str, "platform": str(optional)}, ...]
            platform: Piattaforma predefinita (può essere sostituita da ciascun elemento dell'intervista）
                - "twitter": Intervista solo su piattaforma Twitter
                - "reddit": Intervista solo su piattaforma Reddit
                - Nessuno/non specificare: Ogni Agente intervista due piattaforme contemporaneamente
        """
        # Raggruppa per piattaforma
        twitter_interviews = []
        reddit_interviews = []
        both_platforms_interviews = []  # Necessità di intervistare due piattaforme contemporaneamente
        
        for interview in interviews:
            item_platform = interview.get("platform", platform)
            if item_platform == "twitter":
                twitter_interviews.append(interview)
            elif item_platform == "reddit":
                reddit_interviews.append(interview)
            else:
                # Piattaforma non specificata: intervistato su entrambe le piattaforme
                both_platforms_interviews.append(interview)
        
        # mettere both_platforms_interviews Diviso in due piattaforme
        if both_platforms_interviews:
            if self.twitter_env:
                twitter_interviews.extend(both_platforms_interviews)
            if self.reddit_env:
                reddit_interviews.extend(both_platforms_interviews)
        
        results = {}
        
        # Gestire le interviste sulla piattaforma Twitter
        if twitter_interviews and self.twitter_env:
            try:
                twitter_actions = {}
                for interview in twitter_interviews:
                    agent_id = interview.get("agent_id")
                    prompt = interview.get("prompt", "")
                    try:
                        agent = self.twitter_agent_graph.get_agent(agent_id)
                        twitter_actions[agent] = ManualAction(
                            action_type=ActionType.INTERVIEW,
                            action_args={"prompt": prompt}
                        )
                    except Exception as e:
                        print(f"  avvertimento: Impossibile ottenereTwitter Agent {agent_id}: {e}")
                
                if twitter_actions:
                    await self.twitter_env.step(twitter_actions)
                    
                    for interview in twitter_interviews:
                        agent_id = interview.get("agent_id")
                        result = self._get_interview_result(agent_id, "twitter")
                        result["platform"] = "twitter"
                        results[f"twitter_{agent_id}"] = result
            except Exception as e:
                print(f"  TwitterLe interviste batch sono fallite: {e}")
        
        # Gestione interviste sulla piattaforma Reddit
        if reddit_interviews and self.reddit_env:
            try:
                reddit_actions = {}
                for interview in reddit_interviews:
                    agent_id = interview.get("agent_id")
                    prompt = interview.get("prompt", "")
                    try:
                        agent = self.reddit_agent_graph.get_agent(agent_id)
                        reddit_actions[agent] = ManualAction(
                            action_type=ActionType.INTERVIEW,
                            action_args={"prompt": prompt}
                        )
                    except Exception as e:
                        print(f"  avvertimento: Impossibile ottenereReddit Agent {agent_id}: {e}")
                
                if reddit_actions:
                    await self.reddit_env.step(reddit_actions)
                    
                    for interview in reddit_interviews:
                        agent_id = interview.get("agent_id")
                        result = self._get_interview_result(agent_id, "reddit")
                        result["platform"] = "reddit"
                        results[f"reddit_{agent_id}"] = result
            except Exception as e:
                print(f"  RedditLe interviste batch sono fallite: {e}")
        
        if results:
            self.send_response(command_id, "completed", result={
                "interviews_count": len(results),
                "results": results
            })
            print(f"  Interviste batch completate: {len(results)} unAgent")
            return True
        else:
            self.send_response(command_id, "failed", error="Nessun colloquio riuscito")
            return False
    
    def _get_interview_result(self, agent_id: int, platform: str) -> Dict[str, Any]:
        """Ottieni gli ultimi risultati dell'intervista dal database"""
        db_path = os.path.join(self.simulation_dir, f"{platform}_simulation.db")
        
        result = {
            "agent_id": agent_id,
            "response": None,
            "timestamp": None
        }
        
        if not os.path.exists(db_path):
            return result
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Interrogare gli ultimi record dell'intervista
            cursor.execute("""
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (ActionType.INTERVIEW.value, agent_id))
            
            row = cursor.fetchone()
            if row:
                user_id, info_json, created_at = row
                try:
                    info = json.loads(info_json) if info_json else {}
                    result["response"] = info.get("response", info)
                    result["timestamp"] = created_at
                except json.JSONDecodeError:
                    result["response"] = info_json
            
            conn.close()
            
        except Exception as e:
            print(f"  Impossibile leggere i risultati dell'intervista: {e}")
        
        return result
    
    async def process_commands(self) -> bool:
        """
        Elabora tutti i comandi in sospeso
        
        Returns:
            True significa continuare a correre, False significa che dovrebbe uscire
        """
        command = self.poll_command()
        if not command:
            return True
        
        command_id = command.get("command_id")
        command_type = command.get("command_type")
        args = command.get("args", {})
        
        print(f"\nComando IPC ricevuto: {command_type}, id={command_id}")
        
        if command_type == CommandType.INTERVIEW:
            await self.handle_interview(
                command_id,
                args.get("agent_id", 0),
                args.get("prompt", ""),
                args.get("platform")
            )
            return True
            
        elif command_type == CommandType.BATCH_INTERVIEW:
            await self.handle_batch_interview(
                command_id,
                args.get("interviews", []),
                args.get("platform")
            )
            return True
            
        elif command_type == CommandType.CLOSE_ENV:
            print("Ricevere un comando di arresto dell'ambiente")
            self.send_response(command_id, "completed", result={"message": "L'ambiente sta per chiudere"})
            return False
        
        else:
            self.send_response(command_id, "failed", error=f"Tipo di comando sconosciuto: {command_type}")
            return True


def load_config(config_path: str) -> Dict[str, Any]:
    """Carica il file di configurazione"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# Tipi di azioni non principali che devono essere filtrate (queste azioni hanno un valore inferiore per l'analisi）
FILTERED_ACTIONS = {'refresh', 'sign_up'}

# Tabella di mappatura del tipo di azione (nome nel database -> Nome standard）
ACTION_TYPE_MAP = {
    'create_post': 'CREATE_POST',
    'like_post': 'LIKE_POST',
    'dislike_post': 'DISLIKE_POST',
    'repost': 'REPOST',
    'quote_post': 'QUOTE_POST',
    'follow': 'FOLLOW',
    'mute': 'MUTE',
    'create_comment': 'CREATE_COMMENT',
    'like_comment': 'LIKE_COMMENT',
    'dislike_comment': 'DISLIKE_COMMENT',
    'search_posts': 'SEARCH_POSTS',
    'search_user': 'SEARCH_USER',
    'trend': 'TREND',
    'do_nothing': 'DO_NOTHING',
    'interview': 'INTERVIEW',
}


def get_agent_names_from_config(config: Dict[str, Any]) -> Dict[int, str]:
    """
    da simulation_config Entra agent_id -> entity_name mappatura
    
    Questo può essere fatto actions.jsonl visualizza il nome reale dell'entità invece di "Agent_0" Un nome in codice del genere
    
    Args:
        config: simulation_config.json contenuto
        
    Returns:
        agent_id -> entity_name dizionario cartografico
    """
    agent_names = {}
    agent_configs = config.get("agent_configs", [])
    
    for agent_config in agent_configs:
        agent_id = agent_config.get("agent_id")
        entity_name = agent_config.get("entity_name", f"Agent_{agent_id}")
        if agent_id is not None:
            agent_names[agent_id] = entity_name
    
    return agent_names


def fetch_new_actions_from_db(
    db_path: str,
    last_rowid: int,
    agent_names: Dict[int, str]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Ottieni nuovi record di azioni dal database e integrali con informazioni contestuali complete
    
    Args:
        db_path: Percorso del file del database
        last_rowid: Valore massimo rowid letto l'ultima volta (usa rowid invece di created_at，Perché piattaforme diverse created_at Diversi formati）
        agent_names: agent_id -> agent_name mappatura
        
    Returns:
        (actions_list, new_last_rowid)
        - actions_list: Elenco azioni, ogni elemento contiene agent_id, agent_name, action_type, action_args（Contiene informazioni contestuali）
        - new_last_rowid: nuovo valore massimo della riga
    """
    actions = []
    new_last_rowid = last_rowid
    
    if not os.path.exists(db_path):
        return actions, new_last_rowid
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Utilizza rowid per tenere traccia dei record elaborati (rowid è il campo di incremento automatico integrato di SQLite）
        # Questo può essere evitato created_at Problema di differenza di formato (Twitter utilizza numeri interi, Reddit utilizza stringhe di data e ora）
        cursor.execute("""
            SELECT rowid, user_id, action, info
            FROM trace
            WHERE rowid > ?
            ORDER BY rowid ASC
        """, (last_rowid,))
        
        for rowid, user_id, action, info_json in cursor.fetchall():
            # Aggiorna massimo rowid
            new_last_rowid = rowid
            
            # Filtra le azioni non principali
            if action in FILTERED_ACTIONS:
                continue
            
            # Analizzare i parametri dell'azione
            try:
                action_args = json.loads(info_json) if info_json else {}
            except json.JSONDecodeError:
                action_args = {}
            
            # Semplificare action_args，Mantieni solo i campi chiave (mantieni il contenuto completo senza troncamento)）
            simplified_args = {}
            if 'content' in action_args:
                simplified_args['content'] = action_args['content']
            if 'post_id' in action_args:
                simplified_args['post_id'] = action_args['post_id']
            if 'comment_id' in action_args:
                simplified_args['comment_id'] = action_args['comment_id']
            if 'quoted_id' in action_args:
                simplified_args['quoted_id'] = action_args['quoted_id']
            if 'new_post_id' in action_args:
                simplified_args['new_post_id'] = action_args['new_post_id']
            if 'follow_id' in action_args:
                simplified_args['follow_id'] = action_args['follow_id']
            if 'query' in action_args:
                simplified_args['query'] = action_args['query']
            if 'like_id' in action_args:
                simplified_args['like_id'] = action_args['like_id']
            if 'dislike_id' in action_args:
                simplified_args['dislike_id'] = action_args['dislike_id']
            
            # Nome del tipo di azione di conversione
            action_type = ACTION_TYPE_MAP.get(action, action.upper())
            
            # Informazioni contestuali supplementari (contenuto del post、Nome utente ecc.）
            _enrich_action_context(cursor, action_type, simplified_args, agent_names)
            
            actions.append({
                'agent_id': user_id,
                'agent_name': agent_names.get(user_id, f'Agent_{user_id}'),
                'action_type': action_type,
                'action_args': simplified_args,
            })
        
        conn.close()
    except Exception as e:
        print(f"Impossibile leggere l'azione del database: {e}")
    
    return actions, new_last_rowid


def _enrich_action_context(
    cursor,
    action_type: str,
    action_args: Dict[str, Any],
    agent_names: Dict[int, str]
) -> None:
    """
    Integra le azioni con informazioni contestuali (pubblica contenuto、Nome utente ecc.）
    
    Args:
        cursor: Cursore del database
        action_type: tipo di azione
        action_args: Parametri dell'azione (verranno modificati）
        agent_names: agent_id -> agent_name mappatura
    """
    try:
        # Mi piace/Non mi piace il post: integra il contenuto e l'autore del post
        if action_type in ('LIKE_POST', 'DISLIKE_POST'):
            post_id = action_args.get('post_id')
            if post_id:
                post_info = _get_post_info(cursor, post_id, agent_names)
                if post_info:
                    action_args['post_content'] = post_info.get('content', '')
                    action_args['post_author_name'] = post_info.get('author_name', '')
        
        # Repost: integra il contenuto e l'autore del post originale
        elif action_type == 'REPOST':
            new_post_id = action_args.get('new_post_id')
            if new_post_id:
                # Post inoltrato original_post_id Punta al post originale
                cursor.execute("""
                    SELECT original_post_id FROM post WHERE post_id = ?
                """, (new_post_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    original_post_id = row[0]
                    original_info = _get_post_info(cursor, original_post_id, agent_names)
                    if original_info:
                        action_args['original_content'] = original_info.get('content', '')
                        action_args['original_author_name'] = original_info.get('author_name', '')
        
        # Post citato: integra il contenuto del post originale、Commenti dell'autore e della citazione
        elif action_type == 'QUOTE_POST':
            quoted_id = action_args.get('quoted_id')
            new_post_id = action_args.get('new_post_id')
            
            if quoted_id:
                original_info = _get_post_info(cursor, quoted_id, agent_names)
                if original_info:
                    action_args['original_content'] = original_info.get('content', '')
                    action_args['original_author_name'] = original_info.get('author_name', '')
            
            # Ottieni il contenuto del commento del post di riferimento（quote_content）
            if new_post_id:
                cursor.execute("""
                    SELECT quote_content FROM post WHERE post_id = ?
                """, (new_post_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    action_args['quote_content'] = row[0]
        
        # Segui utenti: integra il nome dell'utente seguito
        elif action_type == 'FOLLOW':
            follow_id = action_args.get('follow_id')
            if follow_id:
                # Ottieni dalla tabella seguente followee_id
                cursor.execute("""
                    SELECT followee_id FROM follow WHERE follow_id = ?
                """, (follow_id,))
                row = cursor.fetchone()
                if row:
                    followee_id = row[0]
                    target_name = _get_user_name(cursor, followee_id, agent_names)
                    if target_name:
                        action_args['target_user_name'] = target_name
        
        # Utente bloccato: integra il nome dell'utente bloccato
        elif action_type == 'MUTE':
            # da action_args Entra user_id o target_id
            target_id = action_args.get('user_id') or action_args.get('target_id')
            if target_id:
                target_name = _get_user_name(cursor, target_id, agent_names)
                if target_name:
                    action_args['target_user_name'] = target_name
        
        # Commenti Mi piace/Non mi piace: integra il contenuto e l'autore del commento
        elif action_type in ('LIKE_COMMENT', 'DISLIKE_COMMENT'):
            comment_id = action_args.get('comment_id')
            if comment_id:
                comment_info = _get_comment_info(cursor, comment_id, agent_names)
                if comment_info:
                    action_args['comment_content'] = comment_info.get('content', '')
                    action_args['comment_author_name'] = comment_info.get('author_name', '')
        
        # Pubblica un commento: integra le informazioni sul post commentato
        elif action_type == 'CREATE_COMMENT':
            post_id = action_args.get('post_id')
            if post_id:
                post_info = _get_post_info(cursor, post_id, agent_names)
                if post_info:
                    action_args['post_content'] = post_info.get('content', '')
                    action_args['post_author_name'] = post_info.get('author_name', '')
    
    except Exception as e:
        # La mancata integrazione del contesto non influisce sul processo principale
        print(f"Il contesto dell'azione supplementare non è riuscito: {e}")


def _get_post_info(
    cursor,
    post_id: int,
    agent_names: Dict[int, str]
) -> Optional[Dict[str, str]]:
    """
    Ottieni informazioni sul post
    
    Args:
        cursor: Cursore del database
        post_id: PostaID
        agent_names: agent_id -> agent_name mappatura
        
    Returns:
        Contiene contenuti e author_name dizionario, o None
    """
    try:
        cursor.execute("""
            SELECT p.content, p.user_id, u.agent_id
            FROM post p
            LEFT JOIN user u ON p.user_id = u.user_id
            WHERE p.post_id = ?
        """, (post_id,))
        row = cursor.fetchone()
        if row:
            content = row[0] or ''
            user_id = row[1]
            agent_id = row[2]
            
            # utilizzo prioritario agent_names nome dentro
            author_name = ''
            if agent_id is not None and agent_id in agent_names:
                author_name = agent_names[agent_id]
            elif user_id:
                # Ottieni il nome dalla tabella utente
                cursor.execute("SELECT name, user_name FROM user WHERE user_id = ?", (user_id,))
                user_row = cursor.fetchone()
                if user_row:
                    author_name = user_row[0] or user_row[1] or ''
            
            return {'content': content, 'author_name': author_name}
    except Exception:
        pass
    return None


def _get_user_name(
    cursor,
    user_id: int,
    agent_names: Dict[int, str]
) -> Optional[str]:
    """
    Ottieni il nome utente
    
    Args:
        cursor: Cursore del database
        user_id: UtenteID
        agent_names: agent_id -> agent_name mappatura
        
    Returns:
        nome utente o None
    """
    try:
        cursor.execute("""
            SELECT agent_id, name, user_name FROM user WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            agent_id = row[0]
            name = row[1]
            user_name = row[2]
            
            # utilizzo prioritario agent_names nome dentro
            if agent_id is not None and agent_id in agent_names:
                return agent_names[agent_id]
            return name or user_name or ''
    except Exception:
        pass
    return None


def _get_comment_info(
    cursor,
    comment_id: int,
    agent_names: Dict[int, str]
) -> Optional[Dict[str, str]]:
    """
    Ottieni informazioni sui commenti
    
    Args:
        cursor: Cursore del database
        comment_id: CommentoID
        agent_names: agent_id -> agent_name mappatura
        
    Returns:
        Contiene contenuti e author_name dizionario, o None
    """
    try:
        cursor.execute("""
            SELECT c.content, c.user_id, u.agent_id
            FROM comment c
            LEFT JOIN user u ON c.user_id = u.user_id
            WHERE c.comment_id = ?
        """, (comment_id,))
        row = cursor.fetchone()
        if row:
            content = row[0] or ''
            user_id = row[1]
            agent_id = row[2]
            
            # utilizzo prioritario agent_names nome dentro
            author_name = ''
            if agent_id is not None and agent_id in agent_names:
                author_name = agent_names[agent_id]
            elif user_id:
                # Ottieni il nome dalla tabella utente
                cursor.execute("SELECT name, user_name FROM user WHERE user_id = ?", (user_id,))
                user_row = cursor.fetchone()
                if user_row:
                    author_name = user_row[0] or user_row[1] or ''
            
            return {'content': content, 'author_name': author_name}
    except Exception:
        pass
    return None


def create_model(config: Dict[str, Any], use_boost: bool = False):
    """
    Crea modello LLM
    
    Supporta la configurazione dual LLM per velocizzare la simulazione parallela:
    - Configurazione comune：LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME
    - Configurazione dell'accelerazione (opzionale）：LLM_BOOST_API_KEY, LLM_BOOST_BASE_URL, LLM_BOOST_MODEL_NAME
    
    Se è configurato LLM accelerato, piattaforme diverse possono utilizzare diversi provider di servizi API durante la simulazione parallela per migliorare la concorrenza.。
    
    Args:
        config: Dizionario di configurazione della simulazione
        use_boost: Se utilizzare la configurazione LLM accelerata (se disponibile）
    """
    # Controlla se c'è la configurazione dell'accelerazione
    boost_api_key = os.environ.get("LLM_BOOST_API_KEY", "")
    boost_base_url = os.environ.get("LLM_BOOST_BASE_URL", "")
    boost_model = os.environ.get("LLM_BOOST_MODEL_NAME", "")
    has_boost_config = bool(boost_api_key)
    
    # Scegli quale utilizzare in base ai parametri e alla configurazione LLM
    if use_boost and has_boost_config:
        # Utilizza la configurazione dell'accelerazione
        llm_api_key = boost_api_key
        llm_base_url = boost_base_url
        llm_model = boost_model or os.environ.get("LLM_MODEL_NAME", "")
        config_label = "[accelerareLLM]"
    else:
        # Utilizza la configurazione comune
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        llm_base_url = os.environ.get("LLM_BASE_URL", "")
        llm_model = os.environ.get("LLM_MODEL_NAME", "")
        config_label = "[UniversaleLLM]"
    
    # se .env Se non è presente alcun nome del modello in , utilizzare config come fallback
    if not llm_model:
        llm_model = config.get("llm_model", "gpt-4o-mini")
    
    # Imposta le variabili di ambiente richieste da camel-ai
    if llm_api_key:
        os.environ["OPENAI_API_KEY"] = llm_api_key
    
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Manca la configurazione della chiave API, configurala nella directory root del progetto .env Impostato in archivio LLM_API_KEY")
    
    if llm_base_url:
        os.environ["OPENAI_API_BASE_URL"] = llm_base_url
    
    print(f"{config_label} model={llm_model}, base_url={llm_base_url[:40] if llm_base_url else 'Predefinito'}...")
    
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=llm_model,
    )


def get_active_agents_for_round(
    env,
    config: Dict[str, Any],
    current_hour: int,
    round_num: int
) -> List:
    """Decidi quali attivare questo round in base al tempo e alla configurazioneAgent"""
    time_config = config.get("time_config", {})
    agent_configs = config.get("agent_configs", [])
    
    base_min = time_config.get("agents_per_hour_min", 5)
    base_max = time_config.get("agents_per_hour_max", 20)
    
    peak_hours = time_config.get("peak_hours", [9, 10, 11, 14, 15, 20, 21, 22])
    off_peak_hours = time_config.get("off_peak_hours", [0, 1, 2, 3, 4, 5])
    
    if current_hour in peak_hours:
        multiplier = time_config.get("peak_activity_multiplier", 1.5)
    elif current_hour in off_peak_hours:
        multiplier = time_config.get("off_peak_activity_multiplier", 0.3)
    else:
        multiplier = 1.0
    
    target_count = int(random.uniform(base_min, base_max) * multiplier)
    
    candidates = []
    for cfg in agent_configs:
        agent_id = cfg.get("agent_id", 0)
        active_hours = cfg.get("active_hours", list(range(8, 23)))
        activity_level = cfg.get("activity_level", 0.5)
        
        if current_hour not in active_hours:
            continue
        
        if random.random() < activity_level:
            candidates.append(agent_id)
    
    selected_ids = random.sample(
        candidates, 
        min(target_count, len(candidates))
    ) if candidates else []
    
    active_agents = []
    for agent_id in selected_ids:
        try:
            agent = env.agent_graph.get_agent(agent_id)
            active_agents.append((agent_id, agent))
        except Exception:
            pass
    
    return active_agents


class PlatformSimulation:
    """Contenitore dei risultati della simulazione della piattaforma"""
    def __init__(self):
        self.env = None
        self.agent_graph = None
        self.total_actions = 0


async def run_twitter_simulation(
    config: Dict[str, Any], 
    simulation_dir: str,
    action_logger: Optional[PlatformActionLogger] = None,
    main_logger: Optional[SimulationLogManager] = None,
    max_rounds: Optional[int] = None
) -> PlatformSimulation:
    """Esegui una simulazione su Twitter
    
    Args:
        config: Configurazione della simulazione
        simulation_dir: Directory di simulazione
        action_logger: registratore di azioni
        main_logger: Gestore registro principale
        max_rounds: Numero massimo di cicli di simulazione (facoltativo, utilizzato per troncare le simulazioni troppo lunghe）
        
    Returns:
        PlatformSimulation: Contiene busta eagent_graphl'oggetto risultato
    """
    result = PlatformSimulation()
    
    def log_info(msg):
        if main_logger:
            main_logger.info(f"[Twitter] {msg}")
        print(f"[Twitter] {msg}")
    
    log_info("inizializzazione...")
    
    # Twitter Utilizzare la configurazione LLM generica
    model = create_model(config, use_boost=False)
    
    # OASIS TwitterUtilizza il formato CSV
    profile_path = os.path.join(simulation_dir, "twitter_profiles.csv")
    if not os.path.exists(profile_path):
        log_info(f"Errore: ProfileIl file non esiste: {profile_path}")
        return result
    
    result.agent_graph = await generate_twitter_agent_graph(
        profile_path=profile_path,
        model=model,
        available_actions=TWITTER_ACTIONS,
    )
    
    # Ottieni la mappatura del nome reale dell'agente dal file di configurazione (utilizzando entity_name piuttosto che quello predefinito Agent_X）
    agent_names = get_agent_names_from_config(config)
    # Se un agente non è presente nella configurazione, viene utilizzato il nome predefinito di OASIS
    for agent_id, agent in result.agent_graph.get_agents():
        if agent_id not in agent_names:
            agent_names[agent_id] = getattr(agent, 'name', f'Agent_{agent_id}')
    
    db_path = os.path.join(simulation_dir, "twitter_simulation.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    result.env = oasis.make(
        agent_graph=result.agent_graph,
        platform=oasis.DefaultPlatformType.TWITTER,
        database_path=db_path,
        semaphore=30,  # Limita il numero massimo di richieste LLM simultanee per evitare il sovraccarico dell'API
    )
    
    await result.env.reset()
    log_info("L'ambiente è iniziato")
    
    if action_logger:
        action_logger.log_simulation_start(config)
    
    total_actions = 0
    last_rowid = 0  # Tieni traccia dell'ultimo numero di riga elaborato nel database (usa rowid per evitare created_at Differenze di formato）
    
    # Esegui l'evento iniziale
    event_config = config.get("event_config", {})
    initial_posts = event_config.get("initial_posts", [])
    
    # Inizia il record del round 0 (fase iniziale dell'evento）
    if action_logger:
        action_logger.log_round_start(0, 0)  # round 0, simulated_hour 0
    
    initial_action_count = 0
    if initial_posts:
        initial_actions = {}
        for post in initial_posts:
            agent_id = post.get("poster_agent_id", 0)
            content = post.get("content", "")
            try:
                agent = result.env.agent_graph.get_agent(agent_id)
                initial_actions[agent] = ManualAction(
                    action_type=ActionType.CREATE_POST,
                    action_args={"content": content}
                )
                
                if action_logger:
                    action_logger.log_action(
                        round_num=0,
                        agent_id=agent_id,
                        agent_name=agent_names.get(agent_id, f"Agent_{agent_id}"),
                        action_type="CREATE_POST",
                        action_args={"content": content}
                    )
                    total_actions += 1
                    initial_action_count += 1
            except Exception:
                pass
        
        if initial_actions:
            await result.env.step(initial_actions)
            log_info(f"Pubblicato {len(initial_actions)} post iniziali")
    
    # Registra la fine del round 0
    if action_logger:
        action_logger.log_round_end(0, initial_action_count)
    
    # ciclo di simulazione principale
    time_config = config.get("time_config", {})
    total_hours = time_config.get("total_simulation_hours", 72)
    minutes_per_round = time_config.get("minutes_per_round", 30)
    total_rounds = (total_hours * 60) // minutes_per_round
    
    # Tronca se viene specificato il numero massimo di round
    if max_rounds is not None and max_rounds > 0:
        original_rounds = total_rounds
        total_rounds = min(total_rounds, max_rounds)
        if total_rounds < original_rounds:
            log_info(f"Turni troncati: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
    
    start_time = datetime.now()
    
    for round_num in range(total_rounds):
        # Controllare se è stato ricevuto il segnale di uscita
        if _shutdown_event and _shutdown_event.is_set():
            if main_logger:
                main_logger.info(f"Segnale di uscita ricevuto, nella sezione {round_num + 1} simulazione dell'arresto della ruota")
            break
        
        simulated_minutes = round_num * minutes_per_round
        simulated_hour = (simulated_minutes // 60) % 24
        simulated_day = simulated_minutes // (60 * 24) + 1
        
        active_agents = get_active_agents_for_round(
            result.env, config, simulated_hour, round_num
        )
        
        # Indipendentemente dal fatto che sia presente un agente attivo, viene registrato l'inizio del round.
        if action_logger:
            action_logger.log_round_start(round_num + 1, simulated_hour)
        
        if not active_agents:
            # La fine del round viene registrata anche quando non è presente alcun agente attivo.（actions_count=0）
            if action_logger:
                action_logger.log_round_end(round_num + 1, 0)
            continue
        
        actions = {agent: LLMAction() for _, agent in active_agents}
        await result.env.step(actions)
        
        # Ottieni le azioni effettivamente eseguite dal database e registrale
        actual_actions, last_rowid = fetch_new_actions_from_db(
            db_path, last_rowid, agent_names
        )
        
        round_action_count = 0
        for action_data in actual_actions:
            if action_logger:
                action_logger.log_action(
                    round_num=round_num + 1,
                    agent_id=action_data['agent_id'],
                    agent_name=action_data['agent_name'],
                    action_type=action_data['action_type'],
                    action_args=action_data['action_args']
                )
                total_actions += 1
                round_action_count += 1
        
        if action_logger:
            action_logger.log_round_end(round_num + 1, round_action_count)
        
        if (round_num + 1) % 20 == 0:
            progress = (round_num + 1) / total_rounds * 100
            log_info(f"Day {simulated_day}, {simulated_hour:02d}:00 - Round {round_num + 1}/{total_rounds} ({progress:.1f}%)")
    
    # Nota: non chiudere l'ambiente e riservarlo per l'uso nell'intervista
    
    if action_logger:
        action_logger.log_simulation_end(total_rounds, total_actions)
    
    result.total_actions = total_actions
    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(f"Ciclo di simulazione completato! Richiede tempo: {elapsed:.1f}secondi, azione totale: {total_actions}")
    
    return result


async def run_reddit_simulation(
    config: Dict[str, Any], 
    simulation_dir: str,
    action_logger: Optional[PlatformActionLogger] = None,
    main_logger: Optional[SimulationLogManager] = None,
    max_rounds: Optional[int] = None
) -> PlatformSimulation:
    """Esegui la simulazione di Reddit
    
    Args:
        config: Configurazione della simulazione
        simulation_dir: Directory di simulazione
        action_logger: registratore di azioni
        main_logger: Gestore registro principale
        max_rounds: Numero massimo di cicli di simulazione (facoltativo, utilizzato per troncare le simulazioni troppo lunghe）
        
    Returns:
        PlatformSimulation: Contiene busta eagent_graphl'oggetto risultato
    """
    result = PlatformSimulation()
    
    def log_info(msg):
        if main_logger:
            main_logger.info(f"[Reddit] {msg}")
        print(f"[Reddit] {msg}")
    
    log_info("inizializzazione...")
    
    # Reddit Utilizza la configurazione LLM accelerata se disponibile, altrimenti torna alla configurazione generica）
    model = create_model(config, use_boost=True)
    
    profile_path = os.path.join(simulation_dir, "reddit_profiles.json")
    if not os.path.exists(profile_path):
        log_info(f"Errore: ProfileIl file non esiste: {profile_path}")
        return result
    
    result.agent_graph = await generate_reddit_agent_graph(
        profile_path=profile_path,
        model=model,
        available_actions=REDDIT_ACTIONS,
    )
    
    # Ottieni la mappatura del nome reale dell'agente dal file di configurazione (utilizzando entity_name piuttosto che quello predefinito Agent_X）
    agent_names = get_agent_names_from_config(config)
    # Se un agente non è presente nella configurazione, viene utilizzato il nome predefinito di OASIS
    for agent_id, agent in result.agent_graph.get_agents():
        if agent_id not in agent_names:
            agent_names[agent_id] = getattr(agent, 'name', f'Agent_{agent_id}')
    
    db_path = os.path.join(simulation_dir, "reddit_simulation.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    result.env = oasis.make(
        agent_graph=result.agent_graph,
        platform=oasis.DefaultPlatformType.REDDIT,
        database_path=db_path,
        semaphore=30,  # Limita il numero massimo di richieste LLM simultanee per evitare il sovraccarico dell'API
    )
    
    await result.env.reset()
    log_info("L'ambiente è iniziato")
    
    if action_logger:
        action_logger.log_simulation_start(config)
    
    total_actions = 0
    last_rowid = 0  # Tieni traccia dell'ultimo numero di riga elaborato nel database (usa rowid per evitare created_at Differenze di formato）
    
    # Esegui l'evento iniziale
    event_config = config.get("event_config", {})
    initial_posts = event_config.get("initial_posts", [])
    
    # Inizia il record del round 0 (fase iniziale dell'evento）
    if action_logger:
        action_logger.log_round_start(0, 0)  # round 0, simulated_hour 0
    
    initial_action_count = 0
    if initial_posts:
        initial_actions = {}
        for post in initial_posts:
            agent_id = post.get("poster_agent_id", 0)
            content = post.get("content", "")
            try:
                agent = result.env.agent_graph.get_agent(agent_id)
                if agent in initial_actions:
                    if not isinstance(initial_actions[agent], list):
                        initial_actions[agent] = [initial_actions[agent]]
                    initial_actions[agent].append(ManualAction(
                        action_type=ActionType.CREATE_POST,
                        action_args={"content": content}
                    ))
                else:
                    initial_actions[agent] = ManualAction(
                        action_type=ActionType.CREATE_POST,
                        action_args={"content": content}
                    )
                
                if action_logger:
                    action_logger.log_action(
                        round_num=0,
                        agent_id=agent_id,
                        agent_name=agent_names.get(agent_id, f"Agent_{agent_id}"),
                        action_type="CREATE_POST",
                        action_args={"content": content}
                    )
                    total_actions += 1
                    initial_action_count += 1
            except Exception:
                pass
        
        if initial_actions:
            await result.env.step(initial_actions)
            log_info(f"Pubblicato {len(initial_actions)} post iniziali")
    
    # Registra la fine del round 0
    if action_logger:
        action_logger.log_round_end(0, initial_action_count)
    
    # ciclo di simulazione principale
    time_config = config.get("time_config", {})
    total_hours = time_config.get("total_simulation_hours", 72)
    minutes_per_round = time_config.get("minutes_per_round", 30)
    total_rounds = (total_hours * 60) // minutes_per_round
    
    # Tronca se viene specificato il numero massimo di round
    if max_rounds is not None and max_rounds > 0:
        original_rounds = total_rounds
        total_rounds = min(total_rounds, max_rounds)
        if total_rounds < original_rounds:
            log_info(f"Turni troncati: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
    
    start_time = datetime.now()
    
    for round_num in range(total_rounds):
        # Controllare se è stato ricevuto il segnale di uscita
        if _shutdown_event and _shutdown_event.is_set():
            if main_logger:
                main_logger.info(f"Segnale di uscita ricevuto, nella sezione {round_num + 1} simulazione dell'arresto della ruota")
            break
        
        simulated_minutes = round_num * minutes_per_round
        simulated_hour = (simulated_minutes // 60) % 24
        simulated_day = simulated_minutes // (60 * 24) + 1
        
        active_agents = get_active_agents_for_round(
            result.env, config, simulated_hour, round_num
        )
        
        # Indipendentemente dal fatto che sia presente un agente attivo, viene registrato l'inizio del round.
        if action_logger:
            action_logger.log_round_start(round_num + 1, simulated_hour)
        
        if not active_agents:
            # La fine del round viene registrata anche quando non è presente alcun agente attivo.（actions_count=0）
            if action_logger:
                action_logger.log_round_end(round_num + 1, 0)
            continue
        
        actions = {agent: LLMAction() for _, agent in active_agents}
        await result.env.step(actions)
        
        # Ottieni le azioni effettivamente eseguite dal database e registrale
        actual_actions, last_rowid = fetch_new_actions_from_db(
            db_path, last_rowid, agent_names
        )
        
        round_action_count = 0
        for action_data in actual_actions:
            if action_logger:
                action_logger.log_action(
                    round_num=round_num + 1,
                    agent_id=action_data['agent_id'],
                    agent_name=action_data['agent_name'],
                    action_type=action_data['action_type'],
                    action_args=action_data['action_args']
                )
                total_actions += 1
                round_action_count += 1
        
        if action_logger:
            action_logger.log_round_end(round_num + 1, round_action_count)
        
        if (round_num + 1) % 20 == 0:
            progress = (round_num + 1) / total_rounds * 100
            log_info(f"Day {simulated_day}, {simulated_hour:02d}:00 - Round {round_num + 1}/{total_rounds} ({progress:.1f}%)")
    
    # Nota: non chiudere l'ambiente e riservarlo per l'uso nell'intervista
    
    if action_logger:
        action_logger.log_simulation_end(total_rounds, total_actions)
    
    result.total_actions = total_actions
    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(f"Ciclo di simulazione completato! Richiede tempo: {elapsed:.1f}secondi, azione totale: {total_actions}")
    
    return result


async def main():
    parser = argparse.ArgumentParser(description='OASISSimulazione parallela a doppia piattaforma')
    parser.add_argument(
        '--config', 
        type=str, 
        required=True,
        help='Percorso del file di configurazione (simulation_config.json)'
    )
    parser.add_argument(
        '--twitter-only',
        action='store_true',
        help='Just run the Twitter simulation'
    )
    parser.add_argument(
        '--reddit-only',
        action='store_true',
        help='Basta eseguire la simulazione di Reddit'
    )
    parser.add_argument(
        '--max-rounds',
        type=int,
        default=None,
        help='Numero massimo di cicli di simulazione (facoltativo, utilizzato per troncare le simulazioni troppo lunghe）'
    )
    parser.add_argument(
        '--no-wait',
        action='store_true',
        default=False,
        help="Chiudere immediatamente l'ambiente al termine della simulazione e non accedere alla modalità di comando in attesa."
    )
    
    args = parser.parse_args()
    
    # Crea un evento di spegnimento all'inizio della funzione principale per garantire che l'intero programma possa rispondere al segnale di uscita
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    
    if not os.path.exists(args.config):
        print(f"Errore: Il file di configurazione non esiste: {args.config}")
        sys.exit(1)
    
    config = load_config(args.config)
    simulation_dir = os.path.dirname(args.config) or "."
    wait_for_commands = not args.no_wait
    
    # Inizializza la configurazione dei log (disabilita i log di OASIS, pulisci i vecchi file）
    init_logging_for_simulation(simulation_dir)
    
    # Crea un gestore di registri
    log_manager = SimulationLogManager(simulation_dir)
    twitter_logger = log_manager.get_twitter_logger()
    reddit_logger = log_manager.get_reddit_logger()
    
    log_manager.info("=" * 60)
    log_manager.info("OASIS Simulazione parallela a doppia piattaforma")
    log_manager.info(f"File di configurazione: {args.config}")
    log_manager.info(f"SimulazioneID: {config.get('simulation_id', 'unknown')}")
    log_manager.info(f"Attendi la modalità comando: {'abilitare' if wait_for_commands else 'Disabilita'}")
    log_manager.info("=" * 60)
    
    time_config = config.get("time_config", {})
    total_hours = time_config.get('total_simulation_hours', 72)
    minutes_per_round = time_config.get('minutes_per_round', 30)
    config_total_rounds = (total_hours * 60) // minutes_per_round
    
    log_manager.info(f"Parametri di simulazione:")
    log_manager.info(f"  - Tempo totale di simulazione: {total_hours}Ore")
    log_manager.info(f"  - Tempo per round: {minutes_per_round}Minuti")
    log_manager.info(f"  - Configura il numero totale di round: {config_total_rounds}")
    if args.max_rounds:
        log_manager.info(f"  - Limite massimo del numero di round: {args.max_rounds}")
        if args.max_rounds < config_total_rounds:
            log_manager.info(f"  - Turni di esecuzione effettivi: {args.max_rounds} (Troncato)")
    log_manager.info(f"  - AgentQuantità: {len(config.get('agent_configs', []))}")
    
    log_manager.info("Struttura del registro:")
    log_manager.info(f"  - registro principale: simulation.log")
    log_manager.info(f"  - Twitterazione: twitter/actions.jsonl")
    log_manager.info(f"  - Redditazione: reddit/actions.jsonl")
    log_manager.info("=" * 60)
    
    start_time = datetime.now()
    
    # Memorizza i risultati della simulazione per entrambe le piattaforme
    twitter_result: Optional[PlatformSimulation] = None
    reddit_result: Optional[PlatformSimulation] = None
    
    if args.twitter_only:
        twitter_result = await run_twitter_simulation(config, simulation_dir, twitter_logger, log_manager, args.max_rounds)
    elif args.reddit_only:
        reddit_result = await run_reddit_simulation(config, simulation_dir, reddit_logger, log_manager, args.max_rounds)
    else:
        # Esegui in parallelo (utilizza un logger separato per ciascuna piattaforma）
        results = await asyncio.gather(
            run_twitter_simulation(config, simulation_dir, twitter_logger, log_manager, args.max_rounds),
            run_reddit_simulation(config, simulation_dir, reddit_logger, log_manager, args.max_rounds),
        )
        twitter_result, reddit_result = results
    
    total_elapsed = (datetime.now() - start_time).total_seconds()
    log_manager.info("=" * 60)
    log_manager.info(f"Ciclo di simulazione completato! Tempo totale impiegato: {total_elapsed:.1f}secondi")
    
    # Se accedere alla modalità comando in attesa
    if wait_for_commands:
        log_manager.info("")
        log_manager.info("=" * 60)
        log_manager.info("Accedi alla modalità di attesa del comando: l'ambiente rimane in esecuzione")
        log_manager.info("Comandi supportati: interview, batch_interview, close_env")
        log_manager.info("=" * 60)
        
        # Crea gestore IPC
        ipc_handler = ParallelIPCHandler(
            simulation_dir=simulation_dir,
            twitter_env=twitter_result.env if twitter_result else None,
            twitter_agent_graph=twitter_result.agent_graph if twitter_result else None,
            reddit_env=reddit_result.env if reddit_result else None,
            reddit_agent_graph=reddit_result.agent_graph if reddit_result else None
        )
        ipc_handler.update_status("alive")
        
        # Attendi il ciclo di comandi (usando global _shutdown_event）
        try:
            while not _shutdown_event.is_set():
                should_continue = await ipc_handler.process_commands()
                if not should_continue:
                    break
                # Utilizzare wait_for Sostituisci il sonno, che è reattivo shutdown_event
                try:
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=0.5)
                    break  # Segnale di uscita ricevuto
                except asyncio.TimeoutError:
                    pass  # Continua il ciclo dopo il timeout
        except KeyboardInterrupt:
            print("\nSegnale di interruzione ricevuto")
        except asyncio.CancelledError:
            print("\nAttività annullata")
        except Exception as e:
            print(f"\nErrore nell'elaborazione del comando: {e}")
        
        log_manager.info("\nAmbiente chiuso...")
        ipc_handler.update_status("stopped")
    
    # Ambiente chiuso
    if twitter_result and twitter_result.env:
        await twitter_result.env.close()
        log_manager.info("[Twitter] L'ambiente è in crisi")
    
    if reddit_result and reddit_result.env:
        await reddit_result.env.close()
        log_manager.info("[Reddit] L'ambiente è in crisi")
    
    log_manager.info("=" * 60)
    log_manager.info(f"Tutto fatto!")
    log_manager.info(f"file di registro:")
    log_manager.info(f"  - {os.path.join(simulation_dir, 'simulation.log')}")
    log_manager.info(f"  - {os.path.join(simulation_dir, 'twitter', 'actions.jsonl')}")
    log_manager.info(f"  - {os.path.join(simulation_dir, 'reddit', 'actions.jsonl')}")
    log_manager.info("=" * 60)


def setup_signal_handlers(loop=None):
    """
    Configura il gestore del segnale per garantire l'uscita corretta durante la ricezione di SIGTERM/SIGINT
    
    Scenario di simulazione persistente: non uscire una volta completata la simulazione, attendere il comando di intervista
    Quando viene ricevuto un segnale di terminazione, è necessario：
    1. Notifica il ciclo asincrono per uscire dall'attesa
    2. Dare al programma la possibilità di ripulire le risorse normalmente (chiudere il database、ambiente ecc.）
    3. e poi uscire
    """
    def signal_handler(signum, frame):
        global _cleanup_done
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\nricevuto {sig_name} segnale, uscita...")
        
        if not _cleanup_done:
            _cleanup_done = True
            # Imposta un evento per notificare l'uscita del ciclo asincrono (dando al ciclo la possibilità di ripulire le risorse）
            if _shutdown_event:
                _shutdown_event.set()
        
        # Non essere diretto sys.exit()，Lascia che il ciclo asincrono esca senza problemi e pulisca le risorse
        # Se ricevi segnali ripetuti, sarai costretto ad uscire.
        else:
            print("forzare l'uscita...")
            sys.exit(1)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    setup_signal_handlers()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nIl programma viene interrotto")
    except SystemExit:
        pass
    finally:
        # Pulisci il tracker delle risorse multiprocessing (previeni avvisi all'uscita）
        try:
            from multiprocessing import resource_tracker
            resource_tracker._resource_tracker._stop()
        except Exception:
            pass
        print("Il processo di simulazione è terminato")
