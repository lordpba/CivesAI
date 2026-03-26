"""
Simula il routing API correlato
Step2: ZepLettura e filtraggio delle entità、OASISPreparazione e funzionamento della simulazione (automazione completa）
"""

import os
import traceback
from flask import request, jsonify, send_file

from . import simulation_bp
from ..config import Config
from ..services.zep_entity_reader import ZepEntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.logger import get_logger
from ..models.project import ProjectManager

logger = get_logger('mirofish.api.simulation')


# Interview prompt Ottimizza il prefisso
# L'aggiunta di questo prefisso può evitare che l'agente chiami lo strumento e risponda direttamente con il testo.
INTERVIEW_PROMPT_PREFIX = "Combinalo con la tua personalità、Tutti i ricordi e le azioni passate, rispondimi direttamente tramite SMS senza utilizzare alcuno strumento.："


def optimize_interview_prompt(prompt: str) -> str:
    """
    Ottimizza le domande dell'intervista e aggiungi prefissi per evitare che gli agenti chiamino gli strumenti
    
    Args:
        prompt: Domanda originale
        
    Returns:
        Domande ottimizzate
    """
    if not prompt:
        return prompt
    # Evitare di aggiungere prefissi ripetutamente
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


# ============== Interfaccia di lettura delle entità ==============

@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """
    Ottieni tutte le entità nel grafico (filtrato)
    
    Restituisce solo i nodi che corrispondono ai tipi di entità predefiniti (le etichette non sono solo nodi di entità)
    
    Parametri di query：
        entity_types: Elenco separato da virgole di tipi di entità (facoltativo, per ulteriori filtri）
        enrich: Se ottenere informazioni secondarie rilevanti (defaulttrue）
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEYNon configurato"
            }), 500
        
        entity_types_str = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        logger.info(f"Ottieni entità grafiche: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")
        
        reader = ZepEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere l'entità del grafico: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Ottieni i dettagli di una singola entità"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEYNon configurato"
            }), 500
        
        reader = ZepEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)
        
        if not entity:
            return jsonify({
                "success": False,
                "error": f"L'entità non esiste: {entity_uuid}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": entity.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere i dettagli dell'entità: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """Ottieni tutte le entità del tipo specificato"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEYNon configurato"
            }), 500
        
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        reader = ZepEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities]
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere l'entità: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia di gestione analogica ==============

@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """
    Crea una nuova simulazione
    
    Nota：max_roundsParametri come questi vengono generati in modo intelligente da LLM e non richiedono impostazioni manuali.
    
    Richiesta（JSON）：
        {
            "project_id": "proj_xxxx",      // Obbligatorio
            "graph_id": "mirofish_xxxx",    // Facoltativo, se non previsto, sarà ricavato dal progetto
            "enable_twitter": true,          // Facoltativo, predefinitotrue
            "enable_reddit": true            // Facoltativo, predefinitotrue
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "mirofish_xxxx",
                "status": "created",
                "enable_twitter": true,
                "enable_reddit": true,
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci project_id"
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Il progetto non esiste: {project_id}"
            }), 404
        
        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Il progetto non ha ancora creato una mappa, per favore chiama prima /api/graph/build"
            }), 400
        
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
        )
        
        return jsonify({
            "success": True,
            "data": state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Impossibile creare la simulazione: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Controlla se la simulazione è pronta per essere completata
    
    Controlla le condizioni：
    1. state.json esiste e lo stato è "ready"
    2. Esistono i file necessari：reddit_profiles.json, twitter_profiles.csv, simulation_config.json
    
    NOTA: eseguire lo script(run_*.py)Rimani nella directory backend/scripts/ e non copiare più nella directory di simulazione
    
    Args:
        simulation_id: SimulazioneID
        
    Returns:
        (is_prepared: bool, info: dict)
    """
    import os
    from ..config import Config
    
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    
    # Controlla se la directory esiste
    if not os.path.exists(simulation_dir):
        return False, {"reason": "La directory di simulazione non esiste"}
    
    # Elenco dei file richiesti (esclusi gli script, che si trovano in backend/scripts/）
    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv"
    ]
    
    # Controlla se il file esiste
    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)
    
    if missing_files:
        return False, {
            "reason": "File necessari mancanti",
            "missing_files": missing_files,
            "existing_files": existing_files
        }
    
    # Controllastate.jsonnello stato
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        import json
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        
        # Registro dettagliato
        logger.debug(f"Controlla lo stato di preparazione della simulazione: {simulation_id}, status={status}, config_generated={config_generated}")
        
        # se config_generated=True e il file esiste, la preparazione è considerata completata.
        # Tutti gli stati seguenti indicano che il lavoro di preparazione è stato completato：
        # - ready: Pronto a correre
        # - preparing: se config_generated=True Descrizione completata
        # - running: Correre, indicando che la preparazione è stata completata molto tempo fa
        # - completed: L'operazione è completata, indicando che la preparazione è stata completata molto tempo fa.
        # - stopped: Interrotto, indicando che la preparazione è stata completata molto tempo fa
        # - failed: L'esecuzione non è riuscita (ma la preparazione è stata completata）
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            # Ottieni statistiche sui file
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
            config_file = os.path.join(simulation_dir, "simulation_config.json")
            
            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0
            
            # Se lo stato è in preparazione ma il file è stato completato, lo stato aggiornato automaticamente saràready
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    from datetime import datetime
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Aggiorna automaticamente lo stato della simulazione: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"Aggiornamento automatico dello stato non riuscito: {e}")
            
            logger.info(f"Simulazione {simulation_id} Risultati dei test: Pronto (status={status}, config_generated={config_generated})")
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(f"Simulazione {simulation_id} Risultati dei test: Non ancora pronto (status={status}, config_generated={config_generated})")
            return False, {
                "reason": f"Lo stato non è nell'elenco preparato oconfig_generatedperfalse: status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated
            }
            
    except Exception as e:
        return False, {"reason": f"Impossibile leggere il file di stato: {str(e)}"}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """
    Preparare l'ambiente di simulazione (attività asincrone, LLM genera in modo intelligente tutti i parametri)
    
    Questa è un'operazione che richiede tempo e l'interfaccia tornerà immediatamentetask_id，
    Utilizzare GET /api/simulation/prepare/status per interrogare lo stato di avanzamento
    
    Caratteristiche:
    - Rileva automaticamente le preparazioni completate per evitare generazioni ripetute
    - Se la preparazione è completata, restituire direttamente i risultati esistenti
    - Supporta la rigenerazione forzata（force_regenerate=true）
    
    passi：
    1. Controllare se i preparativi sono stati completati
    2. Leggi e filtra le entità dal grafico Zep
    3. perGenera il profilo dell'agente OASIS per ciascuna entità (con meccanismo di riprova）
    4. LLMGenerazione intelligente della configurazione della simulazione (con meccanismo di ripetizione)）
    5. Salva file di configurazione e script preimpostati
    
    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",                   // Obbligatorio, simulaID
            "entity_types": ["Student", "PublicFigure"],  // Facoltativo, specificare il tipo di entità
            "use_llm_for_profiles": true,                 // Facoltativo,SìSe utilizzare LLM per generare caratteri
            "parallel_profile_count": 5,                  // Facoltativo, il numero di caratteri generati in parallelo, predefinito5
            "force_regenerate": false                     // Opzionale, forza rigenerazione, impostazione predefinitafalse
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",           // Ritorna quando nuova attività
                "status": "preparing|ready",
                "message": "L'attività di preparazione è stata avviata|I lavori preparatori sono stati completati",
                "already_prepared": true|false    // Sei pronto?
            }
        }
    """
    import threading
    import os
    from ..models.task import TaskManager, TaskStatus
    from ..config import Config
    
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400
        
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404
        
        # Verificare se forzare una rigenerazione
        force_regenerate = data.get('force_regenerate', False)
        logger.info(f"Avvia l'elaborazione/prepara la richiesta: simulation_id={simulation_id}, force_regenerate={force_regenerate}")
        
        # Controlla se è pronto (per evitare generazioni ripetute）
        if not force_regenerate:
            logger.debug(f"Controlla la simulazione {simulation_id} Sei pronto?...")
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(f"Controlla i risultati: is_prepared={is_prepared}, prepare_info={prepare_info}")
            if is_prepared:
                logger.info(f"Simulazione {simulation_id} Preparato, salta la generazione ripetuta")
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": "I preparativi sono stati completati, non è necessario rigenerare",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
            else:
                logger.info(f"Simulazione {simulation_id} La preparazione non è completata e l'attività di preparazione verrà avviata.")
        
        # Ottieni le informazioni necessarie dal progetto
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Il progetto non esiste: {state.project_id}"
            }), 404
        
        # Ottieni i requisiti di simulazione
        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Nel progetto manca la descrizione dei requisiti di simulazione (simulation_requirement)"
            }), 400
        
        # Ottieni il testo del documento
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        
        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)
        
        # ========== Ottieni il numero di entità in modo sincrono (prima di avviare l'attività in background） ==========
        # In questo modo, il front-end può ottenere immediatamente il numero totale previsto di agenti dopo aver chiamato prepare.
        try:
            logger.info(f"Ottieni il numero di entità in modo sincrono: graph_id={state.graph_id}")
            reader = ZepEntityReader()
            # Leggi rapidamente le entità (non sono richieste informazioni secondarie, conta solo la quantità)）
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # Non ottenere informazioni secondarie, accelera
            )
            # Salva il numero di entità nello stato (perché il front-end possa ottenerlo immediatamente）
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(f"Numero previsto di entità: {filtered_preview.filtered_count}, Digitare: {filtered_preview.entity_types}")
        except Exception as e:
            logger.warning(f"Impossibile ottenere il numero di entità in modo sincrono (riproveremo nell'attività in background）: {e}")
            # Il fallimento non influenzerà i processi successivi e le attività in background verranno riacquisite.
        
        # Creare un'attività asincrona
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id
            }
        )
        
        # Aggiorna lo stato della simulazione (contiene il numero di entità precaricate）
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)
        
        # Definire le attività in background
        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="Inizio preparazione sandbox..."
                )
                
                # Prepararsi per la simulazione (con callback sull'avanzamento）
                # Dettagli avanzamento fase di archiviazione
                stage_details = {}
                
                def progress_callback(stage, progress, message, **kwargs):
                    # Calcola il progresso totale
                    stage_weights = {
                        "reading": (0, 20),           # 0-20%
                        "generating_profiles": (20, 70),  # 20-70%
                        "generating_config": (70, 90),    # 70-90%
                        "copying_scripts": (90, 100)       # 90-100%
                    }
                    
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)
                    
                    # Crea informazioni dettagliate sullo stato di avanzamento
                    stage_names = {
                        "reading": "Lettura Entità Mappa",
                        "generating_profiles": "Generazione Profili Cittadini/PA",
                        "generating_config": "Generazione Algoritmi Simulazione",
                        "copying_scripts": "Inizializzazione Motore Eventi"
                    }
                    
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)
                    
                    # Aggiorna i dettagli della fase
                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }
                    
                    # Crea informazioni dettagliate sullo stato di avanzamento
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }
                    
                    # Costruisci messaggi concisi
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"
                    
                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )
                
                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count
                )
                
                # Missione compiuta
                task_manager.complete_task(
                    task_id,
                    result=result_state.to_simple_dict()
                )
                
            except Exception as e:
                logger.error(f"La preparazione per la simulazione non è riuscita: {str(e)}")
                task_manager.fail_task(task_id, str(e))
                
                # Aggiorna lo stato della simulazione su fallito
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)
        
        # Avvia il thread in background
        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": "L'attività di preparazione è stata avviata, controlla l'avanzamento tramite /api/simulation/prepare/status",
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # Numero totale previsto di agenti
                "entity_types": state.entity_types  # Elenco dei tipi di entità
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"Avviare l'attività di preparazione non riuscita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """
    Query the progress of preparation tasks
    
    Supports two query methods：
    1. Passatask_idInterrogare lo stato di avanzamento delle attività in corso
    2. Passasimulation_idControllare se i preparativi sono stati completati
    
    Richiesta（JSON）：
        {
            "task_id": "task_xxxx",          // Facoltativo, restituito da preparetask_id
            "simulation_id": "sim_xxxx"      // ID fittizio facoltativo (utilizzato per verificare la preparazione completata）
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // I preparativi sono completati?
                "prepare_info": {...}            // Dettagli quando pronti
            }
        }
    """
    from ..models.task import TaskManager
    
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # se fornitosimulation_id，Per prima cosa controlla se è pronto
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "I lavori preparatori sono stati completati",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
        
        # in caso contrariotask_id，errore di restituzione
        if not task_id:
            if simulation_id:
                # Sìsimulation_idma non ancora pronto
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": "La preparazione non è ancora iniziata, chiama /api/simulation/prepare per iniziare",
                        "already_prepared": False
                    }
                })
            return jsonify({
                "success": False,
                "error": "per favore fornisci task_id o simulation_id"
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            # L'attività non esiste, ma se esistesimulation_id，Controlla se è pronto
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "L'attività è completata (il lavoro di preparazione esiste già）",
                            "already_prepared": True,
                            "prepare_info": prepare_info
                        }
                    })
            
            return jsonify({
                "success": False,
                "error": f"L'attività non esiste: {task_id}"
            }), 404
        
        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        
        return jsonify({
            "success": True,
            "data": task_dict
        })
        
    except Exception as e:
        logger.error(f"Impossibile interrogare lo stato dell'attività: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """Ottieni lo stato della simulazione"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404
        
        result = state.to_dict()
        
        # Se la simulazione è pronta, aggiungi le istruzioni per l'esecuzione
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere lo stato della simulazione: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """
    Elenca tutte le simulazioni
    
    Parametri di query：
        project_id: Filtra per ID progetto (facoltativo）
    """
    try:
        project_id = request.args.get('project_id')
        
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)
        
        return jsonify({
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations)
        })
        
    except Exception as e:
        logger.error(f"Elenca gli errori di simulazione: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """
    Ottieni l'ultima versione corrispondente alla simulazione report_id
    
    Attraversa la directory dei report e scoprilo simulation_id rapporto di corrispondenza,
    Se ce ne sono più, restituire l'ultimo (premere created_at ordinare）
    
    Args:
        simulation_id: SimulazioneID
        
    Returns:
        report_id o None
    """
    import json
    from datetime import datetime
    
    # reports percorso della directory：backend/uploads/reports
    # __file__ Sì app/api/simulation.py，È necessario salire di due livelli backend/
    reports_dir = os.path.join(os.path.dirname(__file__), '../../uploads/reports')
    if not os.path.exists(reports_dir):
        return None
    
    matching_reports = []
    
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue
            
            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue
            
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                if meta.get("simulation_id") == simulation_id:
                    matching_reports.append({
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", "")
                    })
            except Exception:
                continue
        
        if not matching_reports:
            return None
        
        # Ordina in ordine inverso rispetto all'ora di creazione e restituisce l'ultimo
        matching_reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")
        
    except Exception as e:
        logger.warning(f"Trova simulation {simulation_id} Il rapporto è fallito: {e}")
        return None


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """
    Ottieni un elenco di simulazioni storiche (con i dettagli del progetto)
    
    Utilizzato per visualizzare i progetti storici sulla home page, restituendo il nome del progetto、Elenco delle simulazioni con informazioni dettagliate come la descrizione
    
    Parametri di query：
        limit: Limite quantità reso (predefinito 20)
    
    Ritorno：
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "Analisi dell'opinione pubblica dell'Università di Wuhan",
                    "simulation_requirement": "Se l'Università di Wuhan rilascia...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]
        
        # Migliora i dati di simulazione, leggi solo dal file di simulazione
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()
            
            # Ottieni informazioni sulla configurazione della simulazione (da simulation_config.json leggere simulation_requirement）
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # Numero consigliato di round (valore di backup）
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60 / 
                    max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0
            
            # Ottieni lo stato di esecuzione (da run_state.json Leggere il numero effettivo di round impostati dall'utente）
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # Utilizza le impostazioni utente total_rounds，In caso contrario, utilizzare il numero di giri consigliato
                sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds
            
            # Ottieni l'elenco dei file dei progetti associati (fino a 3）
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "file sconosciuto")} 
                    for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []
            
            # Associati report_id（Trova l'ultima versione di questa simulazione report）
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)
            
            # Aggiungi il numero di versione
            sim_dict["version"] = "v1.0.2"
            
            # Formato data
            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except:
                sim_dict["created_date"] = ""
            
            enriched_simulations.append(sim_dict)
        
        return jsonify({
            "success": True,
            "data": enriched_simulations,
            "count": len(enriched_simulations)
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere la simulazione storica: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """
    Ottieni il profilo agente simulato
    
    Parametri di query：
        platform: Tipo di piattaforma (reddit/twitter, predefinitareddit）
    """
    try:
        platform = request.args.get('platform', 'reddit')
        
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il profilo: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """
    Ottieni il profilo agente simulato in tempo reale (utilizzato per visualizzare l'avanzamento in tempo reale durante il processo di generazione)
    
    Differenze rispetto all'interfaccia /profiles:
    - Leggi i file direttamente senza passare da SimulationManager
    - Adatto per la visualizzazione in tempo reale durante il processo di generazione
    - Restituisce metadati aggiuntivi (come l'ora di modifica del file、Se viene generato, ecc.)
    
    Parametri di query：
        platform: Tipo di piattaforma (reddit/twitter, reddit predefinita)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,  // Totale previsto (se presente）
                "is_generating": true,  // sta generando
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import json
    import csv
    from datetime import datetime
    
    try:
        platform = request.args.get('platform', 'reddit')
        
        # Ottieni la directory di simulazione
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404
        
        # Determina il percorso del file
        if platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")
        
        # Controlla se il file esiste
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None
        
        if file_exists:
            # Ottieni l'ora di modifica del file
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                if platform == "reddit":
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles = json.load(f)
                else:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Impossibile leggere il file dei profili (potrebbe essere in scrittura）: {e}")
                profiles = []
        
        # Controlla se viene generato (tramite state.json giudice）
        is_generating = False
        total_expected = None
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il profilo in tempo reale: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """
    Ottieni la configurazione della simulazione in tempo reale (per visualizzare l'avanzamento in tempo reale durante il processo di creazione)
    
    Differenze dall'interfaccia /config:
    - Leggi i file direttamente senza passare da SimulationManager
    - Adatto per la visualizzazione in tempo reale durante il processo di generazione
    - Restituisce metadati aggiuntivi (come l'ora di modifica del file、Se viene generato, ecc.)
    - È possibile restituire informazioni parziali anche se la configurazione non è stata ancora generata
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,  // sta generando
                "generation_stage": "generating_config",  // Fase di costruzione attuale
                "config": {...}  // Contenuto della configurazione (se presente）
            }
        }
    """
    import json
    from datetime import datetime
    
    try:
        # Ottieni la directory di simulazione
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404
        
        # Percorso del file di configurazione
        config_file = os.path.join(sim_dir, "simulation_config.json")
        
        # Controlla se il file esiste
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None
        
        if file_exists:
            # Ottieni l'ora di modifica del file
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Impossibile leggere il file di configurazione (potrebbe essere in scrittura）: {e}")
                config = None
        
        # Controlla se viene generato (tramite state.json giudice）
        is_generating = False
        generation_stage = None
        config_generated = False
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)
                    
                    # Determina la fase attuale
                    if is_generating:
                        if state_data.get("profiles_generated", False):
                            generation_stage = "generating_config"
                        else:
                            generation_stage = "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
            except Exception:
                pass
        
        # Costruisci dati di ritorno
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config
        }
        
        # Se la configurazione esiste, estrai alcune statistiche chiave
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model")
            }
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere la configurazione in tempo reale: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """
    Ottieni la configurazione della simulazione (configurazione completa generata in modo intelligente da LLM)
    
    Il reso contiene：
        - time_config: Configurazione temporale (durata della simulazione、giri、ore di picco/minimo）
        - agent_configs: La configurazione dell'attività di ciascun agente (activity、frequenza parlante、posizione ecc.）
        - event_config: configurazione evento (post iniziale、argomenti caldi）
        - platform_configs: Configurazione della piattaforma
        - generation_reasoning: LLMDescrizione del ragionamento della configurazione di
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        
        if not config:
            return jsonify({
                "success": False,
                "error": f"La configurazione della simulazione non esiste, richiama prima l'interfaccia /prepare"
            }), 404
        
        return jsonify({
            "success": True,
            "data": config
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere la configurazione: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """Scarica il file di configurazione della simulazione"""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "Il file di configurazione non esiste, richiama prima l'interfaccia /prepare"
            }), 404
        
        return send_file(
            config_path,
            as_attachment=True,
            download_name="simulation_config.json"
        )
        
    except Exception as e:
        logger.error(f"Impossibile scaricare la configurazione: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """
    Scaricare il file dello script di esecuzione della simulazione (script generico, disponibile in backend/scripts/）
    
    script_nameValore facoltativo：
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # Lo script si trova nella directory backend/scripts/
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        # Nome dello script di convalida
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py", 
            "run_parallel_simulation.py",
            "action_logger.py"
        ]
        
        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": f"scrittura sconosciuta: {script_name}，Facoltativo: {allowed_scripts}"
            }), 400
        
        script_path = os.path.join(scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": f"Il file di script non esiste: {script_name}"
            }), 404
        
        return send_file(
            script_path,
            as_attachment=True,
            download_name=script_name
        )
        
    except Exception as e:
        logger.error(f"Download dello script non riuscito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== ProfileGenera interfaccia (per uso indipendente） ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    Genera il profilo dell'agente OASIS direttamente dal grafico (senza creare una simulazione)
    
    Richiesta（JSON）：
        {
            "graph_id": "mirofish_xxxx",     // Obbligatorio
            "entity_types": ["Student"],      // Facoltativo
            "use_llm": true,                  // Facoltativo
            "platform": "reddit"              // Facoltativo
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci graph_id"
            }), 400
        
        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')
        
        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )
        
        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": "Nessuna entità corrispondente trovata"
            }), 400
        
        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        
        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile generare il profilo: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia di controllo del funzionamento della simulazione ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    Inizia a eseguire la simulazione

    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",          // Obbligatorio, simulaID
            "platform": "parallel",                // Facoltativo: twitter / reddit / parallel (Predefinito)
            "max_rounds": 100,                     // Facoltativo: Numero massimo di cicli di simulazione, utilizzato per troncare le simulazioni troppo lunghe
            "enable_graph_memory_update": false,   // Facoltativo: Se aggiornare dinamicamente le attività dell'agente nella memoria della mappa Zep
            "force": false                         // Facoltativo: Forza un riavvio (interromperà la simulazione in esecuzione e cancellerà i registri）
        }

    Per quanto riguarda il parametro forza:
        - Quando abilitato, se la simulazione è in esecuzione o è stata completata, verrà prima arrestata e pulita il registro di esecuzione
        - Il contenuto pulito include：run_state.json, actions.jsonl, simulation.log Aspetta
        - Non pulirà i file di configurazione（simulation_config.json）e file di profilo
        - Adatto per scenari in cui è necessario eseguire nuovamente la simulazione

    Circa enable_graph_memory_update：
        - Se abilitato, le attività di tutti gli agenti nella simulazione (pubblicazione、Commento、Mi piace, ecc.) verranno aggiornati sulla mappa Zep in tempo reale
        - Ciò consente al grafico di"ricorda"Processo di simulazione per analisi successive o dialogo AI
        - I progetti che necessitano di essere simulati sono validi graph_id
        - Utilizza il meccanismo di aggiornamento batch per ridurre il numero di chiamate API

    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // Se l'aggiornamento della memoria della mappa è abilitato
                "force_restarted": true               // È una ripartenza forzata?
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400

        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  # Facoltativo: numero massimo di round di simulazione
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # Facoltativo: se abilitare l'aggiornamento della memoria della mappa
        force = data.get('force', False)  # Facoltativo: forzare un riavvio

        # Verifica max_rounds parametri
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "max_rounds Deve essere un numero intero positivo"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "max_rounds Deve essere un numero intero valido"
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel']:
            return jsonify({
                "success": False,
                "error": f"Tipo di piattaforma non valido: {platform}，Facoltativo: twitter/reddit/parallel"
            }), 400

        # Controlla se la simulazione è pronta
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404

        force_restarted = False
        
        # Stato di elaborazione intelligente: consente il riavvio se la preparazione è completa
        if state.status != SimulationStatus.READY:
            # Controlla se i preparativi sono completi
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # La preparazione è completata, controlla se ci sono processi in esecuzione
                if state.status == SimulationStatus.RUNNING:
                    # Controlla se il processo simulato è effettivamente in esecuzione
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # Il processo è effettivamente in corso
                        if force:
                            # Modalità forzata: interrompe una simulazione in esecuzione
                            logger.info(f"Modalità forzata: interrompe una simulazione in esecuzione {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"Avvertimento quando si interrompe la simulazione: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": f"La simulazione è in esecuzione, richiamare prima l'interfaccia /stop per interromperla oppure utilizzare force=true forzare il riavvio"
                            }), 400

                # Se è la modalità forzata, cancellare il registro di esecuzione
                if force:
                    logger.info(f"Modalità forzata: pulisci i registri di simulazione {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"Avviso durante la cancellazione dei registri: {cleanup_result.get('errors')}")
                    force_restarted = True

                # Il processo non esiste o è terminato e lo stato di ripristino lo è ready
                logger.info(f"Simulazione {simulation_id} Il lavoro di preparazione è stato completato e lo stato di ripristino è pronto (stato originale: {state.status.value}）")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # Lavori di preparazione non completati
                return jsonify({
                    "success": False,
                    "error": f"La simulazione non è pronta, stato attuale: {state.status.value}，Per favore chiama prima /prepara l'interfaccia"
                }), 400
        
        # Ottieni l'ID della mappa (utilizzato per l'aggiornamento della memoria della mappa）
        graph_id = None
        if enable_graph_memory_update:
            # Ottieni dallo stato o dal progetto della simulazione graph_id
            graph_id = state.graph_id
            if not graph_id:
                # Prova a ottenere da project
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id
            
            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "L'abilitazione degli aggiornamenti della memoria della mappa richiede un file valido graph_id，Assicurati che il progetto abbia creato il grafico"
                }), 400
            
            logger.info(f"Abilita gli aggiornamenti della memoria della mappa: simulation_id={simulation_id}, graph_id={graph_id}")
        
        # Avvia la simulazione
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )
        
        # Aggiorna lo stato della simulazione
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Impossibile avviare la simulazione: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    Interrompi la simulazione
    
    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx"  // Obbligatorio, simulaID
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400
        
        run_state = SimulationRunner.stop_simulation(simulation_id)
        
        # Aggiorna lo stato della simulazione
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Interruzione della simulazione non riuscita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia di monitoraggio dello stato in tempo reale ==============

@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """
    Ottieni lo stato in tempo reale dell'esecuzione della simulazione (per il polling front-end)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                }
            })
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere lo stato di esecuzione: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """
    Ottieni lo stato dettagliato dell'esecuzione della simulazione (comprese tutte le azioni)
    
    Utilizzato per la visualizzazione front-end delle dinamiche in tempo reale
    
    Parametri di query：
        platform: Piattaforma di filtraggio (twitter/reddit, opzionale)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # Twitter Tutte le azioni sulla piattaforma
                "reddit_actions": [...]    # Reddit Tutte le azioni sulla piattaforma
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": []
                }
            })
        
        # Ottieni l'elenco completo delle azioni
        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter
        )
        
        # Ottieni azioni per piattaforma
        twitter_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="twitter"
        ) if not platform_filter or platform_filter == "twitter" else []
        
        reddit_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="reddit"
        ) if not platform_filter or platform_filter == "reddit" else []
        
        # Ottieni l'azione del round corrente（recent_actions Mostra solo l'ultimo round）
        current_round = run_state.current_round
        recent_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
            round_num=current_round
        ) if current_round > 0 else []
        
        # Ottieni informazioni di base sullo stato
        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        # recent_actions Visualizza solo l'ultima serie di contenuti delle due piattaforme
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere lo stato dettagliato: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """
    Ottieni la cronologia delle azioni dell'agente nella simulazione
    
    Parametri di query：
        limit: Quantità restituita (impostazione predefinita100）
        offset: offset (predefinito0）
        platform: piattaforma di filtraggio（twitter/reddit）
        agent_id: filtroAgent ID
        round_num: giri di filtro
    
    Ritorno：
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)
        
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere la cronologia delle azioni: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """
    Ottieni la sequenza temporale della simulazione (riepilogata per round)
    
    Utilizzato per la visualizzazione front-end della barra di avanzamento e della visualizzazione della sequenza temporale
    
    Parametri di query：
        start_round: Turno iniziale (predefinito0）
        end_round: Fine round (predefinito tutto)
    
    Restituisci informazioni di riepilogo per ogni round
    """
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)
        
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )
        
        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere la sequenza temporale: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """
    Ottieni statistiche per ciascun agente
    
    Utilizzato per la visualizzazione front-end delle classifiche delle attività dell'agente、Distribuzione dell'azione, ecc.
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        
        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere le statistiche dell'agente: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia di interrogazione del database ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """
    Ottieni post in simulazione
    
    Parametri di query：
        platform: tipo di piattaforma（twitter/reddit）
        limit: Quantità restituita (impostazione predefinita50）
        offset: compensare
    
    Restituisce l'elenco dei post (letto dal database SQLite）
    """
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "Il database non esiste, la simulazione potrebbe non essere stata ancora eseguita"
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            posts = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
            
        except sqlite3.OperationalError:
            posts = []
            total = 0
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere i post: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """
    Ricevi commenti in una simulazione (solo Reddit)
    
    Parametri di query：
        post_id: Filtra l'ID del post (facoltativo）
        limit: Quantità restituita
        offset: compensare
    """
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_path = os.path.join(sim_dir, "reddit_simulation.db")
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            
            comments = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.OperationalError:
            comments = []
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere commenti: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interview Interfaccia per interviste ==============

@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """
    Intervista un singolo agente

    Nota: questa funzione richiede che l'ambiente di simulazione sia in esecuzione (accedere alla modalità comando di attesa dopo aver completato il ciclo di simulazione)

    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",       // Obbligatorio, simulaID
            "agent_id": 0,                     // Obbligatorio，Agent ID
            "prompt": "cosa ne pensi di questa faccenda?？",  // Obbligatorio, domande per il colloquio
            "platform": "twitter",             // Facoltativo, specificare la piattaforma (twitter/reddit)
                                               // Quando non specificato: la simulazione doppia piattaforma intervista due piattaforme contemporaneamente
            "timeout": 60                      // Facoltativo, timeout (secondi), predefinito60
        }

    Ritorno (nessuna piattaforma specificata, modalità doppia piattaforma）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "cosa ne pensi di questa faccenda?？",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    Ritorno (specificareplatform）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "cosa ne pensi di questa faccenda?？",
                "result": {
                    "agent_id": 0,
                    "response": "Penso...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # Facoltativo：twitter/reddit/None
        timeout = data.get('timeout', 60)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400
        
        if agent_id is None:
            return jsonify({
                "success": False,
                "error": "per favore fornisci agent_id"
            }), 400
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": "Si prega di fornire una richiesta (domanda per l'intervista）"
            }), 400
        
        # Verificare i parametri della piattaforma
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform I parametri possono solo essere 'twitter' o 'reddit'"
            }), 400
        
        # Controlla lo stato dell'ambiente
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "L'ambiente di simulazione non è in esecuzione o è spento. Assicurati che la simulazione sia stata completata e che sia attivata la modalità di attesa comando。"
            }), 400
        
        # Ottimizza le richieste e aggiungi prefissi per evitare che l'agente chiami gli strumenti
        optimized_prompt = optimize_interview_prompt(prompt)
        
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Timeout in attesa della risposta al colloquio: {str(e)}"
        }), 504
        
    except Exception as e:
        logger.error(f"Interviewfallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """
    Intervista più agenti in lotti

    Nota: questa funzionalità richiede che l'ambiente di simulazione sia in esecuzione

    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",       // Obbligatorio, simulaID
            "interviews": [                    // Obbligatorio, elenco interviste
                {
                    "agent_id": 0,
                    "prompt": "Cosa ne pensi dell'A？",
                    "platform": "twitter"      // Facoltativo, specificare la piattaforma di colloquio dell'Agente
                },
                {
                    "agent_id": 1,
                    "prompt": "Cosa ne pensi di B?？"  // Se la piattaforma non è specificata, viene utilizzato il valore predefinito
                }
            ],
            "platform": "reddit",              // Piattaforma predefinita facoltativa (sostituita da ciascuna piattaforma)
                                               // Quando non specificato: la simulazione doppia piattaforma consente a ciascun Agente di intervistare due piattaforme contemporaneamente
            "timeout": 120                     // Facoltativo, timeout (secondi), predefinito120
        }

    Ritorno：
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')  # Facoltativo：twitter/reddit/None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": "Si prega di fornire interviste (elenco delle interviste）"
            }), 400

        # Verificare i parametri della piattaforma
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform I parametri possono solo essere 'twitter' o 'reddit'"
            }), 400

        # Verificare ogni elemento dell'intervista
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"Elenco interviste n.{i+1}Articolo mancante agent_id"
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"Elenco interviste n.{i+1}Articolo mancante prompt"
                }), 400
            # Verificare la piattaforma di ciascun articolo (se presente）
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": f"Elenco interviste n.{i+1}La piattaforma di un articolo può essere solo 'twitter' o 'reddit'"
                }), 400

        # Controlla lo stato dell'ambiente
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "L'ambiente di simulazione non è in esecuzione o è spento. Assicurati che la simulazione sia stata completata e che sia attivata la modalità di attesa comando。"
            }), 400

        # Ottimizza la richiesta di ciascun elemento dell'intervista e aggiungi un prefisso per evitare che gli agenti chiamino gli strumenti
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Timeout in attesa della risposta all'intervista batch: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"Le interviste batch sono fallite: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """
    Intervista globale: intervista tutti gli agenti utilizzando le stesse domande

    Nota: questa funzionalità richiede che l'ambiente di simulazione sia in esecuzione

    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",            // Obbligatorio, simulaID
            "prompt": "Qual è la tua opinione generale su questo argomento?？",  // Obbligatorio, domande dell'intervista (tutti gli agenti utilizzano le stesse domande）
            "platform": "reddit",                   // Facoltativo, specificare la piattaforma (twitter/reddit)
                                                    // Quando non specificato: la simulazione doppia piattaforma consente a ciascun Agente di intervistare due piattaforme contemporaneamente
            "timeout": 180                          // Facoltativo, timeout (secondi), predefinito180
        }

    Ritorno：
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # Facoltativo：twitter/reddit/None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "Si prega di fornire una richiesta (domanda per l'intervista）"
            }), 400

        # Verificare i parametri della piattaforma
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform I parametri possono solo essere 'twitter' o 'reddit'"
            }), 400

        # Controlla lo stato dell'ambiente
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "L'ambiente di simulazione non è in esecuzione o è spento. Assicurati che la simulazione sia stata completata e che sia attivata la modalità di attesa comando。"
            }), 400

        # Ottimizza le richieste e aggiungi prefissi per evitare che l'agente chiami gli strumenti
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Timeout in attesa della risposta al colloquio globale: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"Intervista globale fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """
    Ottieni la cronologia delle interviste

    Leggi tutti i record delle interviste dal database fittizio

    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",  // Obbligatorio, simulaID
            "platform": "reddit",          // Facoltativo, tipo di piattaforma (reddit/twitter)
                                           // Se non specificato, verrà restituita tutta la cronologia delle due piattaforme.
            "agent_id": 0,                 // Facoltativo, ottenere solo la cronologia dei colloqui dell'agente
            "limit": 100                   // Facoltativo, quantità restituita, impostazione predefinita100
        }

    Ritorno：
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "Penso...",
                        "prompt": "cosa ne pensi di questa faccenda?？",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        platform = data.get('platform')  # Se non specificato verrà restituita la cronologia delle due piattaforme.
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(f"Impossibile ottenere la cronologia delle interviste: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """
    Ottieni lo stato dell'ambiente di simulazione

    Controlla se l'ambiente di simulazione è attivo (può ricevere il comando Intervista)

    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx"  // Obbligatorio, simulaID
        }

    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "L'ambiente è in esecuzione e può ricevere comandi Intervista"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)
        
        # Ottieni informazioni sullo stato più dettagliate
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "L'ambiente è in esecuzione e può ricevere comandi Intervista"
        else:
            message = "L'ambiente non funziona o è inattivo"

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message
            }
        })

    except Exception as e:
        logger.error(f"Impossibile ottenere lo stato dell'ambiente: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """
    Chiudi l'ambiente di simulazione
    
    Invia un comando di spegnimento dell'ambiente alla simulazione per uscire con garbo dalla modalità di attesa del comando.
    
    Nota: questa è diversa dall'interfaccia /stop, che terminerà forzatamente il processo.
    Questa interfaccia consentirà alla simulazione di chiudere con garbo l'ambiente e uscire.
    
    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",  // Obbligatorio, simulaID
            "timeout": 30                  // Facoltativo, timeout (secondi), predefinito30
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "message": "Comando di arresto dell'ambiente inviato",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        timeout = data.get('timeout', 30)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        # Aggiorna lo stato della simulazione
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Impossibile arrestare l'ambiente: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
