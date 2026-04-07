"""
OASISResponsabile della simulazione
Gestisci simulazioni parallele delle doppie piattaforme Twitter e Reddit
Utilizza script preimpostati + LLM per generare in modo intelligente parametri di configurazione
"""

import os
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import ZepEntityReader, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .calibration_service import CalibrationService
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters

logger = get_logger('mirofish.simulation')


class SimulationStatus(str, Enum):
    """stato di simulazione"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # La simulazione è stata interrotta manualmente
    COMPLETED = "completed"  # Simulazione completata naturalmente
    FAILED = "failed"


class PlatformType(str, Enum):
    """tipo di piattaforma"""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """stato di simulazione"""
    simulation_id: str
    project_id: str
    graph_id: str
    nuts2_region: Optional[str] = None
    
    # Stato abilitato della piattaforma
    enable_twitter: bool = True
    enable_reddit: bool = True
    
    # Stato
    status: SimulationStatus = SimulationStatus.CREATED
    
    # Dati della fase preparatoria
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    
    # Configura le informazioni sulla build
    config_generated: bool = False
    config_reasoning: str = ""
    calibration_profile: Optional[Dict[str, Any]] = None
    
    # dati di esecuzione
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    
    # Timestamp
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # messaggio di errore
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Dizionario di stato completo (utilizzato internamente）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "nuts2_region": self.nuts2_region,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "calibration_profile": self.calibration_profile,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """Dizionario di stato semplificato (l'API restituisce using）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "nuts2_region": self.nuts2_region,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    Responsabile della simulazione
    
    Funzioni principali：
    1. Leggi le entità dalla mappa Zep e filtra
    2. generareOASIS Agent Profile
    3. Utilizza LLM per generare in modo intelligente i parametri di configurazione della simulazione
    4. Preparare tutti i file richiesti per gli script preimpostati
    """
    
    # Directory di archiviazione dei dati di simulazione
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self):
        # Assicurati che la directory esista
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        
        # Cache dello stato della simulazione in memoria
        self._simulations: Dict[str, SimulationState] = {}
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Ottieni la directory dei dati di simulazione"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """Salva lo stato della simulazione su file"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """Carica lo stato della simulazione dal file"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            calibration_profile=data.get("calibration_profile"),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        nuts2_region: Optional[str] = None,
    ) -> SimulationState:
        """
        Crea una nuova simulazione
        
        Args:
            project_id: ProgettoID
            graph_id: ZepAtlanteID
            enable_twitter: Se abilitare la rappresentazione di Twitter
            enable_reddit: Se abilitare la rappresentazione su Reddit
            
        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            nuts2_region=nuts2_region,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )
        
        self._save_simulation_state(state)
        logger.info(f"Crea simulazione: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        nuts2_region: Optional[str] = None,
    ) -> SimulationState:
        """
        Preparare l'ambiente di simulazione (automazione completa)
        
        passi：
        1. Leggi e filtra le entità dal grafico Zep
        2. Genera il profilo dell'agente OASIS per ciascuna entità (miglioramento LLM opzionale, supporta il parallelismo）
        3. Utilizza LLM per generare in modo intelligente i parametri di configurazione della simulazione (time、Livello di Attività、Frequenza del parlato, ecc.）
        4. Salva i file di configurazione e i file di profilo
        5. Copia lo script preimpostato nella directory di simulazione
        
        Args:
            simulation_id: SimulazioneID
            simulation_requirement: Descrizione dei requisiti di simulazione (per la configurazione della generazione LLM）
            document_text: Contenuto del documento originale (per la comprensione del background LLM）
            defined_entity_types: Tipi di entità predefiniti (facoltativo）
            use_llm_for_profiles: Se utilizzare LLM per generare personaggi dettagliati
            progress_callback: Funzione di callback di avanzamento (stage, progress, message)
            parallel_profile_count: Il numero di caratteri generati in parallelo, predefinito3
            
        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"La simulazione non esiste: {simulation_id}")
        
        try:
            state.status = SimulationStatus.PREPARING
            if nuts2_region:
                state.nuts2_region = nuts2_region
            calibration_service = CalibrationService()
            calibration_profile = calibration_service.get_profile(nuts2_region) if nuts2_region else None
            state.calibration_profile = calibration_profile
            self._save_simulation_state(state)
            
            sim_dir = self._get_simulation_dir(simulation_id)
            
            # ========== palco1: Leggere e filtrare le entità ==========
            if progress_callback:
                progress_callback("reading", 0, "Collegamento alla mappa Zep...")
            
            reader = ZepEntityReader()
            
            if progress_callback:
                progress_callback("reading", 30, "Lettura dei dati del nodo...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            
            if progress_callback:
                progress_callback(
                    "reading", 100, 
                    f"Completato, totale {filtered.filtered_count} entità",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "Non è stata trovata alcuna entità corrispondente, controlla se il grafico è costruito correttamente."
                self._save_simulation_state(state)
                return state
            
            # ========== palco2: generareAgent Profile ==========
            total_entities = len(filtered.entities)
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 0, 
                    "Inizio generazione...",
                    current=0,
                    total=total_entities
                )
            
            # in arrivograph_idper abilitare il recupero Zep per un contesto più ricco
            generator = OasisProfileGenerator(graph_id=state.graph_id, nuts2_region=nuts2_region)
            
            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 
                        int(current / total * 100), 
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )
            
            # Imposta il percorso del file per il salvataggio in tempo reale (preferibilmente utilizzando il formato JSON Reddit）
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"
            
            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # in arrivograph_idUtilizzato per il recupero Zep
                parallel_count=parallel_profile_count,  # Number of parallel builds
                realtime_output_path=realtime_output_path,  # Salva il percorso in tempo reale
                output_platform=realtime_platform,  # Formato di uscita
                nuts2_region=nuts2_region,
            )
            
            state.profiles_count = len(profiles)
            
            # Salva il file del profilo (nota: Twitter utilizza il formato CSV, Reddit utilizza il formato JSON）
            # Reddit È stato salvato in tempo reale durante il processo di generazione. Salvalo di nuovo qui per assicurarne la completezza.
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95, 
                    "Salva il file del profilo...",
                    current=total_entities,
                    total=total_entities
                )
            
            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )
            
            if state.enable_twitter:
                # TwitterUtilizza il formato CSV！Questo è un requisito di OASIS
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 100, 
                    f"Completato, totale {len(profiles)} unProfile",
                    current=len(profiles),
                    total=len(profiles)
                )
            
            # ========== palco3: LLMGenerazione intelligente di configurazioni di simulazione ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, 
                    "Analisi dei requisiti di simulazione...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator()
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30, 
                    "Chiamata LLM per configurazione...",
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit,
                nuts2_region=nuts2_region,
                calibration_profile=calibration_profile,
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70, 
                    "Salvataggio del file di configurazione...",
                    current=2,
                    total=3
                )
            
            # Salva il file di configurazione
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            state.calibration_profile = calibration_profile
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100, 
                    "Configurazione completata",
                    current=3,
                    total=3
                )
            
            # NOTA: lo script di esecuzione rimane nella directory backend/scripts/ e non viene più copiato nella directory di simulazione
            # Quando si avvia la simulazione，simulation_runner eseguirà gli script dalla directory scripts/
            
            # stato dell'aggiornamento
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"Simulazione pronta: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"La preparazione della simulazione non è riuscita: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """Ottieni lo stato della simulazione"""
        return self._load_simulation_state(simulation_id)
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """Elenca tutte le simulazioni"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Salta i file nascosti (come .DS_Store）e file non directory
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations

    def delete_simulation(self, simulation_id: str) -> bool:
        """Elimina definitivamente una simulazione e i suoi artefatti locali."""
        sim_dir = self._get_simulation_dir(simulation_id)
        if not os.path.isdir(sim_dir):
            return False

        shutil.rmtree(sim_dir)
        logger.info(f"Simulazione eliminata: {simulation_id}")
        return True
    
    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """ottenere simulatoAgent Profile"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"La simulazione non esiste: {simulation_id}")
        
        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")
        
        if not os.path.exists(profile_path):
            return []
        
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni la configurazione della simulazione"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """Ottieni istruzioni per la corsa"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. Attiva l'ambiente conda: conda activate MiroFish\n"
                f"2. Esegui la simulazione (La sceneggiatura si trova in {scripts_dir}):\n"
                f"   - Corri da soloTwitter: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - Corri da soloReddit: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - Esecuzione di due piattaforme in parallelo: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
