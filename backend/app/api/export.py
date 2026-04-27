"""
API di esportazione completa
Endpoint per esportare progetti in ZIP offline
"""

import traceback
from flask import request, jsonify, send_file
from . import export_bp
from ..services.export_service import ExportService
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.export')


@export_bp.route('/package', methods=['POST'])
def export_package():
    """
    Esporta un pacchetto completo (ZIP offline)
    
    Richiesta (JSON):
        {
            "project_id": "proj_xxxx",          // Obbligatorio
            "simulation_id": "sim_xxxx",        // Opzionale
            "report_id": "report_xxxx"          // Opzionale
        }
    
    Ritorno:
        File ZIP con estensione .zip
    """
    try:
        data = request.get_json() or {}
        project_id = data.get('project_id')
        simulation_id = data.get('simulation_id')
        report_id = data.get('report_id')
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "project_id obbligatorio"
            }), 400
        
        logger.info(f"Inizio esportazione: proj={project_id}, sim={simulation_id}, rep={report_id}")
        
        # Crea il pacchetto
        zip_buffer = ExportService.create_export_package(
            project_id=project_id,
            simulation_id=simulation_id,
            report_id=report_id
        )
        
        # Genera nome file
        filename = f"CivesAI_Export_{project_id}.zip"
        
        logger.info(f"Esportazione completata: {filename}")
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
        
    except ValueError as e:
        logger.warning(f"Errore validazione: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
    except Exception as e:
        logger.error(f"Errore esportazione: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Errore durante l'esportazione: {str(e)}"
        }), 500


@export_bp.route('/status', methods=['POST'])
def export_status():
    """
    Verifica se i dati necessari per l'esportazione sono disponibili
    
    Richiesta (JSON):
        {
            "project_id": "proj_xxxx",
            "simulation_id": "sim_xxxx",        // Opzionale
            "report_id": "report_xxxx"          // Opzionale
        }
    
    Ritorno:
        {
            "success": true,
            "data": {
                "project_available": true,
                "ontology_available": true,
                "simulation_available": false,
                "report_available": false
            }
        }
    """
    try:
        data = request.get_json() or {}
        project_id = data.get('project_id')
        simulation_id = data.get('simulation_id')
        report_id = data.get('report_id')
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "project_id obbligatorio"
            }), 400
        
        from ..models.project import ProjectManager
        from ..config import Config
        import os
        
        project = ProjectManager.get_project(project_id)
        
        status = {
            "project_available": project is not None,
            "ontology_available": project is not None and project.ontology is not None,
            "simulation_available": False,
            "report_available": False
        }
        
        if simulation_id:
            sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
            status["simulation_available"] = os.path.exists(sim_dir)
        
        if report_id:
            report_dir = os.path.join(Config.UPLOAD_FOLDER, 'reports', report_id)
            status["report_available"] = os.path.exists(report_dir)
        
        return jsonify({
            "success": True,
            "data": status
        })
        
    except Exception as e:
        logger.error(f"Errore verifica status: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
