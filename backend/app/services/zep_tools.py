"""
ZepServizio di strumenti di ricerca
Ricerca sulla mappa dei pacchetti、Nodo letto、Edge query e altri strumenti utilizzabili da Report Agent

Strumenti di ricerca principali (dopo l'ottimizzazione）：
1. InsightForge（Deep Insight Search) - la ricerca ibrida più potente, genera automaticamente sotto-domande e ricerca multidimensionale
2. PanoramaSearch（Ricerca in ampiezza): ottieni un quadro completo, compresi i contenuti scaduti
3. QuickSearch（Ricerca semplice) - Recupero rapido
"""

import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_tools')


@dataclass
class SearchResult:
    """Risultati della ricerca"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """Converti in formato testo affinché LLM possa comprendere"""
        text_parts = [f"query di ricerca: {self.query}", f"trovato {self.total_count} informazioni correlate"]
        
        if self.facts:
            text_parts.append("\n### Fatti rilevanti:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """Informazioni sul nodo"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }
    
    def to_text(self) -> str:
        """Converti in formato testo"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node"]), "tipo sconosciuto")
        return f"Entità: {self.name} (Digitare: {entity_type})\nSommario: {self.summary}"


@dataclass
class EdgeInfo:
    """informazioni laterali"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # informazioni sul tempo
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }
    
    def to_text(self, include_temporal: bool = False) -> str:
        """Converti in formato testo"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"relazione: {source} --[{self.name}]--> {target}\nfatti: {self.fact}"
        
        if include_temporal:
            valid_at = self.valid_at or "sconosciuto"
            invalid_at = self.invalid_at or "finora"
            base_text += f"\nlimite di tempo: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (Scaduto: {self.expired_at})"
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """È scaduto?"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """È scaduto?"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
    Approfondimenti sui risultati di ricerca (InsightForge)
    Contiene risultati di ricerca per più domande secondarie e analisi complete
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    # Risultati della ricerca per ciascuna dimensione
    semantic_facts: List[str] = field(default_factory=list)  # Risultati della ricerca semantica
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)  # intuizioni sull'entità
    relationship_chains: List[str] = field(default_factory=list)  # catena di relazioni
    
    # Statistiche
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """Converti in un formato di testo dettagliato affinché LLM possa comprenderlo"""
        text_parts = [
            f"## Analisi approfondita delle previsioni future",
            f"Analizzare il problema: {self.query}",
            f"Scenari di previsione: {self.simulation_requirement}",
            f"\n### Statistiche di previsione",
            f"- Fatti di previsione rilevanti: {self.total_facts}Articolo",
            f"- Enti coinvolti: {self.total_entities}un",
            f"- catena di relazioni: {self.total_relationships}Articolo"
        ]
        
        # sottoproblema
        if self.sub_queries:
            text_parts.append(f"\n### Sottoproblemi analitici")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        # Risultati della ricerca semantica
        if self.semantic_facts:
            text_parts.append(f"\n### 【fatti chiave】(Si prega di citare questi testi originali nella relazione)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # intuizioni sull'entità
        if self.entity_insights:
            text_parts.append(f"\n### 【entità centrale】")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', 'sconosciuto')}** ({entity.get('type', 'Entità')})")
                if entity.get('summary'):
                    text_parts.append(f"  Sommario: \"{entity.get('summary')}\"")
                if entity.get('related_facts'):
                    text_parts.append(f"  Fatti rilevanti: {len(entity.get('related_facts', []))}Articolo")
        
        # catena di relazioni
        if self.relationship_chains:
            text_parts.append(f"\n### 【catena di relazioni】")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    Risultati della ricerca di ampiezza (Panorama)
    Contiene tutte le informazioni rilevanti, incluso il contenuto scaduto
    """
    query: str
    
    # Tutti i nodi
    all_nodes: List[NodeInfo] = field(default_factory=list)
    # Tutti i bordi (compresi quelli scaduti）
    all_edges: List[EdgeInfo] = field(default_factory=list)
    # Fatti attuali
    active_facts: List[str] = field(default_factory=list)
    # Fatti scaduti/scaduti (storia）
    historical_facts: List[str] = field(default_factory=list)
    
    # Statistiche
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """Converti in formato testo (versione completa, non troncata）"""
        text_parts = [
            f"## Risultati della ricerca in ampiezza (vista panoramica del futuro）",
            f"Domanda: {self.query}",
            f"\n### Statistiche",
            f"- Numero totale di nodi: {self.total_nodes}",
            f"- numero totale di bordi: {self.total_edges}",
            f"- fatti validi attuali: {self.active_count}Articolo",
            f"- Fatti storici/scaduti: {self.historical_count}Articolo"
        ]
        
        # Fatti attualmente validi (output completo, non troncato）
        if self.active_facts:
            text_parts.append(f"\n### 【fatti validi attuali】(Risultati della simulazione originale)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Fatti storici/scaduti (output completo, senza troncamento）
        if self.historical_facts:
            text_parts.append(f"\n### 【Fatti storici/scaduti】(Registro del processo di evoluzione)")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Entità chiave (output completo, senza troncamento）
        if self.all_nodes:
            text_parts.append(f"\n### 【Enti coinvolti】")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "Entità")
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """Risultati dell'intervista di un singolo agente"""
    agent_name: str
    agent_role: str  # Tipo di ruolo (es. studente、insegnante、media ecc.）
    agent_bio: str  # Introduzione
    question: str  # domande dell'intervista
    response: str  # Risposte all'intervista
    key_quotes: List[str] = field(default_factory=list)  # Citazioni chiave
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }
    
    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        # spettacolo completoagent_bio，Non troncare
        text += f"_Introduzione: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**Citazioni chiave:**\n"
            for quote in self.key_quotes:
                # Pulisci varie citazioni
                clean_quote = quote.replace('\u201c', '').replace('\u201d', '').replace('"', '')
                clean_quote = clean_quote.replace('\u300c', '').replace('\u300d', '')
                clean_quote = clean_quote.strip()
                # Rimuovi la punteggiatura iniziale
                while clean_quote and clean_quote[0] in '，,；;：:、。！？\n\r\t ':
                    clean_quote = clean_quote[1:]
                # Filtra lo spam contenente i numeri delle domande (question1-9）
                skip = False
                for d in '123456789':
                    if f'\u95ee\u9898{d}' in clean_quote:
                        skip = True
                        break
                if skip:
                    continue
                # Troncare contenuti troppo lunghi (troncare per punto, non troncamento definitivo)）
                if len(clean_quote) > 150:
                    dot_pos = clean_quote.find('\u3002', 80)
                    if dot_pos > 0:
                        clean_quote = clean_quote[:dot_pos + 1]
                    else:
                        clean_quote = clean_quote[:147] + "..."
                if clean_quote and len(clean_quote) >= 10:
                    text += f'> "{clean_quote}"\n'
        return text


@dataclass
class InterviewResult:
    """
    Risultati dell'intervista (Interview)
    Contiene le risposte alle interviste di più agenti simulati
    """
    interview_topic: str  # Argomenti dell'intervista
    interview_questions: List[str]  # Elenco delle domande dell'intervista
    
    # Intervista selezionataAgent
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    # Risposte all'intervista di ciascun agente
    interviews: List[AgentInterview] = field(default_factory=list)
    
    # Motivi per scegliere l'Agente
    selection_reasoning: str = ""
    # Riepilogo consolidato dell'intervista
    summary: str = ""
    
    # Statistiche
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """Convertito in formato di testo dettagliato per la comprensione LLM e la citazione del rapporto"""
        text_parts = [
            "## Rapporto approfondito dell'intervista",
            f"**Argomenti dell'intervista:** {self.interview_topic}",
            f"**Numero di interviste:** {self.interviewed_count} / {self.total_agents} simulazione di bitAgent",
            "\n### Ragioni per la selezione degli intervistati",
            self.selection_reasoning or "（selezione automatica）",
            "\n---",
            "\n### Trascrizione dell'intervista",
        ]

        if self.interviews:
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### intervista #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        else:
            text_parts.append("（Nessuna registrazione dell'intervista）\n\n---")

        text_parts.append("\n### Sintesi dell'intervista e punti chiave")
        text_parts.append(self.summary or "（Nessun astratto）")

        return "\n".join(text_parts)


class ZepToolsService:
    """
    ZepServizio di strumenti di ricerca
    
    【Strumenti di ricerca principali: dopo l'ottimizzazione】
    1. insight_forge - Recupero approfondito degli insight (il più potente, genera automaticamente sotto-domande, recupero multidimensionale）
    2. panorama_search - Ricerca approfondita (ottiene il quadro completo, compresi i contenuti scaduti）
    3. quick_search - Ricerca semplice (recupero rapido)）
    4. interview_agents - Interviste approfondite (intervista ad agenti simulati per ottenere molteplici prospettive)）
    
    【strumenti di base】
    - search_graph - Ricerca semantica del grafico
    - get_all_nodes - Ottieni tutti i nodi nel grafico
    - get_all_edges - Ottieni tutti i bordi del grafico (comprese le informazioni temporali）
    - get_node_detail - Ottieni i dettagli del nodo
    - get_node_edges - Ottieni i bordi relativi al nodo
    - get_entities_by_type - Ottieni entità per tipo
    - get_entity_summary - Ottieni il riepilogo delle relazioni di un'entità
    """
    
    # Riprovare la configurazione
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY Non configurato")
        
        self.client = Zep(api_key=self.api_key)
        # LLMClient utilizzato da InsightForge per generare sotto-domande
        self._llm_client = llm_client
        logger.info("ZepToolsService Inizializzazione completata")
    
    @property
    def llm(self) -> LLMClient:
        """Inizializzazione pigra del client LLM"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """Chiamate API con meccanismo di ripetizione"""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        delay = self.RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} No. {attempt + 1} tentativi falliti: {str(e)[:100]}, "
                        f"{delay:.1f}Riprova tra qualche secondo..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Zep {operation_name} dentro {max_retries} Ancora fallito dopo i tentativi: {str(e)}")
        
        raise last_exception
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Ricerca semantica del grafico
        
        Cerca nel grafico informazioni rilevanti utilizzando la ricerca ibrida (semantica + BM25).
        Se l'API di ricerca di Zep Cloud non è disponibile, esegui il downgrade alla corrispondenza delle parole chiave locali。
        
        Args:
            graph_id: AtlanteID (Standalone Graph)
            query: query di ricerca
            limit: Numero di risultati restituiti
            scope: Ambito di ricerca，"edges" o "nodes"
            
        Returns:
            SearchResult: Risultati della ricerca
        """
        logger.info(f"Ricerca grafica: graph_id={graph_id}, query={query[:50]}...")
        
        # Prova a utilizzareZep Cloud Search API
        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id,
                    query=query,
                    limit=limit,
                    scope=scope,
                    reranker="cross_encoder"
                ),
                operation_name=f"Ricerca grafica(graph={graph_id})"
            )
            
            facts = []
            edges = []
            nodes = []
            
            # Analizza i risultati della ricerca sui bordi
            if hasattr(search_results, 'edges') and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                        "name": getattr(edge, 'name', ''),
                        "fact": getattr(edge, 'fact', ''),
                        "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                        "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                    })
            
            # Analizza i risultati della ricerca del nodo
            if hasattr(search_results, 'nodes') and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                        "name": getattr(node, 'name', ''),
                        "labels": getattr(node, 'labels', []),
                        "summary": getattr(node, 'summary', ''),
                    })
                    # Anche i riepiloghi dei nodi contano come fatti
                    if hasattr(node, 'summary') and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"Ricerca completata: trovato {len(facts)} fatti rilevanti")
            
            return SearchResult(
                facts=facts,
                edges=edges,
                nodes=nodes,
                query=query,
                total_count=len(facts)
            )
            
        except Exception as e:
            logger.warning(f"Zep Search APIOperazione non riuscita, declassato alla ricerca locale: {str(e)}")
            # Downgrade: utilizza la ricerca con corrispondenza di parole chiave locali
            return self._local_search(graph_id, query, limit, scope)
    
    def _local_search(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Ricerca con corrispondenza di parole chiave locali (come downgrade all'API Zep Search)
        
        Ottieni tutti i bordi/nodi e quindi esegui la corrispondenza delle parole chiave localmente
        
        Args:
            graph_id: AtlanteID
            query: query di ricerca
            limit: Numero di risultati restituiti
            scope: Ambito di ricerca
            
        Returns:
            SearchResult: Risultati della ricerca
        """
        logger.info(f"Utilizza la ricerca locale: query={query[:30]}...")
        
        facts = []
        edges_result = []
        nodes_result = []
        
        # Estrai le parole chiave della query (segmentazione semplice delle parole）
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def match_score(text: str) -> int:
            """Calcola il punteggio di corrispondenza tra testo e query"""
            if not text:
                return 0
            text_lower = text.lower()
            # query con corrispondenza esatta
            if query_lower in text_lower:
                return 100
            # corrispondenza delle parole chiave
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score
        
        try:
            if scope in ["edges", "both"]:
                # Ottieni tutti i bordi e abbinali
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))
                
                # Ordina per punteggio
                scored_edges.sort(key=lambda x: x[0], reverse=True)
                
                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                # Ottieni tutti i nodi e abbinali
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))
                
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                
                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"Ricerca locale completata: trovato {len(facts)} fatti rilevanti")
            
        except Exception as e:
            logger.error(f"La ricerca locale non è riuscita: {str(e)}")
        
        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """
        Ottieni tutti i nodi del grafico (ottieni in pagine）

        Args:
            graph_id: AtlanteID

        Returns:
            elenco dei nodi
        """
        logger.info(f"Ottieni la mappa {graph_id} tutti i nodi di...")

        nodes = fetch_all_nodes(self.client, graph_id)

        result = []
        for node in nodes:
            node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', None) or ""
            result.append(NodeInfo(
                uuid=str(node_uuid) if node_uuid else "",
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))

        logger.info(f"Ottieni {len(result)} nodi")
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """
        Ottieni tutti i bordi del grafico (acquisisci in pagine, comprese le informazioni temporali）

        Args:
            graph_id: AtlanteID
            include_temporal: Se includere le informazioni sull'ora (impostazione predefinitaTrue）

        Returns:
            elenco dei bordi (contienecreated_at, valid_at, invalid_at, expired_at）
        """
        logger.info(f"Ottieni la mappa {graph_id} tutti i lati di...")

        edges = fetch_all_edges(self.client, graph_id)

        result = []
        for edge in edges:
            edge_uuid = getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', None) or ""
            edge_info = EdgeInfo(
                uuid=str(edge_uuid) if edge_uuid else "",
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )

            # Aggiungi informazioni sull'ora
            if include_temporal:
                edge_info.created_at = getattr(edge, 'created_at', None)
                edge_info.valid_at = getattr(edge, 'valid_at', None)
                edge_info.invalid_at = getattr(edge, 'invalid_at', None)
                edge_info.expired_at = getattr(edge, 'expired_at', None)

            result.append(edge_info)

        logger.info(f"Ottieni {len(result)} bordo della striscia")
        return result
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """
        Ottieni i dettagli di un singolo nodo
        
        Args:
            node_uuid: nodoUUID
            
        Returns:
            Informazioni sul nodo oNone
        """
        logger.info(f"Ottieni i dettagli del nodo: {node_uuid[:8]}...")
        
        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=f"Ottieni i dettagli del nodo(uuid={node_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            return NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except Exception as e:
            logger.error(f"Impossibile ottenere i dettagli del nodo: {str(e)}")
            return None
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """
        Ottieni tutti i bordi relativi a un nodo
        
        Ottenendo tutti gli spigoli del grafico e quindi filtrando gli spigoli relativi al nodo specificato
        
        Args:
            graph_id: AtlanteID
            node_uuid: nodoUUID
            
        Returns:
            elenco dei bordi
        """
        logger.info(f"Ottieni nodo {node_uuid[:8]}... I bordi rilevanti di")
        
        try:
            # Ottieni tutti i bordi del grafico e poi filtra
            all_edges = self.get_all_edges(graph_id)
            
            result = []
            for edge in all_edges:
                # Controlla se un bordo è correlato a un nodo specificato (come origine o destinazione）
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)
            
            logger.info(f"trovato {len(result)} bordi relativi ad un nodo")
            return result
            
        except Exception as e:
            logger.warning(f"Impossibile ottenere i bordi del nodo: {str(e)}")
            return []
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str
    ) -> List[NodeInfo]:
        """
        Ottieni entità per tipo
        
        Args:
            graph_id: AtlanteID
            entity_type: Tipo di entità (es. Student, PublicFigure Aspetta）
            
        Returns:
            Elenco di entità corrispondenti al tipo
        """
        logger.info(f"Il tipo di acquisizione è {entity_type} entità...")
        
        all_nodes = self.get_all_nodes(graph_id)
        
        filtered = []
        for node in all_nodes:
            # Controlla se le etichette contengono il tipo specificato
            if entity_type in node.labels:
                filtered.append(node)
        
        logger.info(f"trovato {len(filtered)} un {entity_type} tipo di entità")
        return filtered
    
    def get_entity_summary(
        self, 
        graph_id: str, 
        entity_name: str
    ) -> Dict[str, Any]:
        """
        Ottieni il riepilogo della relazione per l'entità specificata
        
        Cerca tutte le informazioni relative a questa entità e genera un riepilogo
        
        Args:
            graph_id: AtlanteID
            entity_name: Nome dell'entità
            
        Returns:
            Informazioni di riepilogo sull'entità
        """
        logger.info(f"Ottieni entità {entity_name} Riepilogo delle relazioni...")
        
        # Prima ricerca di informazioni relative all'entità
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )
        
        # Prova a trovare l'entità in tutti i nodi
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break
        
        related_edges = []
        if entity_node:
            # in arrivograph_idparametri
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """
        Ottieni statistiche sul grafico
        
        Args:
            graph_id: AtlanteID
            
        Returns:
            Statistiche
        """
        logger.info(f"Ottieni la mappa {graph_id} Statistiche...")
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        # Distribuzione del tipo di entità statistica
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        # Distribuzione dei tipi di relazione statistica
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }
    
    def get_simulation_context(
        self, 
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        Ottieni informazioni contestuali relative alla simulazione
        
        Ricerca completa di tutte le informazioni rilevanti per le tue esigenze di simulazione
        
        Args:
            graph_id: AtlanteID
            simulation_requirement: Descrizione dei requisiti di simulazione
            limit: Limite quantitativo per ogni tipo di informazione
            
        Returns:
            Informazioni sul contesto della simulazione
        """
        logger.info(f"Ottieni il contesto della simulazione: {simulation_requirement[:50]}...")
        
        # Cerca informazioni relative ai requisiti di simulazione
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )
        
        # Ottieni statistiche sul grafico
        stats = self.get_graph_statistics(graph_id)
        
        # Ottieni tutti i nodi dell'entità
        all_nodes = self.get_all_nodes(graph_id)
        
        # Filtra le entità con i tipi effettivi (nodi Entità non puri）
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node"]]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary
                })
        
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],  # quantità limitata
            "total_entities": len(entities)
        }
    
    # ========== Strumenti di ricerca principali (dopo l'ottimizzazione） ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        【InsightForge - Ricerca approfondita】
        
        La più potente funzione di recupero ibrido, scompone automaticamente le domande ed esegue il recupero multidimensionale：
        1. Utilizzare LLM per scomporre il problema in sottoproblemi
        2. Ricerca semantica per ogni sotto-domanda
        3. Estrai le entità correlate e ottieni i loro dettagli
        4. Traccia la catena delle relazioni
        5. Integra tutti i risultati per generare insight approfonditi
        
        Args:
            graph_id: AtlanteID
            query: Problemi dell'utente
            simulation_requirement: Descrizione dei requisiti di simulazione
            report_context: Contesto del report (facoltativo, per una generazione di sottoproblemi più precisa）
            max_sub_queries: Numero massimo di sottoproblemi
            
        Returns:
            InsightForgeResult: Approfondimenti sui risultati di ricerca
        """
        logger.info(f"InsightForge Ricerca approfondita: {query[:50]}...")
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Step 1: Utilizzare LLM per generare sottoproblemi
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"generare {len(sub_queries)} sottoproblema")
        
        # Step 2: Ricerca semantica per ogni sotto-domanda
        all_facts = []
        all_edges = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            search_result = self.search_graph(
                graph_id=graph_id,
                query=sub_query,
                limit=15,
                scope="edges"
            )
            
            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
            
            all_edges.extend(search_result.edges)
        
        # Cerca anche la domanda originale
        main_search = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=20,
            scope="edges"
        )
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # Step 3: Estrai gli UUID delle entità correlate dai bordi e ottieni solo informazioni su queste entità (non ottieni tutti i nodi）
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)
        
        # Ottieni i dettagli di tutte le entità correlate (numero illimitato, output completo）
        entity_insights = []
        node_map = {}  # Utilizzato per la successiva costruzione della catena di relazioni
        
        for uuid in list(entity_uuids):  # Elabora tutte le entità senza troncamento
            if not uuid:
                continue
            try:
                # Ottieni informazioni su ciascun nodo rilevante individualmente
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "Entità")
                    
                    # Ottieni tutti i fatti relativi a questa entità (senza troncamento）
                    related_facts = [
                        f for f in all_facts 
                        if node.name.lower() in f.lower()
                    ]
                    
                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts  # Output completo senza troncamento
                    })
            except Exception as e:
                logger.debug(f"Ottieni nodo {uuid} fallito: {e}")
                continue
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Step 4: Costruisci tutte le catene di relazioni (nessun limite al numero）
        relationship_chains = []
        for edge_data in all_edges:  # Elabora tutti i bordi senza troncamento
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"InsightForgeCompleto: {result.total_facts}fatti, {result.total_entities}entità, {result.total_relationships}relazione")
        return result
    
    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """
        Utilizzare LLM per generare sottoproblemi
        
        Scomporre i problemi complessi in più sottoproblemi che possono essere recuperati in modo indipendente
        """
        system_prompt = """Sei un analizzatore di problemi professionale. Il tuo compito è scomporre un problema complesso in più sottoproblemi che possono essere osservati in modo indipendente in un mondo simulato.

richiesta：
1. Ciascun sottoproblema dovrebbe essere sufficientemente specifico da poter riscontrare il comportamento o gli eventi rilevanti dell'Agente nel mondo simulato
2. I sottoproblemi dovrebbero coprire diverse dimensioni del problema originale (ad esempio chi、cosa、perché、Com'è?、quando、Dove）
3. I sottoproblemi dovrebbero essere rilevanti per lo scenario di simulazione
4. Restituisce il formato JSON：{"sub_queries": ["sottoproblema1", "sottoproblema2", ...]}"""

        user_prompt = f"""Contesto dei requisiti di simulazione：
{simulation_requirement}

{f"Contesto del rapporto：{report_context[:500]}" if report_context else ""}

Si prega di suddividere le seguenti domande in{max_queries}sottoproblema：
{query}

Restituisce un elenco di sotto-domande in formato JSON。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            sub_queries = response.get("sub_queries", [])
            # Assicurati che sia un elenco di stringhe
            return [str(sq) for sq in sub_queries[:max_queries]]
            
        except Exception as e:
            logger.warning(f"Impossibile generare la domanda secondaria: {str(e)}，Utilizza la domanda secondaria predefinita")
            # Downgrade: restituisce una variante basata sulla domanda originale
            return [
                query,
                f"{query} principali attori in",
                f"{query} cause ed effetti",
                f"{query} processo di sviluppo"
            ][:max_queries]
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        【PanoramaSearch - ricerca in ampiezza】
        
        Ottieni una visualizzazione completa, inclusi tutti i contenuti rilevanti e le informazioni storiche/scadenza：
        1. Ottieni tutti i nodi correlati
        2. Ottieni tutti i bordi (compresi quelli scaduti/non validi）
        3. Classificare le informazioni attualmente valide e storiche
        
        Questo strumento è adatto a coloro che hanno bisogno di comprendere l'intero incidente、Scenari che ne tracciano l'evoluzione。
        
        Args:
            graph_id: AtlanteID
            query: Query di ricerca (per la classifica di pertinenza）
            include_expired: Se includere contenuti scaduti (impostazione predefinitaTrue）
            limit: Limite al numero di risultati restituiti
            
        Returns:
            PanoramaResult: Risultati della ricerca di ampiezza
        """
        logger.info(f"PanoramaSearch ricerca in ampiezza: {query[:50]}...")
        
        result = PanoramaResult(query=query)
        
        # Ottieni tutti i nodi
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)
        
        # Ottieni tutti i bordi (comprese le informazioni sul tempo）
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)
        
        # fatti di classificazione
        active_facts = []
        historical_facts = []
        
        for edge in all_edges:
            if not edge.fact:
                continue
            
            # Aggiungi il nome dell'entità al fatto
            source_name = node_map.get(edge.source_node_uuid, NodeInfo('', '', [], '', {})).name or edge.source_node_uuid[:8]
            target_name = node_map.get(edge.target_node_uuid, NodeInfo('', '', [], '', {})).name or edge.target_node_uuid[:8]
            
            # Determina se è scaduto/scaduto
            is_historical = edge.is_expired or edge.is_invalid
            
            if is_historical:
                # Fatti storici/scaduti, aggiungi timestamp
                valid_at = edge.valid_at or "sconosciuto"
                invalid_at = edge.invalid_at or edge.expired_at or "sconosciuto"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                # fatti validi attuali
                active_facts.append(edge.fact)
        
        # Classifica per pertinenza in base alla query
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score
        
        # Ordina e limita le quantità
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)
        
        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)
        
        logger.info(f"PanoramaSearchCompleto: {result.active_count}valido, {result.historical_count}storia")
        return result
    
    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        【QuickSearch - Ricerca semplice】
        
        veloce、Strumento di ricerca leggero：
        1. Chiama direttamente la ricerca semantica Zep
        2. Restituisci i risultati più rilevanti
        3. adatto per semplice、requisiti di ricerca diretta
        
        Args:
            graph_id: AtlanteID
            query: query di ricerca
            limit: Numero di risultati restituiti
            
        Returns:
            SearchResult: Risultati della ricerca
        """
        logger.info(f"QuickSearch Ricerca semplice: {query[:50]}...")
        
        # Chiama direttamente un esistentesearch_graphmetodo
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )
        
        logger.info(f"QuickSearchCompleto: {result.total_count}risultati")
        return result
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        【InterviewAgents - intervista approfondita】
        
        Chiama la vera API dell'intervista di OASIS, che è in esecuzione nella simulazione dell'intervistaAgent：
        1. Leggi automaticamente i file dei personaggi e comprendi tutte le simulazioniAgent
        2. Utilizza LLM per analizzare le esigenze dei colloqui e selezionare in modo intelligente quelle più rilevantiAgent
        3. Genera domande per l'intervista utilizzando LLM
        4. Chiama l'interfaccia /api/simulation/interview/batch per condurre interviste reali (interviste simultanee su doppia piattaforma）
        5. Integra tutti i risultati delle interviste e genera rapporti sulle interviste
        
        【importante】Questa funzionalità richiede che l'ambiente di simulazione sia in esecuzione (l'ambiente OASIS non è chiuso）
        
        【Scenari di utilizzo】
        - Necessità di comprendere gli eventi dalle prospettive dei diversi ruoli
        - Necessità di raccogliere opinioni e prospettive da più parti
        - Necessità di ottenere risposte reali dall'Agente simulato (simulazione non LLM）
        
        Args:
            simulation_id: ID di impersonificazione (utilizzato per individuare file personali e convocare intervisteAPI）
            interview_requirement: Descrizione delle esigenze del colloquio (non strutturato, ad es."Comprendere il punto di vista degli studenti sull’incidente"）
            simulation_requirement: Background dei requisiti di simulazione (facoltativo）
            max_agents: Numero massimo di agenti intervistati
            custom_questions: Domande per interviste personalizzate (facoltative, generate automaticamente se non fornite)）
            
        Returns:
            InterviewResult: Risultati dell'intervista
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(f"InterviewAgents Intervista approfondita (realeAPI）: {interview_requirement[:50]}...")
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )
        
        # Step 1: Leggi il file dei caratteri
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(f"Simulazione non trovata {simulation_id} Fascicolo personale")
            result.summary = "Nessun profilo agente intervistabile trovato"
            return result
        
        result.total_agents = len(profiles)
        logger.info(f"caricare a {len(profiles)} Profilo dell'agente")
        
        # Step 2: Utilizza LLM per selezionare l'agente da intervistare (returnagent_idelenco）
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"selezionato {len(selected_agents)} L'agente conduce le interviste: {selected_indices}")
        
        # Step 3: Genera domande per l'intervista (se non fornite）
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"Generato {len(result.interview_questions)} domande dell'intervista")
        
        # Combina le domande in un'unica intervistaprompt
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        
        # Aggiungi il prefisso di ottimizzazione per limitare il formato di risposta dell'agente
        INTERVIEW_PROMPT_PREFIX = (
            "Stai avendo un colloquio. Per favore combinalo con la tua personalità、Tutti i ricordi e le azioni passate，"
            "Rispondi direttamente alle seguenti domande in testo semplice。\n"
            "Rispondi alla richiesta：\n"
            "1. Rispondi direttamente in linguaggio naturale senza richiamare alcuno strumento\n"
            "2. Non restituire il formato JSON o il formato di chiamata dello strumento\n"
            "3. Non utilizzare intestazioni Markdown (come#、##、###）\n"
            "4. Rispondi alle domande una per una, ciascuna risposta termina con「domandaX：」Inizio (X è il numero della domanda）\n"
            "5. Separa le risposte a ciascuna domanda con una riga vuota\n"
            "6. Le risposte dovrebbero essere sostanziali, con almeno 2-3 frasi per ciascuna domanda\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Step 4: Chiama l'API dell'intervista reale (senza specificare la piattaforma, l'impostazione predefinita è condurre interviste simultanee su entrambe le piattaforme)）
        try:
            # Costruisci un elenco di interviste in batch (senza specificare la piattaforma, interviste a doppia piattaforma）
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt  # Utilizzo ottimizzatoprompt
                    # Se la piattaforma non è specificata, l'API accederà sia alle piattaforme Twitter che a quelle Reddit.
                })
            
            logger.info(f"Chiama l'API dell'intervista batch (doppia piattaforma）: {len(interviews_request)} unAgent")
            
            # Chiama il metodo di intervista in batch di SimulationRunner (non passare la piattaforma, intervista a doppia piattaforma）
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,  # Nessuna piattaforma specificata, intervista su doppia piattaforma
                timeout=180.0   # Le piattaforme doppie richiedono timeout più lunghi
            )
            
            logger.info(f"Ritorna l'API per interviste: {api_result.get('interviews_count', 0)} risultati, success={api_result.get('success')}")
            
            # Controlla se la chiamata API ha avuto esito positivo
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "errore sconosciuto")
                logger.warning(f"L'API Interview restituisce un errore: {error_msg}")
                result.summary = f"La chiamata API per l'intervista non è riuscita：{error_msg}。Controlla lo stato dell'ambiente di simulazione OASIS。"
                return result
            
            # Step 5: Analizzare i risultati restituiti dall'API e costruire l'oggetto AgentInterview
            # Formato di ritorno in modalità doppia piattaforma: {"twitter_0": {...}, "reddit_0": {...}, "twitter_1": {...}, ...}
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "sconosciuto")
                agent_bio = agent.get("bio", "")
                
                # Ottieni i risultati del colloquio dell'Agente su due piattaforme
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")

                # Elimina eventuali chiamate dello strumento al wrapper JSON
                twitter_response = self._clean_tool_call_response(twitter_response)
                reddit_response = self._clean_tool_call_response(reddit_response)

                # Always output dual platform tags
                twitter_text = twitter_response if twitter_response else "（La piattaforma non ha ricevuto risposta）"
                reddit_text = reddit_response if reddit_response else "（La piattaforma non ha ricevuto risposta）"
                response_text = f"【TwitterRisposta della piattaforma】\n{twitter_text}\n\n【RedditRisposta della piattaforma】\n{reddit_text}"

                # Estrai virgolette chiave (dalle risposte su entrambe le piattaforme）
                import re
                combined_responses = f"{twitter_response} {reddit_response}"

                # Pulisci il testo della risposta: rimuovi il markup、No.、Markdown In attesa di interferenze
                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'domanda\d+[：:]\s*', '', clean_text)
                clean_text = re.sub(r'【[^】]+】', '', clean_text)

                # Strategia 1 (principale）: Estrai frasi complete dal contenuto sostanziale
                sentences = re.split(r'[。！？]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                    and not s.strip().startswith(('{', 'domanda'))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "。" for s in meaningful[:3]]

                # Strategia 2 (Supplementare）: Citazioni cinesi correttamente abbinate「」Testo interno
                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[，,；;：:、]', q)][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],  # Espandi il limite di lunghezza bio
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            # L'ambiente di simulazione non è in esecuzione
            logger.warning(f"Interview API call failed (environment not running？）: {e}")
            result.summary = f"Intervista fallita：{str(e)}。L'ambiente di simulazione potrebbe essere inattivo, assicurati che l'ambiente OASIS sia in esecuzione。"
            return result
        except Exception as e:
            logger.error(f"Eccezione chiamata API intervista: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"Si è verificato un errore durante l'intervista：{str(e)}"
            return result
        
        # Step 6: Genera riepilogo dell'intervista
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(f"InterviewAgentsCompleto: Interviewed {result.interviewed_count} Agente (doppia piattaforma）")
        return result
    
    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """Pulisci il pacchetto di chiamate dello strumento JSON nelle risposte dell'agente ed estrai il contenuto effettivo"""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Caricare il file del profilo dell'agente simulato"""
        import os
        import csv
        
        # Crea il percorso del file del personaggio
        sim_dir = os.path.join(
            os.path.dirname(__file__), 
            f'../../uploads/simulations/{simulation_id}'
        )
        
        profiles = []
        
        # Dai la priorità al tentativo di leggere il formato JSON di Reddit
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f"da reddit_profiles.json caricato {len(profiles)} impostazioni personali")
                return profiles
            except Exception as e:
                logger.warning(f"leggere reddit_profiles.json fallito: {e}")
        
        # Cercando di leggere il formato CSV di Twitter
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # CSVConverti il formato in formato unificato
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "sconosciuto"
                        })
                logger.info(f"da twitter_profiles.csv caricato {len(profiles)} impostazioni personali")
                return profiles
            except Exception as e:
                logger.warning(f"leggere twitter_profiles.csv fallito: {e}")
        
        return profiles
    
    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """
        Utilizza LLM per selezionare le persone da intervistareAgent
        
        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
                - selected_agents: Elenco completo delle informazioni dell'agente selezionato
                - selected_indices: Seleziona l'elenco dell'indice dell'Agente (utilizzato per le chiamate API）
                - reasoning: Motivo della selezione
        """
        
        # Elenco di riepilogo dell'agente di creazione
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "sconosciuto"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)
        
        system_prompt = """Sei un pianificatore di interviste professionale. Il tuo compito è selezionare l'intervistato più adatto dall'elenco simulato degli agenti in base alle esigenze del colloquio.

criteri di selezione：
1. Agentla cui identità/carriera è rilevante per l'argomento del colloquio
2. AgentPuò contenere prospettive uniche o preziose
3. Scegliere prospettive diverse (ad es. sostenitori、Opposizione、partito neutrale、Professionisti ecc.）
4. Dai la priorità ai ruoli direttamente correlati all'evento

Restituisce il formato JSON：
{
    "selected_indices": [Selezionare l'elenco dell'indice dell'Agente],
    "reasoning": "Motivo della selezione"
}"""

        user_prompt = f"""Requisiti del colloquio：
{interview_requirement}

Sfondo analogico：
{simulation_requirement if simulation_requirement else "Non fornito"}

Elenco agenti selezionabili (totale{len(agent_summaries)}un）：
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Seleziona il massimo{max_agents}Quale Agente è più adatto per il colloquio e spiega i motivi della selezione。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "Selezione automatica in base alla pertinenza")
            
            # Ottieni informazioni complete sull'agente selezionato
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            
            return selected_agents, valid_indices, reasoning
            
        except Exception as e:
            logger.warning(f"LLMImpossibile selezionare l'agente, utilizza la selezione predefinita: {e}")
            # Downgrade: seleziona i primi N
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "Utilizza la strategia di selezione predefinita"
    
    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """Genera domande per l'intervista utilizzando LLM"""
        
        agent_roles = [a.get("profession", "sconosciuto") for a in selected_agents]
        
        system_prompt = """Sei un reporter/intervistatore professionista. In base alle esigenze dell'intervista, genera 3-5 domande approfondite per l'intervista.

Richiesta di domande：
1. Sono incoraggiate domande aperte e risposte dettagliate
2. Potrebbero esserci risposte diverse per ruoli diversi
3. coprire i fatti、punto di vista、Sentimenti e altre dimensioni
4. Il linguaggio è naturale, come una vera intervista
5. Ogni domanda deve contenere non più di 50 parole ed essere concisa e chiara.
6. Chiedi direttamente senza includere note di sottofondo o prefissi

Restituisce il formato JSON：{"questions": ["domanda1", "domanda2", ...]}"""

        user_prompt = f"""Requisiti del colloquio：{interview_requirement}

Sfondo analogico：{simulation_requirement if simulation_requirement else "Non fornito"}

ruolo dell'intervistato：{', '.join(agent_roles)}

Si prega di generare 3-5 domande per l'intervista。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            return response.get("questions", [f"Circa{interview_requirement}，cosa ne pensi?？"])
            
        except Exception as e:
            logger.warning(f"Impossibile generare le domande dell'intervista: {e}")
            return [
                f"Circa{interview_requirement}，qual è il tuo punto di vista?？",
                "Che effetto ha tutto questo su di te o sul gruppo che rappresenti?？",
                "Come pensi che questo problema dovrebbe essere risolto o migliorato?？"
            ]
    
    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """Genera riepilogo dell'intervista"""
        
        if not interviews:
            return "Nessuna intervista completata"
        
        # Raccogli tutte le interviste
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"【{interview.agent_name}（{interview.agent_role}）】\n{interview.response[:500]}")
        
        system_prompt = """Sei un redattore di notizie professionista. Si prega di generare un riepilogo dell'intervista basato sulle risposte di più intervistati.

Requisiti astratti：
1. Estrarre i principali punti di vista di tutte le parti
2. Evidenziare il consenso e le differenze di opinione
3. Evidenzia citazioni preziose
4. Sii obiettivo e neutrale, non schierarti
5. Controllo entro 1000 parole

Vincoli di formato (devono essere rispettati):
- Utilizza paragrafi di testo normale con righe vuote che separano le diverse sezioni
- Non utilizzare intestazioni Markdown (come#、##、###）
- Non utilizzare linee di divisione (ad es.---、***）
- Usa le virgolette cinesi quando citi le parole originali dell'intervistato「」
- Puoi utilizzare **grassetto** per contrassegnare le parole chiave, ma non utilizzare altra sintassi Markdown"""

        user_prompt = f"""Argomenti dell'intervista：{interview_requirement}

Contenuto dell'intervista：
{"".join(interview_texts)}

Si prega di generare un riepilogo dell'intervista。"""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary
            
        except Exception as e:
            logger.warning(f"Impossibile generare il riepilogo dell'intervista: {e}")
            # Downgrade: giunzione semplice
            return f"Intervistato in totale{len(interviews)}intervistati, compresi：" + "、".join([i.agent_name for i in interviews])
