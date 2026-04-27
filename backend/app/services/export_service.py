"""
Servizio di esportazione completo
Esporta progetti completi in PDF + ZIP con tutti i dati, prompts, reality seed, ecc.
"""

import os
import json
import zipfile
import shutil
from io import BytesIO
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..utils.logger import get_logger
from ..models.project import ProjectManager
from .report_agent import ReportLogger

logger = get_logger('mirofish.export')


class ExportService:
    """Servizio di esportazione con supporto offline completo"""
    
    @staticmethod
    def _read_json_file(filepath: str) -> Optional[Dict[str, Any]]:
        """Leggi un file JSON in modo sicuro"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Errore lettura {filepath}: {e}")
        return None
    
    @staticmethod
    def _read_text_file(filepath: str) -> Optional[str]:
        """Leggi un file di testo in modo sicuro"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            logger.warning(f"Errore lettura {filepath}: {e}")
        return None
    
    @staticmethod
    def _collect_project_data(project_id: str) -> Dict[str, Any]:
        """Raccoglie tutti i dati del progetto"""
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"Progetto non trovato: {project_id}")
        
        project_dir = os.path.join(Config.UPLOAD_FOLDER, 'projects', project_id)
        data = {
            'project': project.to_dict(),
            'extracted_text': ExportService._read_text_file(
                os.path.join(project_dir, 'extracted_text.txt')
            ),
            'files': []
        }
        
        # Elenco dei file allegati
        files_dir = os.path.join(project_dir, 'files')
        if os.path.exists(files_dir):
            for filename in os.listdir(files_dir):
                filepath = os.path.join(files_dir, filename)
                if os.path.isfile(filepath):
                    data['files'].append({
                        'filename': filename,
                        'size': os.path.getsize(filepath)
                    })
        
        return data
    
    @staticmethod
    def _collect_simulation_data(simulation_id: str) -> Dict[str, Any]:
        """Raccoglie tutti i dati della simulazione"""
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            logger.warning(f"Cartella simulazione non trovata: {sim_dir}")
            return {}
        
        data = {}
        
        # File JSON principali
        for json_file in ['simulation_config.json', 'state.json', 'run_state.json', 'env_status.json']:
            filepath = os.path.join(sim_dir, json_file)
            content = ExportService._read_json_file(filepath)
            if content:
                data[json_file] = content
        
        # Profili personas
        for profiles_file in ['twitter_profiles.csv', 'reddit_profiles.json']:
            filepath = os.path.join(sim_dir, profiles_file)
            if os.path.exists(filepath):
                try:
                    if profiles_file.endswith('.csv'):
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data['twitter_profiles'] = f.read()
                    else:
                        data['reddit_profiles'] = ExportService._read_json_file(filepath)
                except Exception as e:
                    logger.warning(f"Errore lettura {profiles_file}: {e}")
        
        return data
    
    @staticmethod
    def _collect_report_data(report_id: str) -> Dict[str, Any]:
        """Raccoglie tutti i dati del report"""
        report_dir = os.path.join(Config.UPLOAD_FOLDER, 'reports', report_id)
        
        if not os.path.exists(report_dir):
            logger.warning(f"Cartella report non trovata: {report_dir}")
            return {}
        
        data = {}
        
        # File JSON e Markdown
        for filename in os.listdir(report_dir):
            filepath = os.path.join(report_dir, filename)
            if os.path.isfile(filepath):
                if filename.endswith('.json'):
                    content = ExportService._read_json_file(filepath)
                    if content:
                        data[filename] = content
                elif filename.endswith('.md'):
                    content = ExportService._read_text_file(filepath)
                    if content:
                        data[filename] = content
                elif filename == 'agent_log.jsonl':
                    # Leggi il JSONL come array di oggetti
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data['agent_log'] = [json.loads(line) for line in f if line.strip()]
                    except Exception as e:
                        logger.warning(f"Errore lettura agent_log.jsonl: {e}")
        
        return data
    
    @staticmethod
    def _collect_system_prompts() -> Dict[str, str]:
        """Raccoglie tutti i system prompts del sistema"""
        prompts = {}
        
        # Ontology prompt
        try:
            from .ontology_generator import ONTOLOGY_SYSTEM_PROMPT
            prompts['ontology_generation'] = ONTOLOGY_SYSTEM_PROMPT
        except Exception as e:
            logger.warning(f"Errore raccolta ontology prompt: {e}")
        
        # Report prompts
        try:
            from .report_agent import ReportAgent
            # Nota: questi sono definiti nel metodo, quindi documentarli a parte
            prompts['report_generation'] = "Vedi report_agent.py per i prompts di generazione"
        except Exception as e:
            logger.warning(f"Errore raccolta report prompts: {e}")
        
        # Simulation config prompts
        try:
            from .simulation_config_generator import SimulationConfigGenerator
            prompts['simulation_config'] = "Vedi simulation_config_generator.py per i prompts di configurazione"
        except Exception as e:
            logger.warning(f"Errore raccolta simulation prompts: {e}")
        
        return prompts
    
    @staticmethod
    def create_export_package(
        project_id: str,
        simulation_id: Optional[str] = None,
        report_id: Optional[str] = None
    ) -> BytesIO:
        """
        Crea un archivio ZIP completo offline
        
        Args:
            project_id: ID del progetto
            simulation_id: ID della simulazione (opzionale)
            report_id: ID del report (opzionale)
            
        Returns:
            BytesIO contenente l'archivio ZIP
        """
        logger.info(f"Inizio esportazione: progetto={project_id}, sim={simulation_id}, report={report_id}")
        
        zip_buffer = BytesIO()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                
                # === PROGETTO ===
                logger.debug("Raccogliendo dati del progetto...")
                project_data = ExportService._collect_project_data(project_id)
                zf.writestr('PROJECT/project.json', json.dumps(
                    project_data['project'], ensure_ascii=False, indent=2
                ))
                
                if project_data['extracted_text']:
                    zf.writestr('PROJECT/extracted_text.txt', project_data['extracted_text'])
                
                zf.writestr('PROJECT/files_manifest.json', json.dumps(
                    project_data['files'], ensure_ascii=False, indent=2
                ))
                
                # Copia i file allegati
                project_dir = os.path.join(Config.UPLOAD_FOLDER, 'projects', project_id)
                files_dir = os.path.join(project_dir, 'files')
                if os.path.exists(files_dir):
                    for filename in os.listdir(files_dir):
                        src = os.path.join(files_dir, filename)
                        if os.path.isfile(src):
                            with open(src, 'rb') as f:
                                zf.writestr(f'PROJECT/files/{filename}', f.read())
                
                # === ONTOLOGIA ===
                logger.debug("Raccogliendo dati dell'ontologia...")
                if project_data['project'].get('ontology'):
                    zf.writestr('ONTOLOGY/ontology.json', json.dumps(
                        project_data['project']['ontology'], ensure_ascii=False, indent=2
                    ))
                
                # === SIMULAZIONE ===
                if simulation_id:
                    logger.debug(f"Raccogliendo dati della simulazione {simulation_id}...")
                    sim_data = ExportService._collect_simulation_data(simulation_id)
                    
                    for key, value in sim_data.items():
                        if isinstance(value, dict):
                            zf.writestr(f'SIMULATION/{key}', json.dumps(
                                value, ensure_ascii=False, indent=2
                            ))
                        elif isinstance(value, str):
                            zf.writestr(f'SIMULATION/{key}', value)
                
                # === REPORT ===
                if report_id:
                    logger.debug(f"Raccogliendo dati del report {report_id}...")
                    report_data = ExportService._collect_report_data(report_id)
                    
                    for key, value in report_data.items():
                        if isinstance(value, dict):
                            zf.writestr(f'REPORT/{key}', json.dumps(
                                value, ensure_ascii=False, indent=2
                            ))
                        elif isinstance(value, list):
                            zf.writestr(f'REPORT/{key}.json', json.dumps(
                                value, ensure_ascii=False, indent=2
                            ))
                        elif isinstance(value, str):
                            zf.writestr(f'REPORT/{key}', value)
                
                # === SYSTEM PROMPTS ===
                logger.debug("Raccogliendo system prompts...")
                prompts = ExportService._collect_system_prompts()
                zf.writestr('SYSTEM_PROMPTS/prompts.json', json.dumps(
                    prompts, ensure_ascii=False, indent=2
                ))
                
                # === README ===
                readme_content = ExportService._generate_readme(
                    project_id, simulation_id, report_id
                )
                zf.writestr('README.md', readme_content)
                
                # === MANIFEST ===
                manifest = {
                    'export_timestamp': timestamp,
                    'export_version': '1.0',
                    'project_id': project_id,
                    'simulation_id': simulation_id,
                    'report_id': report_id,
                    'contents': {
                        'project': True,
                        'ontology': bool(project_data['project'].get('ontology')),
                        'simulation': bool(simulation_id),
                        'report': bool(report_id),
                        'system_prompts': bool(prompts)
                    }
                }
                zf.writestr('manifest.json', json.dumps(
                    manifest, ensure_ascii=False, indent=2
                ))
            
            zip_buffer.seek(0)
            logger.info(f"Esportazione completata: {timestamp}")
            return zip_buffer
            
        except Exception as e:
            logger.error(f"Errore durante l'esportazione: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _generate_readme(
        project_id: str,
        simulation_id: Optional[str],
        report_id: Optional[str]
    ) -> str:
        """Genera il README per l'archivio di esportazione"""
        
        readme = f"""# CivesAI Export - {project_id}

## Contenuto dell'archivio

Questo archivio contiene un'esportazione completa e offline del tuo progetto CivesAI.

### Struttura

#### PROJECT/
- `project.json` - Metadati del progetto, configurazione, stato
- `extracted_text.txt` - Testo estratto dai documenti caricati
- `files_manifest.json` - Elenco dei file allegati
- `files/` - Copie dei documenti originali

#### ONTOLOGY/
- `ontology.json` - L'ontologia generata con entità e relazioni
  - Entity types: Tipi di entità definiti
  - Relationship types: Tipi di relazioni tra entità

#### SIMULATION/
*Presente solo se è stata eseguita una simulazione*
- `simulation_config.json` - Configurazione completa della simulazione
- `state.json` - Stato finale della simulazione
- `run_state.json` - Timeline dell'esecuzione
- `twitter_profiles.csv` - Personas generate per Twitter
- `reddit_profiles.json` - Personas generate per Reddit
- `env_status.json` - Stato dell'ambiente durante l'esecuzione

**Reality Seed**: Il calibration_profile è contenuto in simulation_config.json

#### REPORT/
*Presente solo se è stato generato un report*
- `full_report.md` - Report completo in Markdown
- `outline.json` - Struttura e outline del report
- `meta.json` - Metadati del report
- `section_*.md` - Sezioni individuali del report
- `agent_log.json` - Timeline completa delle azioni degli agenti
  - Ogni riga contiene: timestamp, action, stage, details
  - Utile per ripercorrere il processo di generazione

#### SYSTEM_PROMPTS/
- `prompts.json` - Tutti i system prompts utilizzati durante la generazione
  - Ontology generation
  - Report generation
  - Simulation configuration
  - Agent interaction

#### manifest.json
Manifesto dell'esportazione con:
- Data e versione dell'export
- IDs del progetto/simulazione/report
- Contenuti inclusi nell'archivio

## Come usare questi dati

### Riapplicare il progetto
1. Estrai il contenuto di PROJECT/
2. Usa project.json per ricaricare lo stato nel sistema

### Analizzare l'ontologia
- Apri ONTOLOGY/ontology.json in un JSON viewer
- Analizza entity_types e relationship_types

### Riesaminare la simulazione
- Leggi SIMULATION/simulation_config.json per vedere la configurazione
- Consulta SIMULATION/state.json per i risultati finali
- Usa i CSV/JSON delle personas per ricaricare gli agenti

### Riprodurre il report
- Consulta REPORT/agent_log.json per la timeline completa
- Leggi il full_report.md per il risultato finale
- Analizza SYSTEM_PROMPTS/prompts.json per i dettagli dei prompts

## Compatibilità offline
Questo archivio è completamente offline e autosufficiente.
Puoi:
- Analizzare i dati JSON in qualsiasi JSON viewer
- Leggere il Markdown con qualsiasi editor di testo
- Importare i dati in un'altra istanza di CivesAI
- Archiviare per audit trail e riproduzione

---
Esportato il: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        return readme
