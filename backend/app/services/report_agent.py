"""
Report Agentservizio
Utilizzo di LangChain + Zep per implementare la generazione di report di simulazione in modalità ReACT

Funzione：
1. Genera report basati sui requisiti di simulazione e sulle informazioni della mappa Zep
2. Pianificare prima la struttura della directory, quindi generarla in segmenti
3. Ogni paragrafo adotta la modalità di pensiero e riflessione multipla di ReACT
4. Supportare il dialogo con gli utenti e richiamare autonomamente gli strumenti di ricerca durante il dialogo
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Report Agent Registratore dettagliato
    
    Genera nella cartella del report agent_log.jsonl Archivia, registra ogni azione dettagliata.
    Ogni riga è un oggetto JSON completo contenente un timestamp、tipo di azione、Dettagli, ecc.。
    """
    
    def __init__(self, report_id: str):
        """
        Inizializza il registratore
        
        Args:
            report_id: ID report, utilizzato per determinare il percorso del file di registro
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Assicurarsi che la directory in cui si trova il file di registro esista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Ottieni il tempo trascorso dall'inizio a adesso (secondi）"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        registrare un registro
        
        Args:
            action: Tipo di azione, ad esempio 'start', 'tool_call', 'llm_response', 'section_complete' Aspetta
            stage: fase attuale, come ad es 'planning', 'generating', 'completed'
            details: Dizionario dei contenuti dettagliato, senza troncamento
            section_title: Titolo del capitolo corrente (facoltativo）
            section_index: Indice del capitolo corrente (facoltativo）
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Aggiungi la scrittura al file JSONL
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Inizia la generazione del report di registrazione"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Viene avviata l'attività di generazione del report"
            }
        )
    
    def log_planning_start(self):
        """Inizia la pianificazione della struttura della registrazione"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Inizia a pianificare la struttura del tuo rapporto"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Registrare le informazioni contestuali ottenute durante la pianificazione"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Ottieni informazioni sul contesto della simulazione",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Pianificazione della struttura del record completata"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Pianificazione generale completata",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Viene avviata la generazione dei capitoli della registrazione"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Inizia a generare capitoli: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Documenta il tuo processo di pensiero ReACT"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT No.{iteration}giro di pensieri"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Registrazione delle chiamate allo strumento"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Strumento di chiamata: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Registra i risultati delle chiamate allo strumento (contenuto completo, non troncato)）"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Risultato completo, nessun troncamento
                "result_length": len(result),
                "message": f"Strumenti {tool_name} Restituisci risultati"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Registrazione della risposta LLM (contenuto completo, non troncato）"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Risposta completa, nessun troncamento
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM risposta (Chiamata allo strumento: {has_tool_calls}, risposta finale: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Registra la generazione del contenuto del capitolo è completata (registra solo il contenuto, non significa che l'intero capitolo è completato）"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Contenuto completo, senza troncamenti
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Capitolo {section_title} Generazione del contenuto completata"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Generazione del capitolo della registrazione completata

        Il front-end dovrebbe ascoltare questo registro per determinare se un capitolo è effettivamente completato e ottenere il contenuto completo
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Capitolo {section_title} Generazione completata"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Generazione del rapporto sui record completata"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Generazione del rapporto completata"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Errori di registro"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Si è verificato un errore: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent registratore di console
    
    Configura la registrazione dello stile della console（INFO、WARNINGecc.) scritto nella cartella del referto console_log.txt file.
    Questi registri sono correlati a agent_log.jsonl Diversamente, si tratta dell'output della console in formato testo normale.。
    """
    
    def __init__(self, report_id: str):
        """
        Inizializza il logger della console
        
        Args:
            report_id: ID report, utilizzato per determinare il percorso del file di registro
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Assicurarsi che la directory in cui si trova il file di registro esista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Configurare il file processore per scrivere i log sui file contemporaneamente"""
        import logging
        
        # Crea un gestore di file
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Utilizza lo stesso formato conciso della console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # aggiungere a report_agent rilevante logger
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Evitare aggiunte duplicate
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Chiudere il gestore file e rimuoverlo dal logger"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Assicurati di chiudere il gestore di file in caso di distruzione"""
        self.close()


class ReportStatus(str, Enum):
    """Segnala lo stato"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Capitolo Rapporto"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Converti nel formato Markdown"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Schema del rapporto"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Converti nel formato Markdown"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """rapporto completo"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt Costanti del modello
# ═══════════════════════════════════════════════════════════════

# ── Descrizione dello strumento ──

TOOL_DESC_INSIGHT_FORGE = """\
【Ricerca approfondita: potenti strumenti di ricerca】
Questa è la nostra potente funzione di ricerca, progettata per un'analisi approfondita. lo farà：
1. Suddivide automaticamente il problema in sottoproblemi
2. Recupera informazioni da mappe di simulazione in più dimensioni
3. Integra la ricerca semantica、analisi dell'entità、Risultati del monitoraggio della catena di relazioni
4. Ritorna al più completo、Il contenuto di ricerca più profondo

【Scenari di utilizzo】
- Necessità di analizzare un argomento in modo approfondito
- Necessità di comprendere molteplici aspetti dell'incidente
- Necessità di ottenere materiali ricchi a supporto dei capitoli del rapporto

【Restituisci contenuto】
- Testo originale dei fatti rilevanti (può essere citato direttamente)
- Approfondimenti sulle entità principali
-Analisi della catena delle relazioni"""

TOOL_DESC_PANORAMA_SEARCH = """\
【Ricerca in ampiezza: ottieni una visione d'insieme】
Questo strumento viene utilizzato per ottenere un quadro completo dei risultati della simulazione ed è particolarmente adatto per comprendere l'evoluzione degli eventi. lo farà：
1. Ottieni tutti i nodi e le relazioni rilevanti
2. Distinguere tra fatti attualmente validi e fatti storici/scaduti
3. Aiutarti a capire come si evolve l'opinione pubblica

【Scenari di utilizzo】
- È necessario comprendere lo sviluppo completo dell'incidente
- Necessità di confrontare i cambiamenti nell'opinione pubblica nelle diverse fasi
- Necessità di ottenere informazioni complete sull'entità e sulle relazioni

【Restituisci contenuto】
- Fatti attuali validi (simulare i risultati più recenti)
- Fatti storici/scaduti (record di evoluzione)
- Tutti gli enti coinvolti"""

TOOL_DESC_QUICK_SEARCH = """\
【Ricerca semplice: recupero rapido】
Strumento di ricerca rapida leggero, adatto alla ricerca semplice、richiesta di informazioni dirette。

【Scenari di utilizzo】
- Necessità di trovare rapidamente informazioni specifiche
- Necessità di verificare un fatto
- Recupero semplice delle informazioni

【Restituisci contenuto】
- Elenco dei fatti più rilevanti per la query"""

TOOL_DESC_INTERVIEW_AGENTS = """\
【Intervista approfondita - intervista con un agente reale (doppia piattaforma）】
Chiama l'API dell'intervista dell'ambiente di simulazione OASIS per condurre una vera intervista con l'agente di simulazione in esecuzione！
Questa non è una simulazione LLM, ma richiama l'interfaccia del colloquio reale per ottenere le risposte originali dell'agente simulato.
Per impostazione predefinita, le interviste verranno condotte simultaneamente sia su Twitter che su Reddit per ottenere una prospettiva più completa.

Flusso funzionale：
1. Leggi automaticamente i file dei personaggi e comprendi tutte le simulazioniAgent
2. Selezione intelligente degli agenti più rilevanti per l'argomento dell'intervista (come gli studenti、media、Ufficiale, ecc.）
3. Genera automaticamente domande per l'intervista
4. Chiama l'interfaccia /api/simulation/interview/batch per condurre interviste reali su doppia piattaforma
5. Integra tutti i risultati delle interviste per fornire un'analisi multi-prospettiva

【Scenari di utilizzo】
- Necessità di comprendere il punto di vista degli eventi da diverse prospettive di ruolo (cosa pensano gli studenti？Cosa ne pensano i media?？Cosa dice il funzionario?？）
- Necessità di raccogliere opinioni e posizioni da più parti
- Necessità di ottenere la risposta reale dell'Agente simulato (dall'ambiente di simulazione OASIS)
- Se vuoi rendere il resoconto più vivido, includilo"Trascrizione dell'intervista"

【Restituisci contenuto】
- Informazioni sull'identità dell'agente intervistato
- Risposte alle interviste di ciascun agente su Twitter e Reddit
- Citazioni chiave (possono essere citate direttamente)
- Sintesi delle interviste e confronti di punti di vista

【importante】Per utilizzare questa funzionalità è necessario che l'ambiente di simulazione OASIS sia in esecuzione！"""

# ── pianificazione di massima prompt ──

PLAN_SYSTEM_PROMPT = """\
sei un「Rapporto sulle previsioni future」esperto di scrittura con una conoscenza del mondo analogico「La prospettiva di Dio」——Puoi ottenere informazioni dettagliate sul comportamento di ogni agente nella simulazione、discorso e interazione。

【concetto fondamentale】
Abbiamo costruito un mondo simulato e gli abbiamo aggiunto elementi specifici「Requisiti di simulazione」come variabile. L'evoluzione del mondo simulato è una previsione di ciò che potrebbe accadere in futuro. Ciò che stai osservando non lo è"dati sperimentali"，Piuttosto"Anteprima del futuro"。

【il tuo compito】
scrivi un「Rapporto sulle previsioni future」，risposta：
1. Cosa accadrà in futuro nelle condizioni che stabiliamo？
2. Come reagiscono e agiscono i vari tipi di agenti (persone).？
3. Cosa rivela questa simulazione sulle tendenze future e sui rischi che vale la pena osservare？

【Segnalare il posizionamento】
- ✅ Questo è un rapporto sulle previsioni future basato sulla simulazione che rivela"Se sì, cosa accadrà in futuro?"
- ✅ Concentrarsi sulla previsione dei risultati: dove porteranno gli eventi、reazione di gruppo、fenomeno emergente、Rischi potenziali
- ✅ Le parole e le azioni dell'Agente nel mondo simulato sono previsioni del futuro comportamento della folla.
- ❌ Non un'analisi delle condizioni del mondo reale
- ❌ Questa non è una sintesi generale dell’opinione pubblica.

【Limite del numero di capitoli】
- Minimum 2 chapters, maximum 5 chapters
- Non sono necessari sottocapitoli, ogni capitolo scrive direttamente il contenuto completo
- Il contenuto dovrebbe essere perfezionato e focalizzato sulle previsioni e sui risultati principali
- La struttura del capitolo è progettata da te in base ai risultati della previsione

Si prega di produrre la struttura del report in formato JSON, il formato è il seguente：
{
    "title": "Titolo del rapporto",
    "summary": "Riepilogo del rapporto (una frase che riassume i risultati principali della previsione）",
    "sections": [
        {
            "title": "Titolo del capitolo",
            "description": "Descrizione del contenuto del capitolo"
        }
    ]
}

Nota: l'array delle sezioni ha un minimo di 2 e un massimo di 5 elementi.！"""

PLAN_USER_PROMPT_TEMPLATE = """\
【Impostazione scenari predittivi】
Le variabili che inseriamo nel mondo della simulazione (requisiti della simulazione）：{simulation_requirement}

【simulare la scala mondiale】
- Numero di entità che partecipano alla simulazione: {total_nodes}
- Il numero di relazioni generate tra le entità: {total_edges}
- Distribuzione del tipo di entità: {entity_types}
- Numero di agenti attivi: {total_entities}

【Esempi di alcuni dei fatti futuri previsti dalla simulazione】
{related_facts_json}

Per favore usa「La prospettiva di Dio」Dai un'occhiata a questa anteprima del futuro：
1. Come sarà il futuro nelle condizioni che poniamo?？
2. Come reagiscono e agiscono i vari gruppi di persone (Agenti).？
3. Cosa rivela questa simulazione sulle tendenze future che vale la pena osservare？

Progettare la struttura dei capitoli del report più appropriata in base ai risultati delle previsioni。

【promemoria di nuovo】Numero di capitoli del rapporto: minimo 2, massimo 5, il contenuto dovrebbe essere perfezionato e focalizzato sulle previsioni e sui risultati principali。"""

# ── Generazione del capitolo prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
sei un「Rapporto sulle previsioni future」l'esperto di scrittura sta scrivendo un capitolo di una relazione.

Titolo del rapporto: {report_title}
Riepilogo del rapporto: {report_summary}
Scenari di previsione (simulazione della domanda）: {simulation_requirement}

Capitolo attualmente in fase di scrittura: {section_title}

═══════════════════════════════════════════════════════════════
【concetto fondamentale】
═══════════════════════════════════════════════════════════════

Il mondo simulato è un'anteprima del futuro. Iniettiamo condizioni specifiche (requisiti di simulazione) nel mondo della simulazione,
Il comportamento e l'interazione degli agenti nella simulazione sono previsioni del comportamento futuro della folla.

Il tuo compito è:
- Rivelare cosa accadrà in futuro alle condizioni stabilite
- Prevedere come reagiranno e agiranno i vari tipi di persone (agenti).
- Scopri le tendenze future che vale la pena guardare、rischi e opportunità

❌ Non scriverlo come un’analisi delle condizioni del mondo reale
✅ su cui concentrarsi"cosa accadrà in futuro"——Il risultato della simulazione è il futuro previsto

═══════════════════════════════════════════════════════════════
【La regola più importante: deve essere seguita】
═══════════════════════════════════════════════════════════════

1. 【Lo Strumento di chiamata deve osservare il mondo della simulazione】
   - stai utilizzando「La prospettiva di Dio」Guarda un'anteprima del futuro
   - Tutti i contenuti devono provenire da eventi accaduti nel mondo simulato e dalle parole e dalle azioni dell'Agente
   - È vietato utilizzare le proprie conoscenze per scrivere il contenuto del rapporto
   - Richiama lo strumento almeno 3 volte per capitolo (massimo 5 volte) per osservare il mondo simulato, che rappresenta il futuro

2. 【Le parole e le azioni originali dell'Agente devono essere citate】
   - Agentil discorso e il comportamento sono previsioni del comportamento futuro della folla
   - Presentare queste previsioni nei rapporti utilizzando il formato citazione, ad es.：
     > "Un certo gruppo di persone dirà: contenuto originale..."
   - Queste citazioni sono prove fondamentali per le previsioni di simulazione

3. 【Coerenza linguistica: le citazioni devono essere tradotte nella lingua di riferimento】
   - Il contenuto restituito dallo strumento può contenere espressioni in inglese o un misto di cinese e inglese
   - Se il testo originale dei requisiti e dei materiali della simulazione è in cinese, il rapporto dovrà essere scritto interamente in cinese
   - Quando si citano contenuti misti in inglese o cinese-inglese restituiti dallo strumento, è necessario tradurli in cinese fluente prima di inserirli nel rapporto
   - Mantieni invariato il significato originale durante la traduzione per garantire un'espressione naturale e fluida
   - Questa regola si applica sia ai blocchi di testo che a quelli di virgolette（> formato)

4. 【Presenta fedelmente i risultati della previsione】
   - Il contenuto del report deve riflettere i risultati della simulazione che rappresentano il futuro in un mondo simulato
   - Non aggiungere informazioni che non esistono nella simulazione
   - Se non ci sono informazioni sufficienti su un certo aspetto, spiegalo in modo veritiero

═══════════════════════════════════════════════════════════════
【⚠️ Specifiche del formato: estremamente importanti！】
═══════════════════════════════════════════════════════════════

【un capitolo = Unità di contenuto minimo】
- Ogni capitolo è l'unità più piccola di reporting
- ❌ È vietato utilizzare titoli Markdown all'interno dei capitoli（#、##、###、#### Aspetta）
- ❌ È vietato aggiungere il titolo del capitolo principale all'inizio del contenuto
- ✅ I titoli dei capitoli vengono aggiunti automaticamente dal sistema e devi solo scrivere solo contenuto testuale
- ✅ Utilizzare **grassetto**、Separazione dei paragrafi、Citazione、Utilizza gli elenchi per organizzare i contenuti, ma non utilizzare i titoli

【Esempio corretto】
```
In questo capitolo si analizza l’andamento comunicativo dell’incidente all’opinione pubblica. Attraverso un'analisi approfondita dei dati simulati, lo abbiamo scoperto...

**Primo stadio di detonazione**

Come primo sito per l’opinione pubblica, Weibo assume la funzione principale della pubblicazione di informazioni.：

> "Weibo ha contribuito per il 68% ai primi tweet..."

**Stadio di amplificazione emotiva**

La piattaforma Douyin ha amplificato ulteriormente l’impatto dell’evento:

- Forte impatto visivo
- Alta risonanza emotiva
```

【Esempio di errore】
```
## sintesi esecutiva          ← Errore！non aggiungere alcun titolo
### uno、fase iniziale     ← Errore！Non utilizzare###diviso in sezioni
#### 1.1 Analisi dettagliata   ← Errore！Non utilizzare####Segmentazione

Questo capitolo analizza...
```

═══════════════════════════════════════════════════════════════
【Strumenti di ricerca disponibili】（Chiamato 3-5 volte per capitolo）
═══════════════════════════════════════════════════════════════

{tools_description}

【Consigli sull'utilizzo degli strumenti: utilizza un mix di strumenti diversi, non usarne solo uno】
- insight_forge: Analisi approfondita, scomposizione automatica dei problemi e recupero di fatti e relazioni in più dimensioni
- panorama_search: Ricerca panoramica grandangolare per comprendere l'intero evento、Cronologia ed evoluzione
- quick_search: Verifica rapidamente un punto informativo specifico
- interview_agents: Intervista agenti simulati per ottenere le prospettive in prima persona e le reazioni reali dei diversi personaggi

═══════════════════════════════════════════════════════════════
【Flusso di lavoro】
═══════════════════════════════════════════════════════════════

Puoi fare solo una delle seguenti due cose per ciascuna risposta (non contemporaneamente):

Opzione A - Chiama lo strumento:
Esprimi il tuo pensiero e poi chiama uno strumento utilizzando il seguente formato：
<tool_call>
{{"name": "Nome dello strumento", "parameters": {{"Nome del parametro": "Valore del parametro"}}}}
</tool_call>
Il sistema eseguirà lo strumento e ti restituirà i risultati. Non è necessario e non puoi scrivere il tuo strumento per restituire risultati.

Opzione B - Contenuto finale dell'output:
Quando hai ottenuto informazioni sufficienti tramite lo strumento per "Final Answer:" Visualizza il contenuto del capitolo all'inizio。

⚠️ Severamente vietato:
- È vietato includere in un'unica risposta sia la chiamata dello strumento che la risposta finale
- È vietato falsificare i risultati restituiti dagli strumenti (Osservazione). Tutti i risultati dello strumento vengono inseriti dal sistema.
- È possibile richiamare al massimo uno strumento per risposta

═══════════════════════════════════════════════════════════════
【Requisiti relativi al contenuto del capitolo】
═══════════════════════════════════════════════════════════════

1. Content must be based on simulated data retrieved by the tool
2. Ampie citazioni dal testo originale per dimostrare gli effetti della simulazione
3. Utilizza il formato Markdown (ma non consentire intestazioni):
   - Utilizza il **testo in grassetto** per evidenziare i punti importanti (invece dei sottotitoli)
   - utilizzare un elenco (- o1.2.3.）Punti organizzativi
   - Utilizza righe vuote per separare i paragrafi
   - ❌ Uso vietato #、##、###、#### ecc. qualsiasi sintassi del titolo
4. 【Specifica del formato di riferimento: deve essere in paragrafi separati】
   La citazione deve essere un paragrafo indipendente, con una riga vuota prima e dopo, e non può essere mescolata nel paragrafo.：

   ✅ Formato corretto：
   ```
   La risposta della scuola è stata vista come priva di sostanza.。

   > "Il modello di risposta della scuola appare rigido e lento nell’ambiente in continua evoluzione dei social media。"

   Questa valutazione riflette la diffusa insoddisfazione del pubblico。
   ```

   ❌ Formato non valido：
   ```
   La risposta della scuola è stata vista come priva di sostanza.。> "Il modello di risposta della scuola..." Questa valutazione riflette...
   ```
5. Mantenere la coerenza logica con gli altri capitoli
6. 【evitare duplicazioni】Leggere attentamente i capitoli completati di seguito e non ripetere le stesse informazioni.
7. 【Ancora una volta】non aggiungere alcun titolo！Sostituisci i titoli delle sezioni con **grassetto**"""

SECTION_USER_PROMPT_TEMPLATE = """\
Contenuto del capitolo completato (leggere attentamente per evitare duplicazioni）：
{previous_content}

═══════════════════════════════════════════════════════════════
【compito attuale】Scrivi un capitolo: {section_title}
═══════════════════════════════════════════════════════════════

【Promemoria importante】
1. Leggi attentamente i capitoli completati sopra per evitare di ripetere lo stesso contenuto！
2. Prima di iniziare, è necessario richiamare lo strumento per ottenere i dati di simulazione
3. Utilizza un mix di strumenti, non usarne solo uno
4. Il contenuto del report deve provenire dai risultati di ricerca, non utilizzare le tue conoscenze

【⚠️ Avviso sul formato: deve essere seguito】
- ❌ non scrivere alcun titolo（#、##、###、####Nessuno dei due funziona）
- ❌ non scrivere"{section_title}"come inizio
- ✅ I titoli dei capitoli vengono aggiunti automaticamente dal sistema
- ✅ Scrivi direttamente il testo principale e usa il **grassetto** invece dei titoli delle sezioni

per favore inizia：
1. Per prima cosa pensa a quali informazioni sono necessarie per questo capitolo
2. Quindi chiamare lo strumento (Azione) per ottenere i dati di simulazione
3. Dopo aver raccolto informazioni sufficienti, genera la risposta finale (testo semplice, senza titoli)）"""

# ── ReACT Modello di messaggio in-loop ──

REACT_OBSERVATION_TEMPLATE = """\
Observation（Risultati della ricerca）:

═══ Strumenti {tool_name} Ritorno ═══
{result}

═══════════════════════════════════════════════════════════════
Strumento chiamato {tool_calls_count}/{max_tool_calls} volte (usato: {used_tools_str}）{unused_hint}
- Se le informazioni sono sufficienti: con "Final Answer:" Mostra il contenuto del capitolo all'inizio (devi citare il testo originale sopra)
- Se sono necessarie ulteriori informazioni: chiama uno strumento per continuare la ricerca
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "【Nota】Hai appena chiamato{tool_calls_count}strumenti, che richiedono almeno{min_tool_calls}volte。"
    "Richiamare nuovamente lo strumento per ottenere più dati di simulazione, quindi eseguire l'output Final Answer。{unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Al momento solo chiamato {tool_calls_count} strumenti, che richiedono almeno {min_tool_calls} volte。"
    "Chiama lo strumento per ottenere i dati della simulazione。{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Il numero di chiamate utensile ha raggiunto il limite superiore（{tool_calls_count}/{max_tool_calls}），Gli strumenti non possono più essere richiamati。"
    "Ti preghiamo di utilizzare immediatamente le informazioni ottenute \\\"Final Answer:\\\" Visualizza il contenuto del capitolo all'inizio."
)

REACT_UNUSED_TOOLS_HINT = "\n💡 Non l'hai ancora usato: {unused_list}，Si consiglia di provare diversi strumenti per ottenere informazioni multi-angolo"

REACT_FORCE_FINAL_MSG = "È stato raggiunto il limite di chiamate dello strumento, eseguire l'output direttamente Final Answer: e generare il contenuto del capitolo。"

# ── Chat prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
Sei un assistente di previsione della simulazione conciso ed efficiente。

【sfondo】
Condizioni di previsione: {simulation_requirement}

【Rapporto di analisi generato】
{report_content}

【regole】
1. Dai la priorità alle risposte alle domande in base al contenuto del rapporto di cui sopra
2. Rispondi direttamente alle domande ed evita lunghe riflessioni
3. Chiama lo strumento per recuperare più dati solo se il contenuto del report non è sufficiente per rispondere alla domanda
4. Sii conciso nella risposta、chiaro、Organizzato

【Strumenti disponibili】（Usato solo quando necessario, chiamato 1-2 volte al massimo）
{tools_description}

【Formato chiamata utensile】
<tool_call>
{{"name": "Nome dello strumento", "parameters": {{"Nome del parametro": "Valore del parametro"}}}}
</tool_call>

【stile di risposta】
- Sii conciso e diretto, non fare lunghe dichiarazioni
- utilizzare > Formato citazione dei contenuti chiave
- Prima trarre le conclusioni, poi spiegare le ragioni"""

CHAT_OBSERVATION_SUFFIX = "\n\nPer favore rispondi alla domanda in modo conciso。"


# ═══════════════════════════════════════════════════════════════
# ReportAgent classe principale
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Agente di generazione di report di simulazione

    Adotta la modalità ReACT (Ragionamento + Recitazione).：
    1. Fase di pianificazione: analizzare i requisiti della simulazione e pianificare la struttura delle directory del report
    2. Fase di generazione: genera contenuto capitolo per capitolo e ogni capitolo può chiamare lo strumento più volte per ottenere informazioni.
    3. Fase di riflessione: verificare la completezza e l'accuratezza del contenuto
    """
    
    # Numero massimo di chiamate utensile (per capitolo）
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Numero massimo di cicli di riflessione
    MAX_REFLECTION_ROUNDS = 3
    
    # Numero massimo di chiamate strumento in una conversazione
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        inizializzazioneReport Agent
        
        Args:
            graph_id: AtlanteID
            simulation_id: SimulazioneID
            simulation_requirement: Descrizione dei requisiti di simulazione
            llm_client: LLMCliente (facoltativo)）
            zep_tools: ZepServizi di strumenti (facoltativi）
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        # Definizione dello strumento
        self.tools = self._define_tools()
        
        # Registratore (in generate_report Inizializzazione media）
        self.report_logger: Optional[ReportLogger] = None
        # registratore di console (in generate_report Inizializzazione media）
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent Inizializzazione completata: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Definire gli strumenti disponibili"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "Una domanda o un argomento che vorresti analizzare in modo approfondito",
                    "report_context": "Il contesto dell'attuale capitolo del rapporto (facoltativo, aiuta a generare sotto-domande più precise）"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Query di ricerca per la classifica di pertinenza",
                    "include_expired": "Se includere contenuto scaduto/storico (impostazione predefinitaTrue）"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Stringa di query di ricerca",
                    "limit": "Numero di risultati restituiti (facoltativo, predefinito10）"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Argomento del colloquio o descrizione del bisogno (ad es.：'Comprendere le opinioni degli studenti sull’incidente della formaldeide nei dormitori'）",
                    "max_agents": "Il numero massimo di agenti da intervistare (facoltativo, predefinito 5, massimo10）"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Esegue la chiamata dello strumento
        
        Args:
            tool_name: Nome dello strumento
            parameters: Parametri dello strumento
            report_context: contesto di segnalazione (perInsightForge）
            
        Returns:
            Risultati dell'esecuzione dello strumento (formato testo）
        """
        logger.info(f"Strumento di esecuzione: {tool_name}, parametri: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Ricerca approfondita: ottieni il quadro completo
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Ricerca semplice: recupero rapido
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Intervista approfondita: chiama la vera API di intervista di OASIS per ottenere le risposte dell'agente simulato (doppia piattaforma）
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Compatibilità con le versioni precedenti con vecchi strumenti (reindirizzamento interno a nuovi strumenti） ==========
            
            elif tool_name == "search_graph":
                # reindirizzare a quick_search
                logger.info("search_graph Reindirizzato a quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # reindirizzare a insight_forge，perché è più potente
                logger.info("get_simulation_context Reindirizzato a insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"strumento sconosciuto: {tool_name}。Si prega di utilizzare i seguenti strumentiuno: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"L'esecuzione dello strumento non è riuscita: {tool_name}, Errore: {str(e)}")
            return f"L'esecuzione dello strumento non è riuscita: {str(e)}"
    
    # Una raccolta di nomi di strumenti legali per la verifica durante l'analisi del JSON semplice
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Analizza le chiamate dello strumento dalle risposte LLM

        Formati supportati (per priorità）：
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. JSON nudo (la risposta nel suo insieme o una singola riga è una chiamata allo strumento JSON）
        """
        tool_calls = []

        # Formato1: XMLstile (formato standard）
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Formato2: Mantienilo segreto: LLM restituisce direttamente JSON nudo (senza pacchetti) <tool_call> etichetta）
        # Prova solo quando il formato 1 non corrisponde per evitare mancata corrispondenza nel testo. JSON
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # La risposta può contenere testo pensato + JSON semplice, prova a estrarre l'ultimo oggetto JSON
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Verifica se il JSON analizzato è una chiamata a uno strumento legale"""
        # supporto {"name": ..., "parameters": ...} e {"tool": ..., "params": ...} Due nomi chiave
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Nome della chiave unificato name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Genera il testo della descrizione dello strumento"""
        desc_parts = ["Strumenti disponibili："]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  parametri: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Schema del rapporto di pianificazione
        
        Utilizza LLM per analizzare i requisiti di simulazione e pianificare la struttura delle directory del report
        
        Args:
            progress_callback: Funzione di callback di avanzamento
            
        Returns:
            ReportOutline: Schema del rapporto
        """
        logger.info("Inizia a pianificare la struttura del tuo rapporto...")
        
        if progress_callback:
            progress_callback("planning", 0, "Analisi dei requisiti di simulazione...")
        
        # Per prima cosa ottieni il contesto della simulazione
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Generazione della struttura del rapporto...")
        
        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Analisi della struttura del contorno...")
            
            # Analizzare il contorno
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "Rapporto di analisi della simulazione"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "Pianificazione generale completata")
            
            logger.info(f"Pianificazione generale completata: {len(sections)} capitoli")
            return outline
            
        except Exception as e:
            logger.error(f"La pianificazione generale è fallita: {str(e)}")
            # Restituisce la struttura predefinita (3 capitoli, comefallback）
            return ReportOutline(
                title="Rapporto sulle previsioni future",
                summary="Andamento futuro e analisi del rischio sulla base di previsioni di simulazione",
                sections=[
                    ReportSection(title="Scenari predittivi e risultati principali"),
                    ReportSection(title="Analisi predittiva del comportamento della folla"),
                    ReportSection(title="Prospettive di tendenza e avvertenza sui rischi")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Genera contenuto di un singolo capitolo utilizzando la modalità ReACT
        
        Ciclo ReACT：
        1. Thought（Pensare): quali informazioni sono necessarie per l'analisi
        2. Action（Azione): richiama lo strumento per ottenere le informazioni
        3. Observation（Osservazione): lo strumento di analisi restituisce i risultati
        4. Ripetere fino a quando le informazioni sono sufficienti o fino al raggiungimento del tempo massimo
        5. Final Answer（Risposta finale) - Genera il contenuto del capitolo
        
        Args:
            section: Capitoli da generare
            outline: schema completo
            previous_sections: Contenuto dei capitoli precedenti (per continuità）
            progress_callback: Richiamata di avanzamento
            section_index: Indice dei capitoli (per la registrazione）
            
        Returns:
            Contenuto del capitolo (formato Markdown）
        """
        logger.info(f"ReACTGenera capitoli: {section.title}")
        
        # Registra il registro di inizio capitolo
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Crea prompt utente: inserisci un massimo di 4000 parole per ogni capitolo completato
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Massimo 4.000 parole per capitolo
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "（Questo è il primo capitolo）"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACTciclo
        tool_calls_count = 0
        max_iterations = 5  # Numero massimo di cicli di iterazione
        min_tool_calls = 3  # Numero minimo di chiamate utensile
        conflict_retries = 0  # Il numero di conflitti consecutivi tra le chiamate dello strumento e la risposta finale contemporaneamente
        used_tools = set()  # Registrare il nome dell'utensile che è stato chiamato
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Contesto del report per la generazione di sottoproblemi in InsightForge
        report_context = f"Titolo del capitolo: {section.title}\nRequisiti di simulazione: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Ricerca e scrittura approfondite ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # chiamareLLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Controlla se il valore restituito LLM è Nessuno (eccezione API o contenuto vuoto）
            if response is None:
                logger.warning(f"Capitolo {section.title} No. {iteration + 1} iterazioni: LLM Ritorno None")
                # Se rimangono ancora altre iterazioni, aggiungi un messaggio e riprova
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "（la risposta è vuota）"})
                    messages.append({"role": "user", "content": "Continua a generare contenuti。"})
                    continue
                # Anche l'ultima iterazione restituisce None, saltando fuori dal ciclo ed entrando in chiusura forzata.
                break

            logger.debug(f"LLMrisposta: {response[:200]}...")

            # Analizzare una volta e riutilizzare i risultati
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Gestione dei conflitti: LLM genera sia le chiamate agli strumenti che Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Capitolo {section.title} No. {iteration+1} ruota: "
                    f"LLM Emissione simultanea delle chiamate degli strumenti e della risposta finale (sezione {conflict_retries} conflitto）"
                )

                if conflict_retries <= 2:
                    # Le prime due volte: scarta questa risposta e chiedi a LLM di rispondere di nuovo.
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "【Errore di formato】Hai incluso sia una chiamata allo strumento che una risposta finale in un'unica risposta, il che non è consentito。\n"
                            "Ogni risposta può fare solo una delle due cose seguenti:：\n"
                            "- Chiama uno strumento (output a <tool_call> blocca, non scrivere Final Answer）\n"
                            "- Emetti il contenuto finale (con 'Final Answer:' Inizio, non includere <tool_call>）\n"
                            "Per favore rispondi di nuovo e fai solo una di queste cose。"
                        ),
                    })
                    continue
                else:
                    # La terza volta: elaborazione di downgrade, troncare alla prima chiamata dello strumento, forzare l'esecuzione
                    logger.warning(
                        f"Capitolo {section.title}: continuo {conflict_retries} conflitto，"
                        "Downgrade per troncare l'esecuzione della prima chiamata allo strumento"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Registrazione delle risposte LLM
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Caso 1: output LLM Final Answer ──
            if has_final_answer:
                # Il numero di volte in cui lo strumento è stato richiamato non è sufficiente. Rifiuta e chiedi di continuare a regolare lo strumento.
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"（Questi strumenti non sono ancora stati utilizzati, si consiglia di utilizzarli: {', '.join(unused_tools)}）" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Termina normalmente
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Capitolo {section.title} Generazione completata (richiamata utensile: {tool_calls_count}volte）")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Caso 2: LLM tenta di chiamare lo strumento ──
            if has_tool_calls:
                # La quota dello strumento è stata esaurita → Informare chiaramente e richiedere l'output Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Eseguire solo la prima chiamata utensile
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM Prova a chiamare {len(tool_calls)} strumenti, viene eseguito solo il primo: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Crea tooltip inutilizzati
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Caso 3: Né la chiamata dello strumento né Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Il numero di volte in cui lo strumento è stato richiamato non è sufficiente. Si consigliano strumenti non utilizzati.
                unused_tools = all_tools - used_tools
                unused_hint = f"（Questi strumenti non sono ancora stati utilizzati, si consiglia di utilizzarli: {', '.join(unused_tools)}）" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # La chiamata allo strumento è sufficiente, LLM emette il contenuto ma non lo porta "Final Answer:" prefisso
            # Utilizza questo contenuto direttamente come risposta finale, non più inattivo
            logger.info(f"Capitolo {section.title} non rilevato 'Final Answer:' prefisso, adotta direttamente l'output LLM come contenuto finale (chiamata strumento: {tool_calls_count}volte）")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Viene raggiunto il numero massimo di iterazioni e viene forzata la generazione del contenuto.
        logger.warning(f"Capitolo {section.title} Viene raggiunto il numero massimo di iterazioni e viene forzata la generazione")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Controlla se il rendimento LLM lo è None
        if response is None:
            logger.error(f"Capitolo {section.title} Quando si forza la chiusura, LLM restituisce Nessuno e utilizza la richiesta di errore predefinita.")
            final_answer = f"（La generazione di questo capitolo non è riuscita: LLM ha restituito una risposta vuota, riprova più tardi.）"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Registra il contenuto del capitolo e genera un registro di completamento
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Genera un report completo (output in tempo reale in capitoli)
        
        Ogni capitolo viene salvato in una cartella subito dopo essere stato generato, senza attendere il completamento dell'intero report.
        Struttura dei file：
        reports/{report_id}/
            meta.json       - Segnala metainformazioni
            outline.json    - Schema del rapporto
            progress.json   - Costruisci il progresso
            section_01.md   - Capitolo 1
            section_02.md   - Capitolo 2
            ...
            full_report.md  - rapporto completo
        
        Args:
            progress_callback: Funzione di callback di avanzamento (stage, progress, message)
            report_id: ID report (facoltativo, generato automaticamente se non passato)）
            
        Returns:
            Report: rapporto completo
        """
        import uuid
        
        # Se non passato report_id，viene generato automaticamente
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # Elenco dei titoli dei capitoli completati (per il monitoraggio dei progressi）
        completed_section_titles = []
        
        try:
            # Inizializzazione: crea una cartella di report e salva lo stato iniziale
            ReportManager._ensure_report_folder(report_id)
            
            # Inizializza il logger (logging strutturato agent_log.jsonl）
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Inizializza il logger della console（console_log.txt）
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Rapporto di inizializzazione...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # palco1: Schema di pianificazione
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Inizia a pianificare la struttura del tuo rapporto...",
                completed_sections=[]
            )
            
            # Registrare il registro di avvio della pianificazione
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Inizia a pianificare la struttura del tuo rapporto...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # Registrare il registro del completamento della pianificazione
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Salva struttura su file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"La pianificazione generale è completata, per un totale di{len(outline.sections)}capitoli",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Contorno salvato su file: {report_id}/outline.json")
            
            # palco2: Genera capitolo per capitolo (salva nei capitoli)）
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # Salva il contenuto per il contesto
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # aggiornare l'avanzamento
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generazione di capitoli: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"Generazione di capitoli: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Genera il contenuto del capitolo principale
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # salva capitolo
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Registra il registro del completamento del capitolo
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Capitolo salvato: {report_id}/section_{section_num:02d}.md")
                
                # aggiornare l'avanzamento
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Capitolo {section.title} Completato",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # palco3: Assemblare il rapporto completo
            if progress_callback:
                progress_callback("generating", 95, "Assemblaggio del rapporto completo...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Assemblaggio del rapporto completo...",
                completed_sections=completed_section_titles
            )
            
            # Assembla un report completo utilizzando ReportManager
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calcola il tempo totale
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Registrare il registro di completamento del report
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Salva il rapporto finale
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Generazione del rapporto completata",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Generazione del rapporto completata")
            
            logger.info(f"Generazione del rapporto completata: {report_id}")
            
            # Disattiva il registratore della console
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"La generazione del rapporto non è riuscita: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # Registrare il registro degli errori
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Salva stato non riuscito
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"La generazione del rapporto non è riuscita: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignora gli errori di salvataggio non riusciti
            
            # Disattiva il registratore della console
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Parla con l'agente di segnalazione
        
        Durante la conversazione, l'Agente può chiamare autonomamente lo strumento di recupero per rispondere alle domande.
        
        Args:
            message: Messaggi utente
            chat_history: Cronologia delle conversazioni
            
        Returns:
            {
                "response": "AgentRispondi",
                "tool_calls": [Elenco degli strumenti chiamati],
                "sources": [Fonte di informazioni]
            }
        """
        logger.info(f"Report Agentdialogo: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # Ottieni il contenuto del report generato
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limita la lunghezza del report per evitare un contesto lungo
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Il contenuto del report è stato troncato] ..."
        except Exception as e:
            logger.warning(f"Impossibile ottenere il contenuto del rapporto: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "（Nessun rapporto ancora）",
            tools_description=self._get_tools_description(),
        )

        # Costruisci un messaggio
        messages = [{"role": "system", "content": system_prompt}]
        
        # Aggiungi conversazione storica
        for h in chat_history[-10:]:  # Limita la durata della cronologia
            messages.append(h)
        
        # Aggiungi messaggio utente
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACTLoop (versione semplificata)）
        tool_calls_made = []
        max_iterations = 2  # Ridurre il numero di cicli di iterazione
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Chiamata allo strumento di analisi
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # Non viene effettuata alcuna chiamata allo strumento e la risposta viene restituita direttamente
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Eseguire chiamate agli strumenti (numero limitato）
            tool_results = []
            for call in tool_calls[:1]:  # Esegui al massimo 1 chiamata utensile per round
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limita la lunghezza del risultato
                })
                tool_calls_made.append(call)
            
            # Aggiungi risultati al messaggio
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']}risultato]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Raggiungi l'iterazione massima e ottieni la risposta finale
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Risposta pulita
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    responsabile del rapporto
    
    Responsabile dell'archiviazione persistente e del recupero dei report
    
    Struttura dei file (output in capitoli)）：
    reports/
      {report_id}/
        meta.json          - Segnala meta informazioni e stato
        outline.json       - Schema del rapporto
        progress.json      - Costruisci il progresso
        section_01.md      - Capitolo 1
        section_02.md      - Capitolo 2
        ...
        full_report.md     - rapporto completo
    """
    
    # Directory di archiviazione dei report
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Assicurati che la directory root del report esista"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Ottieni il percorso della cartella del report"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Assicurati che la cartella dei report esista e restituisci il percorso"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Ottieni il percorso del file delle metainformazioni del report"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Ottieni il percorso completo del file Markdown del report"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Ottieni il percorso del file di struttura"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Ottieni il percorso del file di avanzamento"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Ottieni il percorso del file Markdown del capitolo"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Ottieni il percorso del file di registro dell'agente"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Ottieni il percorso del file di registro della console"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Ottieni il contenuto del registro della console
        
        Questo è il registro di output della console durante la generazione del report（INFO、WARNINGecc.),
        con agent_log.jsonl Registri strutturati diversi。
        
        Args:
            report_id: rapportoID
            from_line: Da quale riga iniziare la lettura (per l'acquisizione incrementale, 0 significa iniziare dall'inizio）
            
        Returns:
            {
                "logs": [Elenco delle righe di registro],
                "total_lines": Numero totale di righe,
                "from_line": Numero della linea di partenza,
                "has_more": Ci sono più log?
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Mantieni le righe di registro originali, rimuovi i ritorni a capo finali
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Leggi fino alla fine
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Ottieni il registro completo della console (ottieni tutto in una volta）
        
        Args:
            report_id: rapportoID
            
        Returns:
            Elenco delle righe di registro
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Ottieni il contenuto del registro dell'agente
        
        Args:
            report_id: rapportoID
            from_line: Da quale riga iniziare la lettura (per l'acquisizione incrementale, 0 significa iniziare dall'inizio）
            
        Returns:
            {
                "logs": [Elenco delle voci di registro],
                "total_lines": Numero totale di righe,
                "from_line": Numero della linea di partenza,
                "has_more": Ci sono più log?
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Salta le righe la cui analisi non è riuscita
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Leggi fino alla fine
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Ottieni il registro completo dell'agente (utilizzato per ottenere tutto in una volta）
        
        Args:
            report_id: rapportoID
            
        Returns:
            Elenco delle voci di registro
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Salva la struttura del rapporto
        
        Chiamato immediatamente dopo il completamento della fase di pianificazione
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Contorno salvato: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Salva un singolo capitolo

        Chiamato immediatamente dopo la generazione di ciascun capitolo per ottenere un output capitolo per capitolo.

        Args:
            report_id: rapportoID
            section_index: Indice dei capitoli (inizia da 1）
            section: Oggetto del capitolo

        Returns:
            Percorso del file salvato
        """
        cls._ensure_report_folder(report_id)

        # Crea contenuto Markdown del capitolo: ripulisci eventuali titoli duplicati
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # salva file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Capitolo salvato: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Pulisci il contenuto del capitolo
        
        1. Rimuovi la riga del titolo Markdown che duplica il titolo del capitolo all'inizio del contenuto
        2. lo faranno tutti ### I titoli ai livelli e ai livelli inferiori vengono convertiti in testo in grassetto
        
        Args:
            content: contenuto originale
            section_title: Titolo del capitolo
            
        Returns:
            Contenuti puliti
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Controlla se si tratta di una riga di intestazione Markdown
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Controlla se il titolo è un duplicato del titolo del capitolo (salta i duplicati entro le prime 5 righe）
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Converti tutte le intestazioni di livello（#, ##, ###, ####ecc.) convertito in grassetto
                # Poiché i titoli dei capitoli vengono aggiunti dal sistema, non dovrebbero esserci titoli nel contenuto
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # aggiungi una riga vuota
                continue
            
            # Se la riga precedente è un titolo saltato e la riga corrente è vuota, anch'essa verrà saltata.
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Rimuovi le righe vuote iniziali
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Rimuovere il separatore principale
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Rimuovi anche le righe vuote dopo i separatori
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Aggiorna l'avanzamento della generazione del report
        
        Il front-end può leggere tramiteprogress.jsonOttieni progressi in tempo reale
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni i progressi nella generazione dei report"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Ottieni l'elenco dei capitoli generato
        
        Restituisce tutte le informazioni sul file del capitolo salvato
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Analizza l'indice dei capitoli dal nome del file
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemblare il rapporto completo
        
        Assembla un rapporto completo dai file dei capitoli salvati con la pulizia del titolo
        """
        folder = cls._get_report_folder(report_id)
        
        # Crea intestazione del report
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # Leggere tutti i file dei capitoli in sequenza
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Post-elaborazione: elimina i problemi relativi ai titoli in tutto il rapporto
        md_content = cls._post_process_report(md_content, outline)
        
        # Salva il rapporto completo
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Rapporto completo raccolto: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Contenuto del report di post-elaborazione
        
        1. Rimuovi i titoli duplicati
        2. Mantieni il titolo principale del rapporto(#)e titoli dei capitoli(##)，Rimuovi le intestazioni da altri livelli(###, ####Aspetta)
        3. Pulisci le righe vuote e i separatori aggiuntivi
        
        Args:
            content: Contenuto del rapporto originale
            outline: Schema del rapporto
            
        Returns:
            Contenuti elaborati
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Raccogli tutti i titoli dei capitoli nella struttura
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Controlla se è una riga di intestazione
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Controlla se si tratta di un titolo duplicato (i titoli con lo stesso contenuto compaiono entro 5 righe consecutive)）
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Salta le intestazioni ripetute e le righe vuote dopo di esse
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Elaborazione a livello di titolo：
                # - # (level=1) Conserva solo il titolo del report principale
                # - ## (level=2) Conserva i titoli dei capitoli
                # - ### e sotto (level>=3) Converti in testo in grassetto
                
                if level == 1:
                    if title == outline.title:
                        # Mantieni il titolo principale del rapporto
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Titolo del capitolo utilizzato in modo errato#，Corretto a##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Gli altri titoli di primo livello sono scritti in grassetto
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Conserva i titoli dei capitoli
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # I titoli di secondo livello che non sono capitoli vengono scritti in grassetto
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### I titoli ai livelli e ai livelli inferiori vengono convertiti in testo in grassetto
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Salta il separatore immediatamente successivo al titolo
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Lascia solo una riga vuota dopo il titolo
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Pulisci più righe vuote consecutive (mantieni fino a 2）
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Salva le meta informazioni del report e il report completo"""
        cls._ensure_report_folder(report.report_id)
        
        # Salva metainformazioniJSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # salva il contorno
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Salva il rapporto Markdown completo
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Rapporto salvato: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Ottieni un rapporto"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Compatibile con i formati precedenti: controlla i file archiviati direttamente nella directory dei report
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Ricostruisci l'oggetto report
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # semarkdown_contentè vuoto, prova a iniziare dafull_report.mdleggere
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Ottieni report basati sull'ID di rappresentazione"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Nuovo formato: cartella
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Compatibile con i vecchi formati: file JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """elencare i rapporti"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Nuovo formato: cartella
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Compatibile con i vecchi formati: file JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # In ordine decrescente di tempo di creazione
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Elimina rapporto (intera cartella）"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # Nuovo formato: elimina l'intera cartella
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Cartella del rapporto eliminata: {report_id}")
            return True
        
        # Compatibile con i formati precedenti: elimina singoli file
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
