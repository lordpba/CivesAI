"""
ZepServizio di lettura e filtraggio delle entità
Leggi i nodi dal grafico Zep e filtra i nodi che corrispondono ai tipi di entità predefiniti
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_entity_reader')

# per tipi di restituzione generici
T = TypeVar('T')


@dataclass
class EntityNode:
    """Struttura dati del nodo entità"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # Informazioni collaterali rilevanti
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # Altre informazioni sul nodo correlate
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """Ottieni il tipo di entità (escluso il tag Entity predefinito）"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Raccolta di entità filtrate"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    ZepServizio di lettura e filtraggio delle entità
    
    Funzioni principali：
    1. Leggi tutti i nodi dal grafico Zep
    2. Filtra i nodi che corrispondono ai tipi di entità predefiniti (le etichette non sono solo nodi di entità）
    3. Ottieni le informazioni sul bordo rilevante e sul nodo associato di ciascuna entità
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY Non configurato")
        
        self.client = Zep(api_key=self.api_key)
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        Chiamata API Zep con meccanismo di ripetizione
        
        Args:
            func: La funzione da eseguire (lambda senza parametri oppurecallable）
            operation_name: Nome dell'operazione, utilizzato per la registrazione
            max_retries: Numero massimo di tentativi (predefinito 3 volte, ovvero fino a 3 tentativi）
            initial_delay: Secondi di ritardo iniziali
            
        Returns:
            APIRisultato della chiamata
        """
        last_exception = None
        delay = initial_delay
        
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
                    delay *= 2  # backoff esponenziale
                else:
                    logger.error(f"Zep {operation_name} dentro {max_retries} Ancora fallito dopo i tentativi: {str(e)}")
        
        raise last_exception
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Ottieni tutti i nodi del grafico (ottieni in pagine）

        Args:
            graph_id: AtlanteID

        Returns:
            elenco dei nodi
        """
        logger.info(f"Ottieni la mappa {graph_id} tutti i nodi di...")

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"Ottenuto in totale {len(nodes_data)} nodi")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Ottieni tutti i bordi del grafico (entra in pagine）

        Args:
            graph_id: AtlanteID

        Returns:
            elenco dei bordi
        """
        logger.info(f"Ottieni la mappa {graph_id} tutti i lati di...")

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"Ottenuto in totale {len(edges_data)} bordo della striscia")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        Ottieni tutti i bordi rilevanti del nodo specificato (con meccanismo di ripetizione）
        
        Args:
            node_uuid: nodoUUID
            
        Returns:
            elenco dei bordi
        """
        try:
            # Chiama utilizzando il meccanismo di riprovaZep API
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"Ottieni i bordi dei nodi(node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"Ottieni nodo {node_uuid} Il bordo fallisce: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        Filtra i nodi che corrispondono ai tipi di entità predefiniti
        
        Logica del filtro:
        - Se il nodo ha una sola Etichette"Entity"，Indica che questa entità non è conforme al nostro tipo predefinito, salta
        - Se le etichette del nodo contengono qualcosa di diverso da"Entity"e"Node"I tag diversi dalla descrizione corrispondono al tipo predefinito e sono riservati
        
        Args:
            graph_id: AtlanteID
            defined_entity_types: Elenco di tipi di entità predefiniti (facoltativo, mantieni questi tipi solo se forniti）
            enrich_with_edges: Se ottenere le informazioni sui bordi rilevanti di ciascuna entità
            
        Returns:
            FilteredEntities: Raccolta di entità filtrate
        """
        logger.info(f"Inizia a filtrare gli spettri {graph_id} entità...")
        
        # Ottieni tutti i nodi
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # Ottieni tutti i bordi (per le successive ricerche di associazioni）
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # Costruisci una mappatura dell'UUID del nodo sui dati del nodo
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # Filtra le entità che soddisfano i criteri
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # Logica di filtraggio: le etichette devono contenere"Entity"e"Node"tag all'esterno
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if not custom_labels:
                # Solo etichette predefinite, salta
                continue
            
            # Se viene specificato un tipo predefinito, verifica la corrispondenza
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # Crea oggetto nodo entità
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # Ottieni bordi e nodi correlati
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # Ottieni informazioni di base sui nodi associati
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"Screening completato: nodo totale {total_count}, Idoneo {len(filtered_entities)}, "
                   f"Tipo di entità: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        Ottieni una singola entità e il suo contesto completo (bordi e nodi associati, con meccanismo di ripetizione）
        
        Args:
            graph_id: AtlanteID
            entity_uuid: EntitàUUID
            
        Returns:
            EntityNodeoNone
        """
        try:
            # Utilizza il meccanismo di ripetizione per ottenere i nodi
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"Ottieni i dettagli del nodo(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # Ottieni i bordi di un nodo
            edges = self.get_node_edges(entity_uuid)
            
            # Get all nodes for association lookup
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # Bordi e nodi correlati al processo
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # Ottieni informazioni sul nodo associato
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"Ottieni entità {entity_uuid} fallito: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        Ottieni tutte le entità del tipo specificato
        
        Args:
            graph_id: AtlanteID
            entity_type: Tipo di entità (es. "Student", "PublicFigure" Aspetta）
            enrich_with_edges: Se ottenere informazioni collaterali rilevanti
            
        Returns:
            Elenco entità
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities


