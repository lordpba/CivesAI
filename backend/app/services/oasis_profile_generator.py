"""
OASIS Agent Profilegeneratore
Converti le entità nella mappa Zep nel formato Profilo Agente richiesto dalla piattaforma di simulazione OASIS

Ottimizzazione e miglioramento：
1. Chiama la funzione di ricerca Zep per arricchire due volte le informazioni sul nodo
2. Ottimizza le parole rapide per generare caratteri molto dettagliati
3. Distinguere tra entità personali ed entità astratte di gruppo
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader
from .calibration_service import CalibrationService

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profilestruttura dei dati"""
    # Campi comuni
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # Campi opzionali: stile Reddit
    karma: int = 1000
    
    # Campi facoltativi - Stile Twitter
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # Informazioni aggiuntive sul personaggio
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # Informazioni sull'entità di origine
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    nuts2_region: Optional[str] = None
    calibration_summary: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Converti nel formato della piattaforma Reddit"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS La libreria richiede che il campo sia denominato nome utente (senza trattino basso）
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # Aggiungi ulteriori informazioni sulla personalità (se presenti）
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Converti nel formato della piattaforma Twitter"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS La libreria richiede che il campo sia denominato nome utente (senza trattino basso）
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # Aggiungi ulteriori informazioni sulla personalità
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Converti nel formato dizionario completo"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "nuts2_region": self.nuts2_region,
            "calibration_summary": self.calibration_summary,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profilegeneratore
    
    Converti le entità nella mappa Zep nei profili agente richiesti per le simulazioni OASIS
    
    Funzionalità di ottimizzazione：
    1. Chiama la funzione di ricerca della mappa Zep per ottenere un contesto più ricco
    2. Genera personaggi molto dettagliati (comprese le informazioni di base、Esperienza di carriera、Tratti caratteriali、comportamento sui social media, ecc.）
    3. Distinguere tra entità personali ed entità astratte di gruppo
    """
    
    # MBTIElenco tipi
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # Elenco dei paesi comuni
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Entità di tipo personale (necessità di generare personalità specifica）
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Entità di tipo gruppo/organizzazione (è necessario generare una persona rappresentativa del gruppo）
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None,
        nuts2_region: Optional[str] = None,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY Non configurato")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # ZepClient utilizzato per recuperare un contesto ricco
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id
        self.nuts2_region = nuts2_region
        self.calibration = CalibrationService()
        
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"ZepInizializzazione del client non riuscita: {e}")
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True,
        nuts2_region: Optional[str] = None,
    ) -> OasisAgentProfile:
        """
        Genera dall'entità ZepOASIS Agent Profile
        
        Args:
            entity: Zepnodo entità
            user_id: ID utente (perOASIS）
            use_llm: Se utilizzare LLM per generare personaggi dettagliati
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # Informazioni di base
        name = entity.name
        user_name = self._generate_username(name)
        
        # Costruisci informazioni contestuali
        context = self._build_entity_context(entity)
        region = nuts2_region or self.nuts2_region
        calibration_summary = None

        if region and self.calibration.is_loaded:
            calibration_summary = self.calibration.build_agent_calibration_context(region)
            if calibration_summary:
                context = f"{context}\n\n{calibration_summary}"
        
        if use_llm:
            # Utilizza LLM per generare personaggi dettagliati
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context,
                nuts2_region=region
            )
        else:
            # Utilizza le regole per generare personaggi di base
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
            nuts2_region=region,
            calibration_summary=calibration_summary,
        )
    
    def _generate_username(self, name: str) -> str:
        """Genera nome utente"""
        # Rimuovi i caratteri speciali e convertili in minuscolo
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Aggiungi un suffisso casuale per evitare duplicazioni
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Ottieni informazioni dettagliate sulle entità utilizzando le funzionalità di ricerca ibrida di Zep Graph
        
        Zep non dispone di un'interfaccia di ricerca ibrida integrata. È necessario cercare bordi e nodi separatamente e quindi unire i risultati.
        Effettua ricerche simultanee utilizzando richieste parallele per migliorare l'efficienza。
        
        Args:
            entity: oggetto nodo entità
            
        Returns:
            contienefacts, node_summaries, contextdizionario
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # Deve averegraph_idcercare
        if not self.graph_id:
            logger.debug(f"Salta recupero Zep: non impostatograph_id")
            return results
        
        comprehensive_query = f"Circa{entity_name}Tutte le informazioni di、Attività、evento、relazioni e contesto"
        
        def search_edges():
            """Bordi di ricerca (fatti/relazioni) - con meccanismo di ripetizione"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"ZepRicerca dei bordi {attempt + 1} fallito: {str(e)[:80]}, Nuovo tentativo...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"ZepCerca in {max_retries} Ancora fallito dopo i tentativi: {e}")
            return None
        
        def search_nodes():
            """Nodi di ricerca (digest di entità) - con meccanismo di ripetizione"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"ZepRicerca nodo n. {attempt + 1} fallito: {str(e)[:80]}, Nuovo tentativo...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"ZepRicerca nodo dentro {max_retries} Ancora fallito dopo i tentativi: {e}")
            return None
        
        try:
            # Esegui ricerche di bordi e nodi in parallelo
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # Ottieni risultati
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # Elaborazione dei risultati della ricerca edge
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # Elaborare i risultati della ricerca del nodo
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"enti correlati: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # Costruisci un contesto completo
            context_parts = []
            if results["facts"]:
                context_parts.append("informazioni fattuali:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("enti correlati:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"ZepRicerca mista completata: {entity_name}, Ottieni {len(results['facts'])} fatti, {len(results['node_summaries'])} nodi correlati")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"ZepTimeout di recupero ({entity_name})")
        except Exception as e:
            logger.warning(f"ZepRecupero non riuscito ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Costruisci informazioni contestuali complete per un'entità
        
        includere：
        1. Informazioni collaterali sull'entità stessa (fatti）
        2. Dettagli del nodo associato
        3. ZepMescola le ricche informazioni recuperate
        """
        context_parts = []
        
        # 1. Aggiungi informazioni sugli attributi dell'entità
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Proprietà dell'entità\n" + "\n".join(attrs))
        
        # 2. Aggiungi informazioni collaterali rilevanti (fatti/relazioni）
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # Nessun limite alla quantità
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (enti correlati)")
                    else:
                        relationships.append(f"- (enti correlati) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Fatti e relazioni rilevanti\n" + "\n".join(relationships))
        
        # 3. Aggiungi dettagli sui nodi associati
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # Nessun limite alla quantità
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # Filtra i tag predefiniti
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### Informazioni sull'entità correlata\n" + "\n".join(related_info))
        
        # 4. Utilizza la ricerca ibrida Zep per ottenere informazioni più complete
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # Deduplicazione: esclude i fatti esistenti
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### ZepInformazioni fattuali recuperate\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### ZepNodi correlati recuperati\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Determina se si tratta di un'entità di tipo personale"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """Determina se si tratta di un'entità di tipo gruppo/organizzazione"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        nuts2_region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Utilizza LLM per generare personaggi altamente dettagliati
        
        Distinguere in base al tipo di entità:
        - Entità personale: genera impostazioni di carattere specifiche
        - Gruppo/entità organizzativa: genera impostazioni dell'account del rappresentante
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context, nuts2_region
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context, nuts2_region
            )

        # Prova più build fino al successo o al raggiungimento del numero massimo di tentativi
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Abbassa la temperatura ogni volta che riprovi
                    # Non impostatomax_tokens，Lascia che LLM giochi liberamente
                )
                
                content = response.choices[0].message.content
                
                # Controlla se troncato（finish_reasonNo'stop'）
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLML'output è troncato (attempt {attempt+1}), provare a sistemare...")
                    content = self._fix_truncated_json(content)
                
                # prova ad analizzareJSON
                try:
                    result = json.loads(content)
                    
                    # Convalida i campi obbligatori
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name}è un{entity_type}。"
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSONAnalisi non riuscita (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # provare a sistemareJSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLMchiamata fallita (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # backoff esponenziale
        
        logger.warning(f"LLMImpossibile generare il carattere（{max_attempts}tentativi）: {last_error}, Genera utilizzando le regole")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Correzione del JSON troncato (l'output eramax_tokensLimita il troncamento）"""
        import re
        
        # Se JSON viene troncato, prova a chiuderlo
        content = content.strip()
        
        # Contare le parentesi non chiuse
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Controlla se c'è una stringa non chiusa
        # Controllo semplice: se non è presente una virgola o una parentesi di chiusura dopo l'ultima virgoletta, la stringa potrebbe essere troncata
        if content and content[-1] not in '",}]':
            # Prova a chiudere la corda
            content += '"'
        
        # closing bracket
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Prova a riparare ciò che è rottoJSON"""
        import re
        
        # 1. Per prima cosa prova a correggere il caso troncato
        content = self._fix_truncated_json(content)
        
        # 2. Prova ad estrarre la parte JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Gestione dei caratteri di nuova riga nelle stringhe
            # Trova tutti i valori stringa e sostituisci i ritorni a capo al loro interno
            def fix_string_newlines(match):
                s = match.group(0)
                # Sostituisci i ritorni a capo effettivi all'interno di una stringa con spazi
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Sostituisci gli spazi aggiuntivi
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # Corrisponde al valore della stringa JSON
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. prova ad analizzare
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. Se il problema persiste, prova una soluzione più radicale
                try:
                    # Rimuovi tutti i caratteri di controllo
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Sostituisci tutti gli spazi bianchi consecutivi
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Prova a estrarre alcune informazioni dal contenuto
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # potrebbe essere troncato
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name}è un{entity_type}。")
        
        # Se viene estratto contenuto significativo, contrassegnarlo come corretto
        if bio_match or persona_match:
            logger.info(f"Informazioni parziali estratte da JSON corrotto")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Fallimento completo, ritorno alle infrastrutture
        logger.warning(f"JSONRiparazione fallita, ritorno all'infrastruttura")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name}è un{entity_type}。"
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Ottieni parole tempestive dal sistema"""
        base_prompt = "Sei un esperto nella generazione di personaggi sui social media. Genera dettagliato、I personaggi reali vengono utilizzati per la simulazione dell'opinione pubblica,Ripristinare la realtà esistente nella massima misura possibile. È necessario restituire un formato JSON valido, tutti i valori di stringa non possono contenere caratteri di fine riga senza caratteri di escape. Per favore usate l'italiano (Italiano) Generare contenuti e integrarli nel reale contesto sociale dell’Italia: ad es. un cittadino o ente nel Comune (es. Paperopoli), la cui vita è regolamentata dal sindaco e dalla giunta, che paga tasse come la TARI, ed è influenzato dall'opinione pubblica locale."
        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        nuts2_region: Optional[str] = None,
    ) -> str:
        """Costruisci suggerimenti dettagliati sulla personalità per le entità personali"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Nessuno"
        context_str = context[:3000] if context else "nessun contesto aggiuntivo"
        region_note = f"\nRegione NUTS-2 di riferimento: {nuts2_region}" if nuts2_region else ""
        
        return f"""Genera profili utente dettagliati della comunità locale per le entità（Contesto: Comune Italiano, es. Paperopoli）,Ripristinare la realtà esistente nella massima misura possibile.

Nome dell'entità: {entity_name}
Tipo di entità: {entity_type}
Riepilogo dell'entità: {entity_summary}
Proprietà dell'entità: {attrs_str}

informazioni contestuali:
{context_str}
{region_note}

Genera JSON con i seguenti campi:

1. bio: Introduzione ai social media, 200 parole
2. persona: La descrizione dettagliata dei caratteri (2000 parole di testo semplice) deve includere:
   - Informazioni di base (età、Carriera、Background educativo、posizione)
   - Background del personaggio (esperienze importanti、relazioni sociali、tratti identitari：come Partita IVA, Pensionato INPS, Studente Fuori Sede, ecc.）
   - Tratti della personalità (tipo MBTI、carattere fondamentale、espressione emotiva)
   - Comportamento sui social media (frequenza di pubblicazione、Preferenze di contenuto、stile interattivo、caratteristiche del linguaggio)
   -Posizione (atteggiamento verso l'argomento)、Contenuti che potrebbero offendere/toccare)
   - Caratteristiche uniche (mantra、esperienza speciale、hobby personali)
   - Memoria personale (una parte importante della personalità, dovrebbe introdurre la relazione tra l'individuo e l'evento, nonché le azioni e le reazioni dell'individuo nell'evento）
3. age: etàNumero (deve essere un numero intero）
4. gender: Il genere deve essere in inglese: "male" o "female"
5. mbti: MBTITipo (comeINTJ、ENFPAspetta）
6. country: Paese (utilizzare il cinese, ad es."Cina"）
7. profession: Carriera
8. interested_topics: serie di argomenti interessanti
9. nuts2_region: codice NUTS-2 di riferimento, se disponibile
10. calibration_summary: breve sintesi del profilo regionale e delle fonti usate

importante:
- Tutti i valori dei campi devono essere stringhe o numeri, non utilizzare caratteri di fine riga
- la persona deve essere una descrizione testuale coerente
- Output tutto il testo in italiano (tranne il campo genere che deve essere in inglese maschile/femminile)
- Il contenuto deve essere coerente con le informazioni sull'entità
- L'età deve essere un numero intero valido e il sesso deve esserlo"male"o"female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
        nuts2_region: Optional[str] = None,
    ) -> str:
        """Costruire suggerimenti personali dettagliati per gruppi/entità istituzionali"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "Nessuno"
        context_str = context[:3000] if context else "nessun contesto aggiuntivo"
        region_note = f"\nRegione NUTS-2 di riferimento: {nuts2_region}" if nuts2_region else ""
        
        return f"""Genera impostazioni account ufficiali dettagliate per entità istituzionali/di gruppo（Contesto: Pubblica Amministrazione / Comune Italiano, es. Paperopoli）,Ripristinare la realtà esistente nella massima misura possibile.

Nome dell'entità: {entity_name}
Tipo di entità: {entity_type}
Riepilogo dell'entità: {entity_summary}
Proprietà dell'entità: {attrs_str}

informazioni contestuali:
{context_str}
{region_note}

Genera JSON con i seguenti campi:

1. bio: Presentazione ufficiale dell'account, 200 parole, professionale e dignitosa
2. persona: Deve includere una descrizione dettagliata delle impostazioni dell'account (2000 parole di testo semplice).:
   - Informazioni di base dell'organizzazione (nome formale、Natura istituzionale、Contesto dell'istituzione、Funzioni principali)
   - Posizionamento del conto (tipo di conto、pubblico di destinazione、Funzioni principali)
   - Stile parlato (caratteristiche del linguaggio、Espressioni comuni、Argomenti tabù)
   - Pubblicare le caratteristiche del contenuto (tipo di contenuto、Frequenza di rilascio、periodo di tempo attivo)
   - Posizione (posizione ufficiale su argomenti fondamentali)、Come gestire le controversie)
   - Istruzioni particolari (ritratto del gruppo rappresentato)、abitudini operative)
   - Memoria istituzionale (una parte importante della personalità dell'organizzazione, che dovrebbe introdurre la relazione tra l'organizzazione e l'evento, nonché le azioni e le reazioni dell'organizzazione all'evento)）
3. age: Risolto il problema con la compilazione di 30 (età virtuale dell'account dell'organizzazione）
4. gender: Riempimento fisso"other"（I conti istituzionali utilizzano other per indicare soggetti non individuali）
5. mbti: MBTITipo, utilizzato per descrivere lo stile dell'account. Ad esempio, ISTJ sta per rigoroso e conservatore.
6. country: Paese (utilizzare il cinese, ad es."Cina"）
7. profession: Descrizione della funzione organizzativa
8. interested_topics: Matrice dell'area di messa a fuoco
9. nuts2_region: codice NUTS-2 di riferimento, se disponibile
10. calibration_summary: sintesi del profilo regionale, delle fonti e della logica di calibrazione

importante:
- Tutti i valori dei campi devono essere stringhe o numeri, non sono consentiti valori null
- la persona deve essere una descrizione testuale coerente, non utilizzare interruzioni di riga
- Visualizza tutto il testo in italiano (eccetto il campo relativo al genere che deve essere in inglese"other"）
- ageDeve essere un numero intero 30, il genere deve essere una stringa"other"
- Gli interventi dei resoconti istituzionali devono conformarsi alla loro identità e al loro posizionamento"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Utilizza le regole per generare personaggi di base"""
        
        # Genera personaggi diversi in base ai tipi di entità
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # Era virtuale istituzionale
                "gender": "other",  # Uso istituzionaleother
                "mbti": "ISTJ",  # Stile istituzionale: Rigoroso e conservatore
                "country": "Cina",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # Era virtuale istituzionale
                "gender": "other",  # Uso istituzionaleother
                "mbti": "ISTJ",  # Stile istituzionale: Rigoroso e conservatore
                "country": "Cina",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # Persona predefinita
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Imposta l'ID mappa per la ricerca Zep"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit",
        nuts2_region: Optional[str] = None,
    ) -> List[OasisAgentProfile]:
        """
        Genera profili agente da entità in batch (supporta la generazione parallela）
        
        Args:
            entities: Elenco entità
            use_llm: Se utilizzare LLM per generare personaggi dettagliati
            progress_callback: Funzione di callback di avanzamento (current, total, message)
            graph_id: ID mappa, utilizzato per la ricerca Zep per ottenere un contesto più ricco
            parallel_count: Numero di build parallele, predefinito5
            realtime_output_path: Percorso del file da scrivere in tempo reale (se fornito, verrà scritto ogni volta che ne verrà generato uno）
            output_platform: Formato della piattaforma di output ("reddit" o "twitter")
            
        Returns:
            Agent Profileelenco
        """
        import concurrent.futures
        from threading import Lock
        
        # impostazionigraph_idUtilizzato per il recupero Zep
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # L'elenco preassegnato mantiene l'ordine
        completed_count = [0]  # Utilizzare gli elenchi per la modifica nelle chiusure
        lock = Lock()
        
        # Funzione ausiliaria per la scrittura di file in tempo reale
        def save_profiles_realtime():
            """Salva i profili generati su file in tempo reale"""
            if not realtime_output_path:
                return
            
            with lock:
                # Filtra generato profiles
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit JSON Formato
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV Formato
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"Impossibile salvare i profili in tempo reale: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Genera funzioni lavorative per un singolo profilo"""
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm,
                    nuts2_region=nuts2_region,
                )
                
                # Output in tempo reale della personalità generata sulla console e sui registri
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"Genera entità {entity.name} La persona ha fallito: {str(e)}")
                # creare una baseprofile
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                    nuts2_region=nuts2_region,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"Inizio generazione parallela {total} profili agenti ({parallel_count} thread)...")
        print(f"\n{'='*60}")
        print(f"Inizio generazione profili - Entità totali: {total}, Thread: {parallel_count}")
        print(f"{'='*60}\n")
        
        # Esecuzione parallela utilizzando il pool di thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Invia tutte le attività
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # Raccogli i risultati
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # Scrivi file in tempo reale
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"Completato {current}/{total}: {entity.name}（{entity_type}）"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} Usa un personaggio alternativo: {error}")
                    else:
                        logger.info(f"[{current}/{total}] Personaggio generato con successo: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"Gestire le entità {entity.name} L'eccezione si verifica quando: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # Scrivi file in tempo reale (anche con avatar alternativi)）
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"Generazione del personaggio completata！simbiosi {len([p for p in profiles if p])} unAgent")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Invia la personalità generata alla console in tempo reale (contenuto completo, non troncato)）"""
        separator = "-" * 70
        
        # Costruisci il contenuto di output completo (senza troncamento）
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'Nessuno'
        
        output_lines = [
            f"\n{separator}",
            f"[Generato] {entity_name} ({entity_type})",
            f"{separator}",
            f"Nome utente: {profile.user_name}",
            f"",
            f"【Introduzione】",
            f"{profile.bio}",
            f"",
            f"【Design dettagliato dei personaggi】",
            f"{profile.persona}",
            f"",
            f"【Proprietà di base】",
            f"età: {profile.age} | genere: {profile.gender} | MBTI: {profile.mbti}",
            f"Carriera: {profile.profession} | paese: {profile.country}",
            f"Argomenti interessanti: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # Solo output sulla console (per evitare duplicazioni, il logger non genererà più il contenuto completo)）
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Salva profilo su file (scegli il formato corretto in base alla piattaforma)
        
        Requisiti del formato della piattaforma OASIS：
        - Twitter: CSVFormato
        - Reddit: JSONFormato
        
        Args:
            profiles: Profileelenco
            file_path: percorso del file
            platform: tipo di piattaforma ("reddit" o "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Salva il profilo Twitter in formato CSV (conforme ai requisiti ufficiali di OASIS)
        
        Campi CSV richiesti da OASIS Twitter：
        - user_id: ID utente (a partire da 0 secondo l'ordine CSV）
        - name: Nome reale dell'utente
        - username: Nome utente nel sistema
        - user_char: Descrizione dettagliata del personaggio (inserita nei prompt del sistema LLM per guidare il comportamento dell'agente）
        - description: Un breve profilo pubblico (visualizzato nella pagina del profilo utente）
        
        user_char vs description differenza：
        - user_char: L'uso interno, suggerisce il sistema LLM, determina il modo in cui l'agente pensa e agisce
        - description: Display esterno, profilo visibile ad altri utenti
        """
        import csv
        
        # Assicurati che l'estensione del file sia.csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Scrivi l'intestazione richiesta da OASIS
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # Scrivi la riga di dati
            for idx, profile in enumerate(profiles):
                # user_char: Personalità completa (bio + persona), utilizzata per i suggerimenti del sistema LLM
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Gestione dei caratteri di nuova riga (sostituiti da spazi in CSV）
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: Breve introduzione, per display esterno
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: ordine a partire da 0ID
                    profile.name,           # name: vero nome
                    profile.user_name,      # username: Nome utente
                    user_char,              # user_char: Set di caratteri completo (utilizzato internamente da LLM）
                    description             # description: Breve introduzione (display esterno）
                ]
                writer.writerow(row)
        
        logger.info(f"salvato {len(profiles)} Profilo Twitter a {file_path} (OASIS CSVFormato)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        Standardizza il campo relativo al genere al formato inglese richiesto da OASIS
        
        Requisiti di OASIS: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        # Mappatura cinese
        gender_map = {
            "maschio": "male",
            "femmina": "female",
            "istituzione": "other",
            "Altri": "other",
            # Già disponibile in inglese
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Salva il profilo Reddit in formato JSON
        
        Utilizzare con to_reddit_format() Formato coerente per garantire che OASIS possa leggerlo correttamente.
        deve contenere user_id campo, che è OASIS agent_graph.get_agent() chiave corrispondente！
        
        Campi obbligatori：
        - user_id: ID utente (numero intero, utilizzato per la corrispondenza initial_posts dentro poster_agent_id）
        - username: Nome utente
        - name: nome visualizzato
        - bio: Introduzione
        - persona: Design dettagliato dei personaggi
        - age: età (intero）
        - gender: "male", "female", o "other"
        - mbti: MBTIDigitare
        - country: paese
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Utilizzare con to_reddit_format() formato coerente
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Chiave: deve contenere user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASISCampi obbligatori: assicurati che tutti abbiano valori predefiniti
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "Cina",
            }
            
            # campi facoltativi
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"salvato {len(profiles)} Profilo Reddit a {file_path} (JSONformato, inclusouser_idCampo)")
    
    # Mantieni i vecchi nomi dei metodi come alias per mantenere la compatibilità con le versioni precedenti
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Deprecato] Per favore usa save_profiles() metodo"""
        logger.warning("save_profiles_to_jsonDeprecato, si prega di utilizzaresave_profilesmetodo")
        self.save_profiles(profiles, file_path, platform)

