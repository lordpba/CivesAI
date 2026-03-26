"""
Report APIinstradamento
Fornire la generazione di report di simulazione、Ottieni、Dialogo e altre interfacce
"""

import os
import traceback
import threading
from flask import request, jsonify, send_file

from . import report_bp
from ..config import Config
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.report')


# ============== Interfaccia di generazione dei report ==============

@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    Genera report di analisi della simulazione (attività asincrona)
    
    Questa è un'operazione che richiede tempo e l'interfaccia tornerà immediatamentetask_id，
    Utilizzare GET /api/report/generate/status per interrogare lo stato di avanzamento
    
    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",    // Obbligatorio, simulaID
            "force_regenerate": false        // Facoltativo, forzare una rigenerazione
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",
                "status": "generating",
                "message": "Attività di generazione del report avviata"
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
        
        force_regenerate = data.get('force_regenerate', False)
        
        # Ottieni informazioni sulla simulazione
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404
        
        # Controlla se c'è già una segnalazione
        if not force_regenerate:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "message": "Il rapporto esiste già",
                        "already_generated": True
                    }
                })
        
        # Ottieni informazioni sul progetto
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Il progetto non esiste: {state.project_id}"
            }), 404
        
        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Manca l'ID mappa, assicurati di aver creato la mappa"
            }), 400
        
        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Descrizione dei requisiti di simulazione mancante"
            }), 400
        
        # Generare in anticipo report_id，in modo che possa essere restituito immediatamente al front-end
        import uuid
        report_id = f"report_{uuid.uuid4().hex[:12]}"
        
        # Creare un'attività asincrona
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "report_id": report_id
            }
        )
        
        # Definire le attività in background
        def run_generate():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="inizializzazioneReport Agent..."
                )
                
                # CreaReport Agent
                agent = ReportAgent(
                    graph_id=graph_id,
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement
                )
                
                # Richiamata di avanzamento
                def progress_callback(stage, progress, message):
                    task_manager.update_task(
                        task_id,
                        progress=progress,
                        message=f"[{stage}] {message}"
                    )
                
                # Generare un report (passando un file pre-generato report_id）
                report = agent.generate_report(
                    progress_callback=progress_callback,
                    report_id=report_id
                )
                
                # salva rapporto
                ReportManager.save_report(report)
                
                if report.status == ReportStatus.COMPLETED:
                    task_manager.complete_task(
                        task_id,
                        result={
                            "report_id": report.report_id,
                            "simulation_id": simulation_id,
                            "status": "completed"
                        }
                    )
                else:
                    task_manager.fail_task(task_id, report.error or "La generazione del rapporto non è riuscita")
                
            except Exception as e:
                logger.error(f"La generazione del rapporto non è riuscita: {str(e)}")
                task_manager.fail_task(task_id, str(e))
        
        # Avvia il thread in background
        thread = threading.Thread(target=run_generate, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_id": report_id,
                "task_id": task_id,
                "status": "generating",
                "message": "L'attività di generazione del report è stata avviata, controlla l'avanzamento tramite /api/report/generate/status",
                "already_generated": False
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile avviare l'attività di generazione del report: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/generate/status', methods=['POST'])
def get_generate_status():
    """
    Avanzamento dell'attività di generazione del report delle query
    
    Richiesta（JSON）：
        {
            "task_id": "task_xxxx",         // Facoltativo, restituito da generatetask_id
            "simulation_id": "sim_xxxx"     // Facoltativo, simulaID
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|failed",
                "progress": 45,
                "message": "..."
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # se fornitosimulation_id，Per prima cosa controlla se esiste già un report completato
        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "progress": 100,
                        "message": "Rapporto generato",
                        "already_completed": True
                    }
                })
        
        if not task_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci task_id o simulation_id"
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            return jsonify({
                "success": False,
                "error": f"L'attività non esiste: {task_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": task.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Impossibile interrogare lo stato dell'attività: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== Interfaccia di acquisizione dei report ==============

@report_bp.route('/<report_id>', methods=['GET'])
def get_report(report_id: str):
    """
    Ottieni i dettagli del rapporto
    
    Ritorno：
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "simulation_id": "sim_xxxx",
                "status": "completed",
                "outline": {...},
                "markdown_content": "...",
                "created_at": "...",
                "completed_at": "..."
            }
        }
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": f"Il rapporto non esiste: {report_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": report.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il rapporto: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    """
    Ottieni report basati sull'ID di rappresentazione
    
    Ritorno：
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                ...
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": f"Non c'è ancora alcun rapporto per questa simulazione: {simulation_id}",
                "has_report": False
            }), 404
        
        return jsonify({
            "success": True,
            "data": report.to_dict(),
            "has_report": True
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il rapporto: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """
    elenca tutti i rapporti
    
    Parametri di query：
        simulation_id: Filtra per ID di rappresentazione (facoltativo）
        limit: Limite quantità reso (predefinito 50)
    
    Ritorno：
        {
            "success": true,
            "data": [...],
            "count": 10
        }
    """
    try:
        simulation_id = request.args.get('simulation_id')
        limit = request.args.get('limit', 50, type=int)
        
        reports = ReportManager.list_reports(
            simulation_id=simulation_id,
            limit=limit
        )
        
        return jsonify({
            "success": True,
            "data": [r.to_dict() for r in reports],
            "count": len(reports)
        })
        
    except Exception as e:
        logger.error(f"I rapporti sull'elenco non sono riusciti: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    """
    Scarica il rapporto (formato Markdown)
    
    Ritorna al file Markdown
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": f"Il rapporto non esiste: {report_id}"
            }), 404
        
        md_path = ReportManager._get_report_markdown_path(report_id)
        
        if not os.path.exists(md_path):
            # Se il file MD non esiste, generare un file temporaneo
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(report.markdown_content)
                temp_path = f.name
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"{report_id}.md"
            )
        
        return send_file(
            md_path,
            as_attachment=True,
            download_name=f"{report_id}.md"
        )
        
    except Exception as e:
        logger.error(f"Download del rapporto non riuscito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>', methods=['DELETE'])
def delete_report(report_id: str):
    """Elimina rapporto"""
    try:
        success = ReportManager.delete_report(report_id)
        
        if not success:
            return jsonify({
                "success": False,
                "error": f"Il rapporto non esiste: {report_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "message": f"Rapporto eliminato: {report_id}"
        })
        
    except Exception as e:
        logger.error(f"Eliminazione del rapporto non riuscita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Report Agentinterfaccia conversazionale ==============

@report_bp.route('/chat', methods=['POST'])
def chat_with_report_agent():
    """
    Parla con l'agente di segnalazione
    
    Report Agent può chiamare autonomamente gli strumenti di ricerca per rispondere alle domande durante la conversazione
    
    Richiesta（JSON）：
        {
            "simulation_id": "sim_xxxx",        // Obbligatorio, simulaID
            "message": "Si prega di spiegare l'andamento dell'opinione pubblica",    // Obbligatorio, messaggio utente
            "chat_history": [                   // Facoltativo, cronologia delle conversazioni
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }
    
    Ritorno：
        {
            "success": true,
            "data": {
                "response": "AgentRispondi...",
                "tool_calls": [Elenco degli strumenti chiamati],
                "sources": [Fonte di informazioni]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        message = data.get('message')
        chat_history = data.get('chat_history', [])
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "per favore fornisci simulation_id"
            }), 400
        
        if not message:
            return jsonify({
                "success": False,
                "error": "per favore fornisci message"
            }), 400
        
        # Ottieni informazioni sulla simulazione e sul progetto
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404
        
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Il progetto non esiste: {state.project_id}"
            }), 404
        
        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "mappa mancanteID"
            }), 400
        
        simulation_requirement = project.simulation_requirement or ""
        
        # Crea un agente e avvia una conversazione
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement
        )
        
        result = agent.chat(message=message, chat_history=chat_history)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"La conversazione non è riuscita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Segnala i progressi e l'interfaccia del capitolo ==============

@report_bp.route('/<report_id>/progress', methods=['GET'])
def get_report_progress(report_id: str):
    """
    Ottieni l'avanzamento della generazione del report (in tempo reale)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "status": "generating",
                "progress": 45,
                "message": "Generazione di capitoli: Risultati chiave",
                "current_section": "Risultati chiave",
                "completed_sections": ["sintesi esecutiva", "Sfondo analogico"],
                "updated_at": "2025-12-09T..."
            }
        }
    """
    try:
        progress = ReportManager.get_progress(report_id)
        
        if not progress:
            return jsonify({
                "success": False,
                "error": f"Il report non esiste oppure le informazioni sullo stato di avanzamento non sono disponibili: {report_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": progress
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere lo stato di avanzamento del rapporto: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/sections', methods=['GET'])
def get_report_sections(report_id: str):
    """
    Ottieni l'elenco dei capitoli generato (output in capitoli)
    
    Il front-end può eseguire il polling di questa interfaccia per ottenere il contenuto del capitolo generato senza attendere il completamento dell'intero report.
    
    Ritorno：
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "sections": [
                    {
                        "filename": "section_01.md",
                        "section_index": 1,
                        "content": "## sintesi esecutiva\\n\\n..."
                    },
                    ...
                ],
                "total_sections": 3,
                "is_complete": false
            }
        }
    """
    try:
        sections = ReportManager.get_generated_sections(report_id)
        
        # Ottieni lo stato del rapporto
        report = ReportManager.get_report(report_id)
        is_complete = report is not None and report.status == ReportStatus.COMPLETED
        
        return jsonify({
            "success": True,
            "data": {
                "report_id": report_id,
                "sections": sections,
                "total_sections": len(sections),
                "is_complete": is_complete
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere l'elenco dei capitoli: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/section/<int:section_index>', methods=['GET'])
def get_single_section(report_id: str, section_index: int):
    """
    Ottieni il contenuto di un singolo capitolo
    
    Ritorno：
        {
            "success": true,
            "data": {
                "filename": "section_01.md",
                "content": "## sintesi esecutiva\\n\\n..."
            }
        }
    """
    try:
        section_path = ReportManager._get_section_path(report_id, section_index)
        
        if not os.path.exists(section_path):
            return jsonify({
                "success": False,
                "error": f"Il capitolo non esiste: section_{section_index:02d}.md"
            }), 404
        
        with open(section_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            "success": True,
            "data": {
                "filename": f"section_{section_index:02d}.md",
                "section_index": section_index,
                "content": content
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il contenuto del capitolo: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia di controllo dello stato del report ==============

@report_bp.route('/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    """
    Controlla se la simulazione ha rapporti e lo stato dei rapporti
    
    Utilizzato dal front-end per determinare se sbloccare la funzione Intervista
    
    Ritorno：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "has_report": true,
                "report_status": "completed",
                "report_id": "report_xxxx",
                "interview_unlocked": true
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        
        has_report = report is not None
        report_status = report.status.value if report else None
        report_id = report.report_id if report else None
        
        # Sbloccato solo dopo il completamento del rapportointerview
        interview_unlocked = has_report and report.status == ReportStatus.COMPLETED
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "has_report": has_report,
                "report_status": report_status,
                "report_id": report_id,
                "interview_unlocked": interview_unlocked
            }
        })
        
    except Exception as e:
        logger.error(f"Controllare lo stato del rapporto non riuscito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Agent Interfaccia di registro ==============

@report_bp.route('/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    """
    Ottieni log di esecuzione dettagliati di Report Agent
    
    Ottieni accesso in tempo reale a ogni fase del processo di generazione del report, tra cui:
    - Il rapporto viene avviato、Pianificazione inizio/fine
    - Inizio di ogni capitolo、Chiamata allo strumento、LLMrisposta、Completo
    - Segnala il completamento o il fallimento
    
    Parametri di query：
        from_line: Da quale riga iniziare la lettura (facoltativo, predefinito 0, utilizzato per l'acquisizione incrementale)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "timestamp": "2025-12-13T...",
                        "elapsed_seconds": 12.5,
                        "report_id": "report_xxxx",
                        "action": "tool_call",
                        "stage": "generating",
                        "section_title": "sintesi esecutiva",
                        "section_index": 1,
                        "details": {
                            "tool_name": "insight_forge",
                            "parameters": {...},
                            ...
                        }
                    },
                    ...
                ],
                "total_lines": 25,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il registro dell'agente: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/agent-log/stream', methods=['GET'])
def stream_agent_log(report_id: str):
    """
    Ottieni il registro completo dell'agente (ottieni tutto in una volta)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 25
            }
        }
    """
    try:
        logs = ReportManager.get_agent_log_stream(report_id)
        
        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il registro dell'agente: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia di registro della console ==============

@report_bp.route('/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    """
    Ottieni il registro di output della console dell'agente report
    
    Ottieni l'output della console durante la generazione del report in tempo reale（INFO、WARNINGecc.),
    Questo è diverso dal log JSON strutturato restituito dall'interfaccia del log dell'agente.
    È un registro in stile console in formato testo normale.
    
    Parametri di query：
        from_line: Da quale riga iniziare la lettura (facoltativo, predefinito 0, utilizzato per l'acquisizione incrementale)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "logs": [
                    "[19:46:14] INFO: Ricerca completata: Trovato 15 fatti rilevanti",
                    "[19:46:14] INFO: Ricerca grafica: graph_id=xxx, query=...",
                    ...
                ],
                "total_lines": 100,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_console_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il registro della console: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/console-log/stream', methods=['GET'])
def stream_console_log(report_id: str):
    """
    Ottieni il registro completo della console (ottienilo tutto in una volta)
    
    Ritorno：
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 100
            }
        }
    """
    try:
        logs = ReportManager.get_console_log_stream(report_id)
        
        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere il registro della console: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia di chiamata dello strumento (per l'uso del debug）==============

@report_bp.route('/tools/search', methods=['POST'])
def search_graph_tool():
    """
    Interfaccia dello strumento di ricerca grafico (per il debug)
    
    Richiesta（JSON）：
        {
            "graph_id": "mirofish_xxxx",
            "query": "query di ricerca",
            "limit": 10
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        query = data.get('query')
        limit = data.get('limit', 10)
        
        if not graph_id or not query:
            return jsonify({
                "success": False,
                "error": "per favore fornisci graph_id e query"
            }), 400
        
        from ..services.zep_tools import ZepToolsService
        
        tools = ZepToolsService()
        result = tools.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"La ricerca nel grafico non è riuscita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/tools/statistics', methods=['POST'])
def get_graph_statistics_tool():
    """
    Interfaccia dello strumento statistiche grafico (per uso di debug）
    
    Richiesta（JSON）：
        {
            "graph_id": "mirofish_xxxx"
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
        
        from ..services.zep_tools import ZepToolsService
        
        tools = ZepToolsService()
        result = tools.get_graph_statistics(graph_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Impossibile ottenere le statistiche del grafico: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
