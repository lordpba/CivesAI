"""
OASIS TwitterScript preimpostato di simulazione
Questo script legge i parametri nel file di configurazione per eseguire la simulazione e realizzare l'automazione completa.

Caratteristiche:
- Dopo aver completato la simulazione, non chiudere immediatamente l'ambiente ed entrare nella modalità di comando in attesa.
- Supporta la ricezione di comandi di intervista tramite IPC
-Supporta interviste a singolo agente e interviste batch
-Supporta il comando dell'ambiente di spegnimento remoto

Utilizzo:
    python run_twitter_simulation.py --config /path/to/simulation_config.json
    python run_twitter_simulation.py --config /path/to/simulation_config.json --no-wait  # Chiudere immediatamente una volta terminato
"""

import argparse
import asyncio
import json
import logging
import os
import random
import signal
import sys
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

# Variabili globali: utilizzate per l'elaborazione del segnale
_shutdown_event = None
_cleanup_done = False

# Aggiungi il percorso del progetto
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
else:
    _backend_env = os.path.join(_backend_dir, '.env')
    if os.path.exists(_backend_env):
        load_dotenv(_backend_env)


import re


class UnicodeFormatter(logging.Formatter):
    """Formattatore personalizzato che converte le sequenze di escape Unicode in caratteri leggibili"""
    
    UNICODE_ESCAPE_PATTERN = re.compile(r'\\u([0-9a-fA-F]{4})')
    
    def format(self, record):
        result = super().format(record)
        
        def replace_unicode(match):
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return match.group(0)
        
        return self.UNICODE_ESCAPE_PATTERN.sub(replace_unicode, result)


class MaxTokensWarningFilter(logging.Filter):
    """Filtra camel-ai Informazioni max_tokens avviso (non impostiamo intenzionalmente max_tokens，Lasciamo che il modello decida da solo）"""
    
    def filter(self, record):
        # filtrare contiene max_tokens registro degli avvisi
        if "max_tokens" in record.getMessage() and "Invalid or missing" in record.getMessage():
            return False
        return True


# Aggiungi il filtro immediatamente quando il modulo viene caricato per assicurarti che abbia effetto prima che il codice camel venga eseguito
logging.getLogger().addFilter(MaxTokensWarningFilter())


def setup_oasis_logging(log_dir: str):
    """Configura i log di OASIS e utilizza file di log con nomi fissi"""
    os.makedirs(log_dir, exist_ok=True)
    
    # Pulisci i vecchi file di registro
    for f in os.listdir(log_dir):
        old_log = os.path.join(log_dir, f)
        if os.path.isfile(old_log) and f.endswith('.log'):
            try:
                os.remove(old_log)
            except OSError:
                pass
    
    formatter = UnicodeFormatter("%(levelname)s - %(asctime)s - %(name)s - %(message)s")
    
    loggers_config = {
        "social.agent": os.path.join(log_dir, "social.agent.log"),
        "social.twitter": os.path.join(log_dir, "social.twitter.log"),
        "social.rec": os.path.join(log_dir, "social.rec.log"),
        "oasis.env": os.path.join(log_dir, "oasis.env.log"),
        "table": os.path.join(log_dir, "table.log"),
    }
    
    for logger_name, log_file in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.propagate = False


try:
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    import oasis
    from oasis import (
        ActionType,
        LLMAction,
        ManualAction,
        generate_twitter_agent_graph
    )
except ImportError as e:
    print(f"Errore: Dipendenze mancanti {e}")
    print("Si prega di installare prima: pip install oasis-ai camel-ai")
    sys.exit(1)


# IPCCostanti correlate
IPC_COMMANDS_DIR = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE = "env_status.json"

class CommandType:
    """Tipo di comando costante"""
    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"


class IPCHandler:
    """IPCprocessore di comandi"""
    
    def __init__(self, simulation_dir: str, env, agent_graph):
        self.simulation_dir = simulation_dir
        self.env = env
        self.agent_graph = agent_graph
        self.commands_dir = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file = os.path.join(simulation_dir, ENV_STATUS_FILE)
        self._running = True
        
        # Assicurati che la directory esista
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
    
    def update_status(self, status: str):
        """Aggiorna lo stato dell'ambiente"""
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
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
    
    async def handle_interview(self, command_id: str, agent_id: int, prompt: str) -> bool:
        """
        Gestione di un singolo comando di intervista dell'agente
        
        Returns:
            True indica il successo, falso esprimerefallito
        """
        try:
            # OttieniAgent
            agent = self.agent_graph.get_agent(agent_id)
            
            # Crea un'azione Intervista
            interview_action = ManualAction(
                action_type=ActionType.INTERVIEW,
                action_args={"prompt": prompt}
            )
            
            # eseguireInterview
            actions = {agent: interview_action}
            await self.env.step(actions)
            
            # Ottieni risultati dal database
            result = self._get_interview_result(agent_id)
            
            self.send_response(command_id, "completed", result=result)
            print(f"  InterviewCompleto: agent_id={agent_id}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"  Interviewfallito: agent_id={agent_id}, error={error_msg}")
            self.send_response(command_id, "failed", error=error_msg)
            return False
    
    async def handle_batch_interview(self, command_id: str, interviews: List[Dict]) -> bool:
        """
        Elabora comandi di intervista in batch
        
        Args:
            interviews: [{"agent_id": int, "prompt": str}, ...]
        """
        try:
            # Costruisci un dizionario delle azioni
            actions = {}
            agent_prompts = {}  # Registra quello di ciascun agenteprompt
            
            for interview in interviews:
                agent_id = interview.get("agent_id")
                prompt = interview.get("prompt", "")
                
                try:
                    agent = self.agent_graph.get_agent(agent_id)
                    actions[agent] = ManualAction(
                        action_type=ActionType.INTERVIEW,
                        action_args={"prompt": prompt}
                    )
                    agent_prompts[agent_id] = prompt
                except Exception as e:
                    print(f"  avvertimento: Impossibile ottenereAgent {agent_id}: {e}")
            
            if not actions:
                self.send_response(command_id, "failed", error="non validoAgent")
                return False
            
            # Esegui batchInterview
            await self.env.step(actions)
            
            # Ottieni tutti i risultati
            results = {}
            for agent_id in agent_prompts.keys():
                result = self._get_interview_result(agent_id)
                results[agent_id] = result
            
            self.send_response(command_id, "completed", result={
                "interviews_count": len(results),
                "results": results
            })
            print(f"  Interviste batch completate: {len(results)} unAgent")
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"  Le interviste batch sono fallite: {error_msg}")
            self.send_response(command_id, "failed", error=error_msg)
            return False
    
    def _get_interview_result(self, agent_id: int) -> Dict[str, Any]:
        """Ottieni gli ultimi risultati dell'intervista dal database"""
        db_path = os.path.join(self.simulation_dir, "twitter_simulation.db")
        
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
                args.get("prompt", "")
            )
            return True
            
        elif command_type == CommandType.BATCH_INTERVIEW:
            await self.handle_batch_interview(
                command_id,
                args.get("interviews", [])
            )
            return True
            
        elif command_type == CommandType.CLOSE_ENV:
            print("Ricevere un comando di arresto dell'ambiente")
            self.send_response(command_id, "completed", result={"message": "L'ambiente sta per chiudere"})
            return False
        
        else:
            self.send_response(command_id, "failed", error=f"Tipo di comando sconosciuto: {command_type}")
            return True


class TwitterSimulationRunner:
    """TwitterCorridore di simulazione"""
    
    # TwitterLe azioni disponibili (escluso INTERVISTA, INTERVISTA possono essere attivate solo manualmente tramite Azione Manuale）
    AVAILABLE_ACTIONS = [
        ActionType.CREATE_POST,
        ActionType.LIKE_POST,
        ActionType.REPOST,
        ActionType.FOLLOW,
        ActionType.DO_NOTHING,
        ActionType.QUOTE_POST,
    ]
    
    def __init__(self, config_path: str, wait_for_commands: bool = True):
        """
        Inizializza il corridore della simulazione
        
        Args:
            config_path: Percorso del file di configurazione (simulation_config.json)
            wait_for_commands: Se attendere i comandi al termine della simulazione (defaultTrue）
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.simulation_dir = os.path.dirname(config_path)
        self.wait_for_commands = wait_for_commands
        self.env = None
        self.agent_graph = None
        self.ipc_handler = None
        
    def _load_config(self) -> Dict[str, Any]:
        """Carica il file di configurazione"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_profile_path(self) -> str:
        """Ottieni il percorso del file del profilo (OASIS Twitter utilizza il formato CSV）"""
        return os.path.join(self.simulation_dir, "twitter_profiles.csv")
    
    def _get_db_path(self) -> str:
        """Ottieni il percorso del database"""
        return os.path.join(self.simulation_dir, "twitter_simulation.db")
    
    def _create_model(self):
        """
        Crea modello LLM
        
        Utilizzare la directory root del progetto in modo uniforme .env Configuration in file (highest priority）：
        - LLM_API_KEY: APIchiave
        - LLM_BASE_URL: APINozioni di baseURL
        - LLM_MODEL_NAME: Nome del modello
        """
        # Priorità da .env Leggi la configurazione
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        llm_base_url = os.environ.get("LLM_BASE_URL", "")
        llm_model = os.environ.get("LLM_MODEL_NAME", "")
        
        # se .env Se non lo trovi, usa config come fallback
        if not llm_model:
            llm_model = self.config.get("llm_model", "gpt-4o-mini")
        
        # Imposta le variabili di ambiente richieste da camel-ai
        if llm_api_key:
            os.environ["OPENAI_API_KEY"] = llm_api_key
        
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("Manca la configurazione della chiave API, configurala nella directory root del progetto .env Impostato in archivio LLM_API_KEY")
        
        if llm_base_url:
            os.environ["OPENAI_API_BASE_URL"] = llm_base_url
        
        print(f"LLMConfigurazione: model={llm_model}, base_url={llm_base_url[:40] if llm_base_url else 'Predefinito'}...")
        
        return ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=llm_model,
        )
    
    def _get_active_agents_for_round(
        self, 
        env, 
        current_hour: int,
        round_num: int
    ) -> List:
        """
        Decidi quali attivare questo round in base al tempo e alla configurazioneAgent
        
        Args:
            env: OASISambiente
            current_hour: Ora attuale della simulazione（0-23）
            round_num: Numero del round attuale
            
        Returns:
            Elenco agenti attivati
        """
        time_config = self.config.get("time_config", {})
        agent_configs = self.config.get("agent_configs", [])
        
        # Quantità di attivazione di base
        base_min = time_config.get("agents_per_hour_min", 5)
        base_max = time_config.get("agents_per_hour_max", 20)
        
        # Regolare in base al periodo di tempo
        peak_hours = time_config.get("peak_hours", [9, 10, 11, 14, 15, 20, 21, 22])
        off_peak_hours = time_config.get("off_peak_hours", [0, 1, 2, 3, 4, 5])
        
        if current_hour in peak_hours:
            multiplier = time_config.get("peak_activity_multiplier", 1.5)
        elif current_hour in off_peak_hours:
            multiplier = time_config.get("off_peak_activity_multiplier", 0.3)
        else:
            multiplier = 1.0
        
        target_count = int(random.uniform(base_min, base_max) * multiplier)
        
        # Calcola la probabilità di attivazione in base alla configurazione di ciascun agente
        candidates = []
        for cfg in agent_configs:
            agent_id = cfg.get("agent_id", 0)
            active_hours = cfg.get("active_hours", list(range(8, 23)))
            activity_level = cfg.get("activity_level", 0.5)
            
            # Controlla se è l'ora attiva
            if current_hour not in active_hours:
                continue
            
            # Calcolare la probabilità in base all'attività
            if random.random() < activity_level:
                candidates.append(agent_id)
        
        # selezionato casualmente
        selected_ids = random.sample(
            candidates, 
            min(target_count, len(candidates))
        ) if candidates else []
        
        # Converti in oggetto Agente
        active_agents = []
        for agent_id in selected_ids:
            try:
                agent = env.agent_graph.get_agent(agent_id)
                active_agents.append((agent_id, agent))
            except Exception:
                pass
        
        return active_agents
    
    async def run(self, max_rounds: int = None):
        """Esegui una simulazione su Twitter
        
        Args:
            max_rounds: Numero massimo di cicli di simulazione (facoltativo, utilizzato per troncare le simulazioni troppo lunghe）
        """
        print("=" * 60)
        print("OASIS TwitterSimulazione")
        print(f"File di configurazione: {self.config_path}")
        print(f"SimulazioneID: {self.config.get('simulation_id', 'unknown')}")
        print(f"Attendi la modalità comando: {'abilitare' if self.wait_for_commands else 'Disabilita'}")
        print("=" * 60)
        
        # Carica la configurazione del tempo
        time_config = self.config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        
        # Calcola il numero totale di round
        total_rounds = (total_hours * 60) // minutes_per_round
        
        # Tronca se viene specificato il numero massimo di round
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                print(f"\nTurni troncati: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
        
        print(f"\nParametri di simulazione:")
        print(f"  - Tempo totale di simulazione: {total_hours}Ore")
        print(f"  - Tempo per round: {minutes_per_round}Minuti")
        print(f"  - Turni totali: {total_rounds}")
        if max_rounds:
            print(f"  - Limite massimo del numero di round: {max_rounds}")
        print(f"  - AgentQuantità: {len(self.config.get('agent_configs', []))}")
        
        # Crea modello
        print("\nInizializza il modello LLM...")
        model = self._create_model()
        
        # Carica il grafico dell'agente
        print("CaricareAgent Profile...")
        profile_path = self._get_profile_path()
        if not os.path.exists(profile_path):
            print(f"Errore: ProfileIl file non esiste: {profile_path}")
            return
        
        self.agent_graph = await generate_twitter_agent_graph(
            profile_path=profile_path,
            model=model,
            available_actions=self.AVAILABLE_ACTIONS,
        )
        
        # Percorso del database
        db_path = self._get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Vecchio database cancellato: {db_path}")
        
        # Crea ambiente
        print("Crea un ambiente OASIS...")
        self.env = oasis.make(
            agent_graph=self.agent_graph,
            platform=oasis.DefaultPlatformType.TWITTER,
            database_path=db_path,
            semaphore=30,  # Limita il numero massimo di richieste LLM simultanee per evitare il sovraccarico dell'API
        )
        
        await self.env.reset()
        print("Inizializzazione dell'ambiente completata\n")
        
        # Inizializza il gestore IPC
        self.ipc_handler = IPCHandler(self.simulation_dir, self.env, self.agent_graph)
        self.ipc_handler.update_status("running")
        
        # Esegui l'evento iniziale
        event_config = self.config.get("event_config", {})
        initial_posts = event_config.get("initial_posts", [])
        
        if initial_posts:
            print(f"Esegui l'evento iniziale ({len(initial_posts)}post iniziali)...")
            initial_actions = {}
            for post in initial_posts:
                agent_id = post.get("poster_agent_id", 0)
                content = post.get("content", "")
                try:
                    agent = self.env.agent_graph.get_agent(agent_id)
                    initial_actions[agent] = ManualAction(
                        action_type=ActionType.CREATE_POST,
                        action_args={"content": content}
                    )
                except Exception as e:
                    print(f"  avvertimento: incapace diAgent {agent_id}Crea il post iniziale: {e}")
            
            if initial_actions:
                await self.env.step(initial_actions)
                print(f"  Pubblicato {len(initial_actions)} post iniziali")
        
        # ciclo di simulazione principale
        print("\nAvvia il ciclo di simulazione...")
        start_time = datetime.now()
        
        for round_num in range(total_rounds):
            # Calcolare il tempo di simulazione corrente
            simulated_minutes = round_num * minutes_per_round
            simulated_hour = (simulated_minutes // 60) % 24
            simulated_day = simulated_minutes // (60 * 24) + 1
            
            # Attivati in questo roundAgent
            active_agents = self._get_active_agents_for_round(
                self.env, simulated_hour, round_num
            )
            
            if not active_agents:
                continue
            
            # Costruisci azione
            actions = {
                agent: LLMAction()
                for _, agent in active_agents
            }
            
            # eseguire un'azione
            await self.env.step(actions)
            
            # Avanzamento della stampa
            if (round_num + 1) % 10 == 0 or round_num == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = (round_num + 1) / total_rounds * 100
                print(f"  [Day {simulated_day}, {simulated_hour:02d}:00] "
                      f"Round {round_num + 1}/{total_rounds} ({progress:.1f}%) "
                      f"- {len(active_agents)} agents active "
                      f"- elapsed: {elapsed:.1f}s")
        
        total_elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\nCiclo di simulazione completato!")
        print(f"  - Tempo totale impiegato: {total_elapsed:.1f}secondi")
        print(f"  - banca dati: {db_path}")
        
        # Se accedere alla modalità comando in attesa
        if self.wait_for_commands:
            print("\n" + "=" * 60)
            print("Accedi alla modalità di attesa del comando: l'ambiente rimane in esecuzione")
            print("Comandi supportati: interview, batch_interview, close_env")
            print("=" * 60)
            
            self.ipc_handler.update_status("alive")
            
            # Attendi il ciclo di comandi (usando global _shutdown_event）
            try:
                while not _shutdown_event.is_set():
                    should_continue = await self.ipc_handler.process_commands()
                    if not should_continue:
                        break
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=0.5)
                        break  # Segnale di uscita ricevuto
                    except asyncio.TimeoutError:
                        pass
            except KeyboardInterrupt:
                print("\nSegnale di interruzione ricevuto")
            except asyncio.CancelledError:
                print("\nAttività annullata")
            except Exception as e:
                print(f"\nErrore nell'elaborazione del comando: {e}")
            
            print("\nAmbiente chiuso...")
        
        # Ambiente chiuso
        self.ipc_handler.update_status("stopped")
        await self.env.close()
        
        print("L'ambiente è in crisi")
        print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description='OASIS TwitterSimulazione')
    parser.add_argument(
        '--config', 
        type=str, 
        required=True,
        help='Percorso del file di configurazione (simulation_config.json)'
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
    
    # Crea un evento di spegnimento all'inizio della funzione principale
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    
    if not os.path.exists(args.config):
        print(f"Errore: Il file di configurazione non esiste: {args.config}")
        sys.exit(1)
    
    # Inizializza la configurazione del registro (usa un nome file fisso, pulisci i vecchi registri）
    simulation_dir = os.path.dirname(args.config) or "."
    setup_oasis_logging(os.path.join(simulation_dir, "log"))
    
    runner = TwitterSimulationRunner(
        config_path=args.config,
        wait_for_commands=not args.no_wait
    )
    await runner.run(max_rounds=args.max_rounds)


def setup_signal_handlers():
    """
    Configura il gestore del segnale per garantire l'uscita corretta durante la ricezione di SIGTERM/SIGINT
    Dare al programma la possibilità di ripulire le risorse normalmente (chiudere il database、ambiente ecc.）
    """
    def signal_handler(signum, frame):
        global _cleanup_done
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\nricevuto {sig_name} segnale, uscita...")
        if not _cleanup_done:
            _cleanup_done = True
            if _shutdown_event:
                _shutdown_event.set()
        else:
            # Uscita forzata solo dopo aver ricevuto ripetuti segnali
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
        print("Il processo di simulazione è terminato")
