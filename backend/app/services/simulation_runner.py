"""
OASISCorridore di simulazione
Esegui simulazioni in background e registra le azioni di ciascun agente per supportare il monitoraggio dello stato in tempo reale
"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
import signal
import atexit
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue

from ..config import Config
from ..utils.logger import get_logger
from .zep_graph_memory_updater import ZepGraphMemoryManager
from .simulation_ipc import SimulationIPCClient, CommandType, IPCResponse

logger = get_logger('mirofish.simulation_runner')

# Flag whether a cleanup function has been registered
_cleanup_registered = False

# Rilevamento della piattaforma
IS_WINDOWS = sys.platform == 'win32'


class RunnerStatus(str, Enum):
    """Stato di corridore"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentAction:
    """Agentregistro delle azioni"""
    round_num: int
    timestamp: str
    platform: str  # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str  # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class RoundSummary:
    """Riepilogo di ogni round"""
    round_num: int
    start_time: str
    end_time: Optional[str] = None
    simulated_hour: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    active_agents: List[int] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "simulated_hour": self.simulated_hour,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "active_agents": self.active_agents,
            "actions_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class SimulationRunState:
    """Stato di esecuzione della simulazione (in tempo reale）"""
    simulation_id: str
    runner_status: RunnerStatus = RunnerStatus.IDLE
    
    # informazioni sullo stato di avanzamento
    current_round: int = 0
    total_rounds: int = 0
    simulated_hours: int = 0
    total_simulation_hours: int = 0
    
    # Turni e tempi di simulazione indipendenti per ciascuna piattaforma (per la visualizzazione parallela di piattaforme doppie）
    twitter_current_round: int = 0
    reddit_current_round: int = 0
    twitter_simulated_hours: int = 0
    reddit_simulated_hours: int = 0
    
    # Stato della piattaforma
    twitter_running: bool = False
    reddit_running: bool = False
    twitter_actions_count: int = 0
    reddit_actions_count: int = 0
    
    # Stato di completamento della piattaforma (rilevamento superato actions.jsonl dentro simulation_end evento）
    twitter_completed: bool = False
    reddit_completed: bool = False
    
    # Riepilogo di ogni round
    rounds: List[RoundSummary] = field(default_factory=list)
    
    # Azioni recenti (per la visualizzazione in tempo reale front-end）
    recent_actions: List[AgentAction] = field(default_factory=list)
    max_recent_actions: int = 50
    
    # Timestamp
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    # messaggio di errore
    error: Optional[str] = None
    
    # ID processo (utilizzato per interrompere）
    process_pid: Optional[int] = None
    
    def add_action(self, action: AgentAction):
        """Aggiungi un'azione all'elenco delle azioni recenti"""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[:self.max_recent_actions]
        
        if action.platform == "twitter":
            self.twitter_actions_count += 1
        else:
            self.reddit_actions_count += 1
        
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "runner_status": self.runner_status.value,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "simulated_hours": self.simulated_hours,
            "total_simulation_hours": self.total_simulation_hours,
            "progress_percent": round(self.current_round / max(self.total_rounds, 1) * 100, 1),
            # Giri e orari indipendenti per ciascuna piattaforma
            "twitter_current_round": self.twitter_current_round,
            "reddit_current_round": self.reddit_current_round,
            "twitter_simulated_hours": self.twitter_simulated_hours,
            "reddit_simulated_hours": self.reddit_simulated_hours,
            "twitter_running": self.twitter_running,
            "reddit_running": self.reddit_running,
            "twitter_completed": self.twitter_completed,
            "reddit_completed": self.reddit_completed,
            "twitter_actions_count": self.twitter_actions_count,
            "reddit_actions_count": self.reddit_actions_count,
            "total_actions_count": self.twitter_actions_count + self.reddit_actions_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "process_pid": self.process_pid,
        }
    
    def to_detail_dict(self) -> Dict[str, Any]:
        """Contiene i dettagli delle azioni recenti"""
        result = self.to_dict()
        result["recent_actions"] = [a.to_dict() for a in self.recent_actions]
        result["rounds_count"] = len(self.rounds)
        return result


class SimulationRunner:
    """
    Corridore di simulazione
    
    responsabile：
    1. Esegui la simulazione OASIS nel processo in background
    2. Analizza il registro in esecuzione e registra le azioni di ciascun agente
    3. Fornire un'interfaccia per le query sullo stato in tempo reale
    4. Supporta le operazioni di pausa/arresto/ripresa
    """
    
    # Directory di archiviazione dello stato in esecuzione
    RUN_STATE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )
    
    # directory degli script
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../scripts'
    )
    
    # Stato di esecuzione in memoria
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}  # Memorizza l'handle del file stdout
    _stderr_files: Dict[str, Any] = {}  # Memorizza l'handle del file stderr
    
    # Configurazione dell'aggiornamento della memoria della mappa
    _graph_memory_enabled: Dict[str, bool] = {}  # simulation_id -> enabled
    
    @classmethod
    def get_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Ottieni lo stato di esecuzione"""
        if simulation_id in cls._run_states:
            return cls._run_states[simulation_id]
        
        # Prova a caricare da file
        state = cls._load_run_state(simulation_id)
        if state:
            cls._run_states[simulation_id] = state
        return state
    
    @classmethod
    def _load_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Carica lo stato di esecuzione dal file"""
        state_file = os.path.join(cls.RUN_STATE_DIR, simulation_id, "run_state.json")
        if not os.path.exists(state_file):
            return None
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            state = SimulationRunState(
                simulation_id=simulation_id,
                runner_status=RunnerStatus(data.get("runner_status", "idle")),
                current_round=data.get("current_round", 0),
                total_rounds=data.get("total_rounds", 0),
                simulated_hours=data.get("simulated_hours", 0),
                total_simulation_hours=data.get("total_simulation_hours", 0),
                # Giri e orari indipendenti per ciascuna piattaforma
                twitter_current_round=data.get("twitter_current_round", 0),
                reddit_current_round=data.get("reddit_current_round", 0),
                twitter_simulated_hours=data.get("twitter_simulated_hours", 0),
                reddit_simulated_hours=data.get("reddit_simulated_hours", 0),
                twitter_running=data.get("twitter_running", False),
                reddit_running=data.get("reddit_running", False),
                twitter_completed=data.get("twitter_completed", False),
                reddit_completed=data.get("reddit_completed", False),
                twitter_actions_count=data.get("twitter_actions_count", 0),
                reddit_actions_count=data.get("reddit_actions_count", 0),
                started_at=data.get("started_at"),
                updated_at=data.get("updated_at", datetime.now().isoformat()),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
                process_pid=data.get("process_pid"),
            )
            
            # Carica azioni recenti
            actions_data = data.get("recent_actions", [])
            for a in actions_data:
                state.recent_actions.append(AgentAction(
                    round_num=a.get("round_num", 0),
                    timestamp=a.get("timestamp", ""),
                    platform=a.get("platform", ""),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a.get("action_type", ""),
                    action_args=a.get("action_args", {}),
                    result=a.get("result"),
                    success=a.get("success", True),
                ))
            
            return state
        except Exception as e:
            logger.error(f"Impossibile caricare lo stato di esecuzione: {str(e)}")
            return None
    
    @classmethod
    def _save_run_state(cls, state: SimulationRunState):
        """Salva lo stato di esecuzione su file"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        state_file = os.path.join(sim_dir, "run_state.json")
        
        data = state.to_detail_dict()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        cls._run_states[state.simulation_id] = state
    
    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int = None,  # Numero massimo di cicli di simulazione (facoltativo, utilizzato per troncare le simulazioni troppo lunghe）
        enable_graph_memory_update: bool = False,  # Se aggiornare l'attività sulla mappa Zep
        graph_id: str = None  # ZepID mappa (richiesto quando gli aggiornamenti delle mappe sono abilitati)）
    ) -> SimulationRunState:
        """
        Avvia la simulazione
        
        Args:
            simulation_id: SimulazioneID
            platform: Piattaforma da corsa (twitter/reddit/parallel)
            max_rounds: Numero massimo di cicli di simulazione (facoltativo, utilizzato per troncare le simulazioni troppo lunghe）
            enable_graph_memory_update: Se aggiornare dinamicamente le attività dell'agente sulla mappa Zep
            graph_id: ZepID mappa (richiesto quando gli aggiornamenti delle mappe sono abilitati)）
            
        Returns:
            SimulationRunState
        """
        # Controlla se è già in esecuzione
        existing = cls.get_run_state(simulation_id)
        if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
            raise ValueError(f"La simulazione è già in corso: {simulation_id}")
        
        # Carica la configurazione della simulazione
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            raise ValueError(f"La configurazione della simulazione non esiste, richiama prima l'interfaccia /prepare")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Inizializza lo stato di esecuzione
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)
        
        # Tronca se viene specificato il numero massimo di round
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(f"Turni troncati: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
        
        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )
        
        cls._save_run_state(state)
        
        # Se l'aggiornamento della memoria della mappa è abilitato, crea un programma di aggiornamento
        if enable_graph_memory_update:
            if not graph_id:
                raise ValueError("Necessario quando si abilita l'aggiornamento della memoria della mappa graph_id")
            
            try:
                ZepGraphMemoryManager.create_updater(simulation_id, graph_id)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(f"Aggiornamento della memoria della mappa abilitato: simulation_id={simulation_id}, graph_id={graph_id}")
            except Exception as e:
                logger.error(f"Impossibile creare l'aggiornamento della memoria della mappa: {e}")
                cls._graph_memory_enabled[simulation_id] = False
        else:
            cls._graph_memory_enabled[simulation_id] = False
        
        # Determina quale script eseguire (lo script si trova nella directory backend/scripts/）
        if platform == "twitter":
            script_name = "run_twitter_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_reddit_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True
        
        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)
        
        if not os.path.exists(script_path):
            raise ValueError(f"La sceneggiatura non esiste: {script_path}")
        
        # Crea coda di azioni
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue
        
        # Avvia il processo di simulazione
        try:
            # Crea comando di esecuzione, utilizza il percorso completo
            # Nuova struttura del registro：
            #   twitter/actions.jsonl - Twitter registro delle azioni
            #   reddit/actions.jsonl  - Reddit registro delle azioni
            #   simulation.log        - Registro del processo principale
            
            cmd = [
                sys.executable,  # Pythoninterprete
                script_path,
                "--config", config_path,  # Utilizza il percorso completo del file di configurazione
            ]
            
            # Se viene specificato il numero massimo di cicli, aggiungere agli argomenti della riga di comando
            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])
            
            # Creare un file di registro principale per evitare il blocco del processo a causa dei buffer pipe stdout/stderr pieni
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, 'w', encoding='utf-8')
            
            # Imposta le variabili di ambiente del sottoprocesso per garantire che su Windows venga utilizzata la codifica UTF-8
            # Ciò risolve un problema per cui le librerie di terze parti (come OASIS) leggono file senza specificare la codifica
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'  # Python 3.7+ supporto, lasciamo tutti open() Utilizzato per impostazione predefinita UTF-8
            env['PYTHONIOENCODING'] = 'utf-8'  # Assicurati che sia utilizzato stdout/stderr UTF-8
            
            # Imposta la directory di lavoro sulla directory di simulazione (il database e altri file verranno generati qui）
            # Utilizzare start_new_session=True Crea un nuovo gruppo di processi e assicurati che possa passare os.killpg Uccidi tutti i processi figli
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,  # stderr Scrivi anche nello stesso file
                text=True,
                encoding='utf-8',  # Specificare esplicitamente la codifica
                bufsize=1,
                env=env,  # Passa variabili di ambiente con impostazioni UTF-8
                start_new_session=True,  # Creare un nuovo gruppo di processi per garantire che tutti i processi correlati vengano terminati quando il server viene arrestato
            )
            
            # Salva l'handle del file per una chiusura successiva
            cls._stdout_files[simulation_id] = main_log_file
            cls._stderr_files[simulation_id] = None  # Non più separati stderr
            
            state.process_pid = process.pid
            state.runner_status = RunnerStatus.RUNNING
            cls._processes[simulation_id] = process
            cls._save_run_state(state)
            
            # Inizia a monitorare il thread
            monitor_thread = threading.Thread(
                target=cls._monitor_simulation,
                args=(simulation_id,),
                daemon=True
            )
            monitor_thread.start()
            cls._monitor_threads[simulation_id] = monitor_thread
            
            logger.info(f"La simulazione è iniziata con successo: {simulation_id}, pid={process.pid}, platform={platform}")
            
        except Exception as e:
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
            raise
        
        return state
    
    @classmethod
    def _monitor_simulation(cls, simulation_id: str):
        """Monitorare il processo di simulazione e analizzare i registri delle azioni"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        # Nuova struttura del registro: registri delle azioni per diverse piattaforme
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        process = cls._processes.get(simulation_id)
        state = cls.get_run_state(simulation_id)
        
        if not process or not state:
            return
        
        twitter_position = 0
        reddit_position = 0
        
        try:
            while process.poll() is None:  # Il processo è ancora in corso
                # Leggi il registro delle azioni di Twitter
                if os.path.exists(twitter_actions_log):
                    twitter_position = cls._read_action_log(
                        twitter_actions_log, twitter_position, state, "twitter"
                    )
                
                # Leggi il registro delle azioni di Reddit
                if os.path.exists(reddit_actions_log):
                    reddit_position = cls._read_action_log(
                        reddit_actions_log, reddit_position, state, "reddit"
                    )
                
                # stato dell'aggiornamento
                cls._save_run_state(state)
                time.sleep(2)
            
            # Al termine del processo, leggere il registro per l'ultima volta
            if os.path.exists(twitter_actions_log):
                cls._read_action_log(twitter_actions_log, twitter_position, state, "twitter")
            if os.path.exists(reddit_actions_log):
                cls._read_action_log(reddit_actions_log, reddit_position, state, "reddit")
            
            # Il processo termina
            exit_code = process.returncode
            
            if exit_code == 0:
                state.runner_status = RunnerStatus.COMPLETED
                state.completed_at = datetime.now().isoformat()
                logger.info(f"Simulazione completata: {simulation_id}")
            else:
                state.runner_status = RunnerStatus.FAILED
                # Leggere i messaggi di errore dal file di registro principale
                main_log_path = os.path.join(sim_dir, "simulation.log")
                error_info = ""
                try:
                    if os.path.exists(main_log_path):
                        with open(main_log_path, 'r', encoding='utf-8') as f:
                            error_info = f.read()[-2000:]  # Prendi gli ultimi 2000 caratteri
                except Exception:
                    pass
                state.error = f"codice di uscita del processo: {exit_code}, Errore: {error_info}"
                logger.error(f"La simulazione è fallita: {simulation_id}, error={state.error}")
            
            state.twitter_running = False
            state.reddit_running = False
            cls._save_run_state(state)
            
        except Exception as e:
            logger.error(f"Monitorare le eccezioni del thread: {simulation_id}, error={str(e)}")
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
        
        finally:
            # Arresta l'aggiornamento della memoria della mappa
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    ZepGraphMemoryManager.stop_updater(simulation_id)
                    logger.info(f"Aggiornamento della memoria della mappa interrotto: simulation_id={simulation_id}")
                except Exception as e:
                    logger.error(f"Impossibile arrestare l'aggiornamento della memoria della mappa: {e}")
                cls._graph_memory_enabled.pop(simulation_id, None)
            
            # Ripulire le risorse del processo
            cls._processes.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)
            
            # Chiudi l'handle del file di registro
            if simulation_id in cls._stdout_files:
                try:
                    cls._stdout_files[simulation_id].close()
                except Exception:
                    pass
                cls._stdout_files.pop(simulation_id, None)
            if simulation_id in cls._stderr_files and cls._stderr_files[simulation_id]:
                try:
                    cls._stderr_files[simulation_id].close()
                except Exception:
                    pass
                cls._stderr_files.pop(simulation_id, None)
    
    @classmethod
    def _read_action_log(
        cls, 
        log_path: str, 
        position: int, 
        state: SimulationRunState,
        platform: str
    ) -> int:
        """
        Leggere il file di registro delle azioni
        
        Args:
            log_path: Percorso del file di registro
            position: Posizione dell'ultima lettura
            state: oggetto stato in esecuzione
            platform: Nome della piattaforma (twitter/reddit)
            
        Returns:
            nuova posizione di lettura
        """
        # Controlla se l'aggiornamento della memoria della mappa è abilitato
        graph_memory_enabled = cls._graph_memory_enabled.get(state.simulation_id, False)
        graph_updater = None
        if graph_memory_enabled:
            graph_updater = ZepGraphMemoryManager.get_updater(state.simulation_id)
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                f.seek(position)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            action_data = json.loads(line)
                            
                            # Gestisce le voci del tipo di evento
                            if "event_type" in action_data:
                                event_type = action_data.get("event_type")
                                
                                # Rilevamento simulation_end evento, contrassegnando la piattaforma come completata
                                if event_type == "simulation_end":
                                    if platform == "twitter":
                                        state.twitter_completed = True
                                        state.twitter_running = False
                                        logger.info(f"Twitter Simulazione completata: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")
                                    elif platform == "reddit":
                                        state.reddit_completed = True
                                        state.reddit_running = False
                                        logger.info(f"Reddit Simulazione completata: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")
                                    
                                    # Controlla se tutte le piattaforme abilitate sono state completate
                                    # Se è in esecuzione solo una piattaforma, controlla solo quella piattaforma
                                    # Se utilizzi due piattaforme, devi completarle entrambe
                                    all_completed = cls._check_all_platforms_completed(state)
                                    if all_completed:
                                        state.runner_status = RunnerStatus.COMPLETED
                                        state.completed_at = datetime.now().isoformat()
                                        logger.info(f"Tutte le simulazioni della piattaforma sono state completate: {state.simulation_id}")
                                
                                # Aggiorna le informazioni sul round (da round_end evento）
                                elif event_type == "round_end":
                                    round_num = action_data.get("round", 0)
                                    simulated_hours = action_data.get("simulated_hours", 0)
                                    
                                    # Aggiorna turni e orari indipendenti per ciascuna piattaforma
                                    if platform == "twitter":
                                        if round_num > state.twitter_current_round:
                                            state.twitter_current_round = round_num
                                        state.twitter_simulated_hours = simulated_hours
                                    elif platform == "reddit":
                                        if round_num > state.reddit_current_round:
                                            state.reddit_current_round = round_num
                                        state.reddit_simulated_hours = simulated_hours
                                    
                                    # Il round complessivo prende il valore massimo delle due piattaforme
                                    if round_num > state.current_round:
                                        state.current_round = round_num
                                    # Il tempo complessivo è il massimo delle due piattaforme
                                    state.simulated_hours = max(state.twitter_simulated_hours, state.reddit_simulated_hours)
                                
                                continue
                            
                            action = AgentAction(
                                round_num=action_data.get("round", 0),
                                timestamp=action_data.get("timestamp", datetime.now().isoformat()),
                                platform=platform,
                                agent_id=action_data.get("agent_id", 0),
                                agent_name=action_data.get("agent_name", ""),
                                action_type=action_data.get("action_type", ""),
                                action_args=action_data.get("action_args", {}),
                                result=action_data.get("result"),
                                success=action_data.get("success", True),
                            )
                            state.add_action(action)
                            
                            # Aggiorna i turni
                            if action.round_num and action.round_num > state.current_round:
                                state.current_round = action.round_num
                            
                            # Se gli aggiornamenti della memoria della mappa sono abilitati, invia attività aZep
                            if graph_updater:
                                graph_updater.add_activity_from_dict(action_data, platform)
                            
                        except json.JSONDecodeError:
                            pass
                return f.tell()
        except Exception as e:
            logger.warning(f"Impossibile leggere il registro delle azioni: {log_path}, error={e}")
            return position
    
    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """
        Verifica che tutte le piattaforme abilitate abbiano completato la simulazione
        
        Controllando il corrispondente actions.jsonl Se il file esiste per determinare se la piattaforma è abilitata
        
        Returns:
            True Se tutte le piattaforme abilitate sono state completate
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        twitter_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        # Controlla quali piattaforme sono abilitate (determinate dall'esistenza del file）
        twitter_enabled = os.path.exists(twitter_log)
        reddit_enabled = os.path.exists(reddit_log)
        
        # Restituisce se la piattaforma è abilitata ma non completata False
        if twitter_enabled and not state.twitter_completed:
            return False
        if reddit_enabled and not state.reddit_completed:
            return False
        
        # Almeno una piattaforma è abilitata e completata
        return twitter_enabled or reddit_enabled
    
    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 10):
        """
        Terminazione multipiattaforma dei processi e dei relativi sottoprocessi
        
        Args:
            process: processo da terminare
            simulation_id: ID di rappresentazione (utilizzato per la registrazione）
            timeout: Timeout di attesa per l'uscita del processo (secondi）
        """
        if IS_WINDOWS:
            # Windows: Termina l'albero dei processi utilizzando il comando taskkill
            # /F = Terminazione forzata, /T = Termina l'albero dei processi (compresi i processi figli）
            logger.info(f"Termina l'albero dei processi (Windows): simulation={simulation_id}, pid={process.pid}")
            try:
                # Prova prima a terminare con garbo
                subprocess.run(
                    ['taskkill', '/PID', str(process.pid), '/T'],
                    capture_output=True,
                    timeout=5
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Terminazione forzata
                    logger.warning(f"Il processo non risponde ed è costretto a terminare.: {simulation_id}")
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(process.pid), '/T'],
                        capture_output=True,
                        timeout=5
                    )
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"taskkill fallire, provare terminate: {e}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        else:
            # Unix: Terminare utilizzando il gruppo di processi
            # a causa dell'utilizzo start_new_session=True，L'ID del gruppo di processi è uguale al processo principale PID
            pgid = os.getpgid(process.pid)
            logger.info(f"Termina il gruppo di processi (Unix): simulation={simulation_id}, pgid={pgid}")
            
            # Invia prima SIGTERM all'intero gruppo di processi
            os.killpg(pgid, signal.SIGTERM)
            
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Se non termina dopo il timeout, forzare l'invio SIGKILL
                logger.warning(f"Il gruppo di processi non ha risposto a SIGTERM ed è stato costretto a terminare.: {simulation_id}")
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)
    
    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """Interrompi la simulazione"""
        state = cls.get_run_state(simulation_id)
        if not state:
            raise ValueError(f"La simulazione non esiste: {simulation_id}")
        
        if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
            raise ValueError(f"La simulazione non è in esecuzione: {simulation_id}, status={state.runner_status}")
        
        state.runner_status = RunnerStatus.STOPPING
        cls._save_run_state(state)
        
        # Terminare il processo
        process = cls._processes.get(simulation_id)
        if process and process.poll() is None:
            try:
                cls._terminate_process(process, simulation_id)
            except ProcessLookupError:
                # Il processo non esiste più
                pass
            except Exception as e:
                logger.error(f"Impossibile terminare il gruppo di processi: {simulation_id}, error={e}")
                # Fallback per terminare direttamente il processo
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
        
        state.runner_status = RunnerStatus.STOPPED
        state.twitter_running = False
        state.reddit_running = False
        state.completed_at = datetime.now().isoformat()
        cls._save_run_state(state)
        
        # Arresta l'aggiornamento della memoria della mappa
        if cls._graph_memory_enabled.get(simulation_id, False):
            try:
                ZepGraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"Aggiornamento della memoria della mappa interrotto: simulation_id={simulation_id}")
            except Exception as e:
                logger.error(f"Impossibile arrestare l'aggiornamento della memoria della mappa: {e}")
            cls._graph_memory_enabled.pop(simulation_id, None)
        
        logger.info(f"La simulazione è stata interrotta: {simulation_id}")
        return state
    
    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Leggere le azioni da un singolo file di azioni
        
        Args:
            file_path: Percorso del file di registro delle azioni
            default_platform: Piattaforma predefinita (utilizzata quando non è presente alcun campo piattaforma nel record dell'azione）
            platform_filter: piattaforma di filtraggio
            agent_id: filtro Agent ID
            round_num: giri di filtro
        """
        if not os.path.exists(file_path):
            return []
        
        actions = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # Salta i record non legati ad azioni (come simulation_start, round_start, round_end eventi ecc）
                    if "event_type" in data:
                        continue
                    
                    # salta n agent_id record (azioni non dell'agente）
                    if "agent_id" not in data:
                        continue
                    
                    # Ottieni la piattaforma: dai la priorità alla piattaforma nel record, altrimenti utilizza la piattaforma predefinita
                    record_platform = data.get("platform") or default_platform or ""
                    
                    # filtro
                    if platform_filter and record_platform != platform_filter:
                        continue
                    if agent_id is not None and data.get("agent_id") != agent_id:
                        continue
                    if round_num is not None and data.get("round") != round_num:
                        continue
                    
                    actions.append(AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    ))
                    
                except json.JSONDecodeError:
                    continue
        
        return actions
    
    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Ottieni la cronologia completa delle azioni per tutte le piattaforme (nessuna limitazione di paginazione)）
        
        Args:
            simulation_id: SimulazioneID
            platform: piattaforma di filtraggio（twitter/reddit）
            agent_id: filtroAgent
            round_num: giri di filtro
            
        Returns:
            Elenco completo delle azioni (ordinate per timestamp, prima la più recente)）
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        actions = []
        
        # Leggi il file di azione di Twitter (imposta automaticamente la piattaforma su twitter）
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        if not platform or platform == "twitter":
            actions.extend(cls._read_actions_from_file(
                twitter_actions_log,
                default_platform="twitter",  # Campo della piattaforma di compilazione automatica
                platform_filter=platform,
                agent_id=agent_id, 
                round_num=round_num
            ))
        
        # Leggi il file di azione di Reddit (imposta automaticamente la piattaforma su reddit）
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        if not platform or platform == "reddit":
            actions.extend(cls._read_actions_from_file(
                reddit_actions_log,
                default_platform="reddit",  # Campo della piattaforma di compilazione automatica
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))
        
        # Se il file della sottopiattaforma non esiste, prova a leggere il vecchio formato di file singolo
        if not actions:
            actions_log = os.path.join(sim_dir, "actions.jsonl")
            actions = cls._read_actions_from_file(
                actions_log,
                default_platform=None,  # Dovrebbe esserci un campo piattaforma nel vecchio file di formato
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            )
        
        # Ordina per timestamp (prima il più recente)）
        actions.sort(key=lambda x: x.timestamp, reverse=True)
        
        return actions
    
    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Ottieni la cronologia delle azioni (con impaginazione)）
        
        Args:
            simulation_id: SimulazioneID
            limit: Limite quantità reso
            offset: compensare
            platform: piattaforma di filtraggio
            agent_id: filtroAgent
            round_num: giri di filtro
            
        Returns:
            elenco delle azioni
        """
        actions = cls.get_all_actions(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        # Impaginazione
        return actions[offset:offset + limit]
    
    @classmethod
    def get_timeline(
        cls,
        simulation_id: str,
        start_round: int = 0,
        end_round: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Ottieni la sequenza temporale della simulazione (riepilogata per round）
        
        Args:
            simulation_id: SimulazioneID
            start_round: giro iniziale
            end_round: fine giro
            
        Returns:
            Informazioni riassuntive per ogni round
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        # Gruppo per turno
        rounds: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            round_num = action.round_num
            
            if round_num < start_round:
                continue
            if end_round is not None and round_num > end_round:
                continue
            
            if round_num not in rounds:
                rounds[round_num] = {
                    "round_num": round_num,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "active_agents": set(),
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            r = rounds[round_num]
            
            if action.platform == "twitter":
                r["twitter_actions"] += 1
            else:
                r["reddit_actions"] += 1
            
            r["active_agents"].add(action.agent_id)
            r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
            r["last_action_time"] = action.timestamp
        
        # Converti in elenco
        result = []
        for round_num in sorted(rounds.keys()):
            r = rounds[round_num]
            result.append({
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            })
        
        return result
    
    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Ottieni statistiche per ciascun agente
        
        Returns:
            AgentElenco statistiche
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        agent_stats: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            agent_id = action.agent_id
            
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    "agent_name": action.agent_name,
                    "total_actions": 0,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            stats = agent_stats[agent_id]
            stats["total_actions"] += 1
            
            if action.platform == "twitter":
                stats["twitter_actions"] += 1
            else:
                stats["reddit_actions"] += 1
            
            stats["action_types"][action.action_type] = stats["action_types"].get(action.action_type, 0) + 1
            stats["last_action_time"] = action.timestamp
        
        # Ordina per numero totale di azioni
        result = sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)
        
        return result
    
    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Pulisci il registro di esecuzione della simulazione (utilizzato per forzare il riavvio della simulazione)
        
        I seguenti file verranno eliminati：
        - run_state.json
        - twitter/actions.jsonl
        - reddit/actions.jsonl
        - simulation.log
        - stdout.log / stderr.log
        - twitter_simulation.db（banca dati fittizia）
        - reddit_simulation.db（banca dati fittizia）
        - env_status.json（stato ambientale)
        
        Nota: i file di configurazione non verranno eliminati（simulation_config.json）e file di profilo
        
        Args:
            simulation_id: SimulazioneID
            
        Returns:
            Informazioni sui risultati pulite
        """
        import shutil
        
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return {"success": True, "message": "La directory di simulazione non esiste e non necessita di essere pulita"}
        
        cleaned_files = []
        errors = []
        
        # Elenco dei file da eliminare (compresi i file di database）
        files_to_delete = [
            "run_state.json",
            "simulation.log",
            "stdout.log",
            "stderr.log",
            "twitter_simulation.db",  # Twitter Banca dati della piattaforma
            "reddit_simulation.db",   # Reddit Banca dati della piattaforma
            "env_status.json",        # file di stato dell'ambiente
        ]
        
        # Elenco delle directory da eliminare (inclusi i registri delle azioni）
        dirs_to_clean = ["twitter", "reddit"]
        
        # Elimina file
        for filename in files_to_delete:
            file_path = os.path.join(sim_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_files.append(filename)
                except Exception as e:
                    errors.append(f"Elimina {filename} fallito: {str(e)}")
        
        # Pulisci i log delle azioni nella directory della piattaforma
        for dir_name in dirs_to_clean:
            dir_path = os.path.join(sim_dir, dir_name)
            if os.path.exists(dir_path):
                actions_file = os.path.join(dir_path, "actions.jsonl")
                if os.path.exists(actions_file):
                    try:
                        os.remove(actions_file)
                        cleaned_files.append(f"{dir_name}/actions.jsonl")
                    except Exception as e:
                        errors.append(f"Elimina {dir_name}/actions.jsonl fallito: {str(e)}")
        
        # Pulisci lo stato di esecuzione in memoria
        if simulation_id in cls._run_states:
            del cls._run_states[simulation_id]
        
        logger.info(f"Registro della simulazione di pulizia completato: {simulation_id}, Elimina file: {cleaned_files}")
        
        return {
            "success": len(errors) == 0,
            "cleaned_files": cleaned_files,
            "errors": errors if errors else None
        }
    
    # Segnale per evitare pulizie ripetute
    _cleanup_done = False
    
    @classmethod
    def cleanup_all_simulations(cls):
        """
        Pulisci tutti i processi di simulazione in esecuzione
        
        Chiamato quando il server viene spento, garantendo che tutti i processi figlio vengano terminati
        """
        # Prevenire la pulizia ripetuta
        if cls._cleanup_done:
            return
        cls._cleanup_done = True
        
        # Controlla se ci sono contenuti che devono essere ripuliti (per evitare che processi vuoti stampino log inutili)）
        has_processes = bool(cls._processes)
        has_updaters = bool(cls._graph_memory_enabled)
        
        if not has_processes and not has_updaters:
            return  # Non c'è niente da pulire, torna in silenzio
        
        logger.info("Ripulire tutti i processi di simulazione...")
        
        # Per prima cosa, interrompi tutti gli aggiornamenti della memoria della mappa（stop_all I registri verranno stampati internamente）
        try:
            ZepGraphMemoryManager.stop_all()
        except Exception as e:
            logger.error(f"Impossibile arrestare l'aggiornamento della memoria della mappa: {e}")
        cls._graph_memory_enabled.clear()
        
        # Copia il dizionario per evitare modifiche durante l'iterazione
        processes = list(cls._processes.items())
        
        for simulation_id, process in processes:
            try:
                if process.poll() is None:  # Il processo è ancora in corso
                    logger.info(f"Terminare il processo di simulazione: {simulation_id}, pid={process.pid}")
                    
                    try:
                        # Utilizzare metodi di terminazione del processo multipiattaforma
                        cls._terminate_process(process, simulation_id, timeout=5)
                    except (ProcessLookupError, OSError):
                        # Il processo potrebbe non esistere più, prova a terminarlo direttamente
                        try:
                            process.terminate()
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()
                    
                    # aggiornamento run_state.json
                    state = cls.get_run_state(simulation_id)
                    if state:
                        state.runner_status = RunnerStatus.STOPPED
                        state.twitter_running = False
                        state.reddit_running = False
                        state.completed_at = datetime.now().isoformat()
                        state.error = "Il server viene spento e la simulazione termina"
                        cls._save_run_state(state)
                    
                    # Aggiorna simultaneamente state.json，Imposta lo stato su stopped
                    try:
                        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
                        state_file = os.path.join(sim_dir, "state.json")
                        logger.info(f"prova ad aggiornare state.json: {state_file}")
                        if os.path.exists(state_file):
                            with open(state_file, 'r', encoding='utf-8') as f:
                                state_data = json.load(f)
                            state_data['status'] = 'stopped'
                            state_data['updated_at'] = datetime.now().isoformat()
                            with open(state_file, 'w', encoding='utf-8') as f:
                                json.dump(state_data, f, indent=2, ensure_ascii=False)
                            logger.info(f"aggiornato state.json Lo stato è stopped: {simulation_id}")
                        else:
                            logger.warning(f"state.json non esiste: {state_file}")
                    except Exception as state_err:
                        logger.warning(f"aggiornamento state.json fallito: {simulation_id}, error={state_err}")
                        
            except Exception as e:
                logger.error(f"Il processo di pulizia non è riuscito: {simulation_id}, error={e}")
        
        # Pulisci l'handle del file
        for simulation_id, file_handle in list(cls._stdout_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stdout_files.clear()
        
        for simulation_id, file_handle in list(cls._stderr_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stderr_files.clear()
        
        # Pulisci lo stato in memoria
        cls._processes.clear()
        cls._action_queues.clear()
        
        logger.info("Pulizia del processo di simulazione completata")
    
    @classmethod
    def register_cleanup(cls):
        """
        Registra la funzione di pulizia
        
        Chiamato all'avvio dell'applicazione Flask per garantire che tutti i processi di simulazione vengano puliti quando il server viene spento
        """
        global _cleanup_registered
        
        if _cleanup_registered:
            return
        
        # Flask debug modalità, registra solo la pulizia nel processo figlio del reloader (il processo che esegue effettivamente l'applicazione）
        # WERKZEUG_RUN_MAIN=true Rappresenta un processo figlio del ricaricatore
        # Se non è in modalità debug, non esiste una variabile di ambiente di questo tipo e deve essere registrata.
        is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('WERKZEUG_RUN_MAIN') is not None
        
        # In modalità debug, registrato solo nel processo figlio del reloader；Sempre registrato in modalità non debug
        if is_debug_mode and not is_reloader_process:
            _cleanup_registered = True  # Il flag è registrato, impedendo al processo figlio di riprovare
            return
        
        # Salva il gestore del segnale originale
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        # SIGHUP Esiste solo su sistemi Unix (macOS/Linux), non su Windows
        original_sighup = None
        has_sighup = hasattr(signal, 'SIGHUP')
        if has_sighup:
            original_sighup = signal.getsignal(signal.SIGHUP)
        
        def cleanup_handler(signum=None, frame=None):
            """Processore di segnale: ripulisci prima il processo di simulazione, quindi richiama il processore originale"""
            # Stampa i registri solo quando sono presenti processi che devono essere ripuliti
            if cls._processes or cls._graph_memory_enabled:
                logger.info(f"segnale ricevuto {signum}，Inizia a pulire...")
            cls.cleanup_all_simulations()
            
            # Chiama il gestore del segnale originale per consentire a Flask di uscire normalmente
            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif has_sighup and signum == signal.SIGHUP:
                # SIGHUP: Inviato quando il terminale è chiuso
                if callable(original_sighup):
                    original_sighup(signum, frame)
                else:
                    # Default behavior: exit normally
                    sys.exit(0)
            else:
                # Se il processore originale non è richiamabile (ad es. SIG_DFL），quindi utilizzare il comportamento predefinito
                raise KeyboardInterrupt
        
        # Registra il gestore atexit (come fallback）
        atexit.register(cls.cleanup_all_simulations)
        
        # Registra il gestore del segnale (solo nel thread principale）
        try:
            # SIGTERM: kill Segnale predefinito del comando
            signal.signal(signal.SIGTERM, cleanup_handler)
            # SIGINT: Ctrl+C
            signal.signal(signal.SIGINT, cleanup_handler)
            # SIGHUP: Il terminale si chiude (solo sistemi Unix）
            if has_sighup:
                signal.signal(signal.SIGHUP, cleanup_handler)
        except ValueError:
            # Non nel thread principale, puoi solo usare atexit
            logger.warning("Impossibile registrare il gestore del segnale (non sul thread principale), basta usarlo atexit")
        
        _cleanup_registered = True
    
    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """
        Ottieni un elenco di tutti gli ID di simulazione in esecuzione
        """
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running
    
    # ============== Interview Funzione ==============
    
    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        Controlla se l'ambiente di simulazione è attivo (può ricevere il comando Intervista）

        Args:
            simulation_id: SimulazioneID

        Returns:
            True Indica che l'ambiente è attivo, False indica che l'ambiente è spento
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return False

        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Ottieni informazioni dettagliate sullo stato dell'ambiente di simulazione

        Args:
            simulation_id: SimulazioneID

        Returns:
            Dizionario dei dettagli sullo stato, incluso status, twitter_available, reddit_available, timestamp
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        status_file = os.path.join(sim_dir, "env_status.json")
        
        default_status = {
            "status": "stopped",
            "twitter_available": False,
            "reddit_available": False,
            "timestamp": None
        }
        
        if not os.path.exists(status_file):
            return default_status
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return {
                "status": status.get("status", "stopped"),
                "twitter_available": status.get("twitter_available", False),
                "reddit_available": status.get("reddit_available", False),
                "timestamp": status.get("timestamp")
            }
        except (json.JSONDecodeError, OSError):
            return default_status

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Intervista un singoloAgent

        Args:
            simulation_id: SimulazioneID
            agent_id: Agent ID
            prompt: domande dell'intervista
            platform: Specifica la piattaforma (facoltativo)）
                - "twitter": Intervista solo su piattaforma Twitter
                - "reddit": Intervista solo su piattaforma Reddit
                - None: Durante la simulazione a doppia piattaforma, intervista due piattaforme contemporaneamente e restituisci i risultati integrati.
            timeout: Timeout (secondi）

        Returns:
            Dizionario dei risultati delle interviste

        Raises:
            ValueError: La simulazione non esiste oppure l'ambiente non è in esecuzione
            TimeoutError: Timeout in attesa di risposta
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"La simulazione non esiste: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"L'ambiente di simulazione non è in esecuzione o è stato chiuso e non può essere eseguito.Interview: {simulation_id}")

        logger.info(f"Invia comando intervista: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}")

        response = ipc_client.send_interview(
            agent_id=agent_id,
            prompt=prompt,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Intervista su più lottiAgent

        Args:
            simulation_id: SimulazioneID
            interviews: Elenco delle interviste, contenuto in ogni elemento {"agent_id": int, "prompt": str, "platform": str(Facoltativo)}
            platform: Piattaforma predefinita (facoltativa, verrà sostituita dalla piattaforma di ciascun elemento dell'intervista）
                - "twitter": Per impostazione predefinita viene intervistata solo la piattaforma Twitter
                - "reddit": Per impostazione predefinita, viene intervistata solo la piattaforma Reddit
                - None: Durante la simulazione a doppia piattaforma, ogni agente intervista due piattaforme contemporaneamente.
            timeout: Timeout (secondi）

        Returns:
            Dizionario dei risultati delle interviste batch

        Raises:
            ValueError: La simulazione non esiste oppure l'ambiente non è in esecuzione
            TimeoutError: Timeout in attesa di risposta
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"La simulazione non esiste: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"L'ambiente di simulazione non è in esecuzione o è stato chiuso e non può essere eseguito.Interview: {simulation_id}")

        logger.info(f"Invia il comando di intervista in batch: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}")

        response = ipc_client.send_batch_interview(
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: str = None,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        Intervista a tutti gli agenti (intervista globale)

        Usa le stesse domande per intervistare tutti nella simulazioneAgent

        Args:
            simulation_id: SimulazioneID
            prompt: Domande dell'intervista (tutti gli agenti utilizzano le stesse domande）
            platform: Specifica la piattaforma (facoltativo)）
                - "twitter": Intervista solo su piattaforma Twitter
                - "reddit": Intervista solo su piattaforma Reddit
                - None: Durante la simulazione a doppia piattaforma, ogni agente intervista due piattaforme contemporaneamente.
            timeout: Timeout (secondi）

        Returns:
            Dizionario dei risultati delle interviste globali
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"La simulazione non esiste: {simulation_id}")

        # Ottieni tutte le informazioni sull'agente dal file di configurazione
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise ValueError(f"La configurazione di rappresentazione non esiste: {simulation_id}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise ValueError(f"Non disponibile nella configurazione di simulazioneAgent: {simulation_id}")

        # Costruisci un elenco di interviste in batch
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({
                    "agent_id": agent_id,
                    "prompt": prompt
                })

        logger.info(f"Invia il comando Intervista globale: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}")

        return cls.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )
    
    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Chiudere l'ambiente di simulazione (invece di interrompere il processo di simulazione)
        
        Invia un comando dell'ambiente di spegnimento alla simulazione per uscire con garbo dalla modalità di comando in attesa
        
        Args:
            simulation_id: SimulazioneID
            timeout: Timeout (secondi）
            
        Returns:
            Dizionario dei risultati dell'operazione
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"La simulazione non esiste: {simulation_id}")
        
        ipc_client = SimulationIPCClient(sim_dir)
        
        if not ipc_client.check_env_alive():
            return {
                "success": True,
                "message": "L'ambiente è chiuso"
            }
        
        logger.info(f"Invia un comando di spegnimento: simulation_id={simulation_id}")
        
        try:
            response = ipc_client.send_close_env(timeout=timeout)
            
            return {
                "success": response.status.value == "completed",
                "message": "Comando di arresto dell'ambiente inviato",
                "result": response.result,
                "timestamp": response.timestamp
            }
        except TimeoutError:
            # Il timeout potrebbe essere dovuto al fatto che l'ambiente si sta spegnendo
            return {
                "success": True,
                "message": "Comando di arresto dell'ambiente inviato (timeout in attesa di risposta, l'ambiente potrebbe essere in fase di arresto）"
            }
    
    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Ottieni la cronologia delle interviste da un unico database"""
        import sqlite3
        
        if not os.path.exists(db_path):
            return []
        
        results = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if agent_id is not None:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview' AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))
            else:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            for user_id, info_json, created_at in cursor.fetchall():
                try:
                    info = json.loads(info_json) if info_json else {}
                except json.JSONDecodeError:
                    info = {"raw": info_json}
                
                results.append({
                    "agent_id": user_id,
                    "response": info.get("response", info),
                    "prompt": info.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name
                })
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Impossibile leggere la cronologia delle interviste ({platform_name}): {e}")
        
        return results

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Ottieni la cronologia delle interviste (leggi dal database）
        
        Args:
            simulation_id: SimulazioneID
            platform: tipo di piattaforma（reddit/twitter/None）
                - "reddit": Get only the history of the Reddit platform
                - "twitter": Ottieni solo la cronologia della piattaforma Twitter
                - None: Ottieni tutta la cronologia per entrambe le piattaforme
            agent_id: Specifica l'ID agente (facoltativo, ottieni solo la cronologia di questo agente)）
            limit: Limite di quantità restituita per piattaforma
            
        Returns:
            InterviewElenco della cronologia
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        results = []
        
        # Determina la piattaforma su cui desideri eseguire la query
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # Quando la piattaforma non è specificata, vengono interrogate due piattaforme.
            platforms = ["twitter", "reddit"]
        
        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = cls._get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit
            )
            results.extend(platform_results)
        
        # Ordina per ordine decrescente
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Se vengono interrogate più piattaforme, limitare il numero totale
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]
        
        return results

