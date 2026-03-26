"""
Modulo di comunicazione IPC analogico
Per la comunicazione tra processi tra il backend Flask e gli script di simulazione

Implementazione di un semplice modello di comando/risposta attraverso il file system：
1. FlaskScrivere comandi nella directory comments/
2. Lo script di simulazione interroga la directory dei comandi, esegue il comando e scrive la risposta nella directory Responses/
3. FlaskEseguire il polling della directory delle risposte per ottenere risultati
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger('mirofish.simulation_ipc')


class CommandType(str, Enum):
    """Tipo di comando"""
    INTERVIEW = "interview"           # Intervista a un singolo agente
    BATCH_INTERVIEW = "batch_interview"  # interviste batch
    CLOSE_ENV = "close_env"           # Ambiente chiuso


class CommandStatus(str, Enum):
    """stato del comando"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """IPCcomando"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """IPCrisposta"""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    Simula client IPC (utilizzato da Flask)
    
    Utilizzato per inviare comandi al processo di simulazione e attendere la risposta
    """
    
    def __init__(self, simulation_dir: str):
        """
        Inizializza il client IPC
        
        Args:
            simulation_dir: Directory dei dati di simulazione
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # Assicurati che la directory esista
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
    
    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """
        Invia il comando e attendi la risposta
        
        Args:
            command_type: Tipo di comando
            args: Parametri di comando
            timeout: Timeout (secondi）
            poll_interval: Intervallo di polling (secondi）
            
        Returns:
            IPCResponse
            
        Raises:
            TimeoutError: Timeout in attesa di risposta
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )
        
        # Scrivi il file di comando
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Invia comando IPC: {command_type.value}, command_id={command_id}")
        
        # In attesa di risposta
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)
                    
                    # Pulisci i file di comando e di risposta
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass
                    
                    logger.info(f"Risposta dell'IPC ricevuta: command_id={command_id}, status={response.status.value}")
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Impossibile analizzare la risposta: {e}")
            
            time.sleep(poll_interval)
        
        # timeout
        logger.error(f"Timeout in attesa della risposta dell'IPC: command_id={command_id}")
        
        # Pulisci il file di comando
        try:
            os.remove(command_file)
        except OSError:
            pass
        
        raise TimeoutError(f"Timeout in attesa della risposta al comando ({timeout}secondi)")
    
    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """
        Invia un comando di intervista a un singolo agente
        
        Args:
            agent_id: Agent ID
            prompt: domande dell'intervista
            platform: Specifica la piattaforma (facoltativo)）
                - "twitter": Intervista solo su piattaforma Twitter
                - "reddit": Intervista solo su piattaforma Reddit  
                - None: Durante la simulazione a doppia piattaforma, intervista entrambe le piattaforme contemporaneamente e durante la simulazione a piattaforma singola, intervista la piattaforma.
            timeout: timeout
            
        Returns:
            IPCResponse，resultIl campo contiene i risultati dell'intervista
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform
            
        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """
        Invia comandi di intervista batch
        
        Args:
            interviews: Elenco delle interviste, contenuto in ogni elemento {"agent_id": int, "prompt": str, "platform": str(Facoltativo)}
            platform: Piattaforma predefinita (facoltativa, verrà sostituita dalla piattaforma di ciascun elemento dell'intervista）
                - "twitter": Per impostazione predefinita viene intervistata solo la piattaforma Twitter
                - "reddit": Per impostazione predefinita, viene intervistata solo la piattaforma Reddit
                - None: Durante la simulazione a doppia piattaforma, ogni agente intervista due piattaforme contemporaneamente.
            timeout: timeout
            
        Returns:
            IPCResponse，resultIl campo contiene tutti i risultati dell'intervista
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform
            
        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        Invia un comando di spegnimento
        
        Args:
            timeout: timeout
            
        Returns:
            IPCResponse
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )
    
    def check_env_alive(self) -> bool:
        """
        Controlla se l'ambiente simulato è vivo
        
        superato l'ispezione env_status.json file per giudicare
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return status.get("status") == "alive"
        except (json.JSONDecodeError, OSError):
            return False


class SimulationIPCServer:
    """
    Simula server IPC (utilizzato dallo script di simulazione)
    
    Interroga la directory dei comandi, esegue il comando e restituisce la risposta
    """
    
    def __init__(self, simulation_dir: str):
        """
        Inizializza il server IPC
        
        Args:
            simulation_dir: Directory dei dati di simulazione
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # Assicurati che la directory esista
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
        
        # stato ambientale
        self._running = False
    
    def start(self):
        """Contrassegna il server come in esecuzione"""
        self._running = True
        self._update_env_status("alive")
    
    def stop(self):
        """Contrassegna il server come arrestato"""
        self._running = False
        self._update_env_status("stopped")
    
    def _update_env_status(self, status: str):
        """Aggiorna il file di stato dell'ambiente"""
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def poll_commands(self) -> Optional[IPCCommand]:
        """
        Effettua il polling della directory dei comandi e restituisce il primo comando in sospeso
        
        Returns:
            IPCCommand o None
        """
        if not os.path.exists(self.commands_dir):
            return None
        
        # Ottieni i file di comando ordinati per ora
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))
        
        command_files.sort(key=lambda x: x[1])
        
        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Impossibile leggere il file di comando: {filepath}, {e}")
                continue
        
        return None
    
    def send_response(self, response: IPCResponse):
        """
        Invia risposta
        
        Args:
            response: IPCrisposta
        """
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Elimina il file di comando
        command_file = os.path.join(self.commands_dir, f"{response.command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass
    
    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Invia una risposta riuscita"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))
    
    def send_error(self, command_id: str, error: str):
        """Invia risposta all'errore"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
