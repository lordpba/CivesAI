"""
Generatore intelligente di configurazione della simulazione
Utilizza LLM in base alle esigenze di simulazione、Contenuto del documento、Le informazioni spettrali generano automaticamente parametri di simulazione dettagliati
Realizza l'automazione completa, senza bisogno di impostare manualmente i parametri

Adotta una strategia di generazione passo-passo per evitare errori causati dalla generazione simultanea di contenuti troppo lunghi：
1. Configurazione del tempo di creazione
2. Genera la configurazione dell'evento
3. Genera la configurazione dell'agente in batch
4. Genera la configurazione della piattaforma
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader
from .calibration_service import CalibrationService

logger = get_logger('mirofish.simulation_config')

# Configurazione del tempo di lavoro e di riposo in Cina (ora di Pechino）
CHINA_TIMEZONE_CONFIG = {
    # Ore notturne (quasi nessuna attività)）
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # Periodo mattutino (risveglio graduale）
    "morning_hours": [6, 7, 8],
    # Ore Lavorative
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # Picco serale (più attivo）
    "peak_hours": [19, 20, 21, 22],
    # Periodo notturno (attività ridotta）
    "night_hours": [23],
    # coefficiente di attività
    "activity_multipliers": {
        "dead": 0.05,      # Quasi nessuno la mattina presto
        "morning": 0.4,    # Diventa più attivo al mattino
        "work": 0.7,       # Orario di lavoro moderato
        "peak": 1.5,       # picco serale
        "night": 0.5       # caduta a tarda notte
    }
}


@dataclass
class AgentActivityConfig:
    """Configurazione dell'attività di un singolo Agent"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str
    
    # Configurazione dell'attività (0.0-1.0)
    activity_level: float = 0.5  # Attività complessiva
    
    # Frequenza del discorso (numero previsto di interventi all'ora）
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0
    
    # Periodo di tempo attivo (formato 24 ore，0-23）
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))
    
    # Velocità di risposta (ritardo di risposta agli eventi hot, unità: minuti di simulazione）
    response_delay_min: int = 5
    response_delay_max: int = 60
    
    # Tendenza Emotiva (-1.0Arrivo1.0，negativo in positivo)
    sentiment_bias: float = 0.0
    
    # stance (atteggiamento verso un particolare argomento)）
    stance: str = "neutral"  # supportive, opposing, neutral, observer
    
    # Peso di influenza (determina la probabilità che il suo discorso venga visto da altri agenti)）
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """Configurazione della simulazione del tempo (basata sulle abitudini di lavoro e di riposo dei cinesi）"""
    # Durata totale della simulazione (ore di simulazione）
    total_simulation_hours: int = 72  # La simulazione predefinita è 72 ore (3 giorni）
    
    # Tempo rappresentato in ogni round (minuti di simulazione): l'impostazione predefinita è 60 minuti (1 ora) per accelerare il flusso del tempo
    minutes_per_round: int = 60
    
    # Intervallo del numero di agenti attivati all'ora
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20
    
    # Ore di punta (19-22, l'orario più attivo per i cinesi）
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5
    
    # Nelle ore basse (dalle 0 alle 5, quasi nessuno è attivo)）
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Attività molto bassa al mattino presto
    
    # Ore Mattutine
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4
    
    # Ore Lavorative
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """configurazione dell'evento"""
    # Evento iniziale (evento che attiva l'avvio della simulazione）
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)
    
    # Eventi temporizzati (eventi attivati in un momento specifico）
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)
    
    # parole chiave di argomenti caldi
    hot_topics: List[str] = field(default_factory=list)
    
    # Direzione di orientamento dell'opinione pubblica
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Configurazione specifica della piattaforma"""
    platform: str  # twitter or reddit
    
    # Peso dell'algoritmo consigliato
    recency_weight: float = 0.4  # freschezza del tempo
    popularity_weight: float = 0.3  # Calore
    relevance_weight: float = 0.3  # Rilevanza
    
    # Soglia di diffusione virale (quante interazioni vengono raggiunte prima che si attivi la diffusione)）
    viral_threshold: int = 10
    
    # La forza dell’effetto camera di risonanza (il grado in cui opinioni simili si uniscono）
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Configurazione completa dei parametri di simulazione"""
    # Informazioni di base
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    nuts2_region: Optional[str] = None
    calibration_profile: Optional[Dict[str, Any]] = None
    
    # Configurazione dell'ora
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)
    
    # AgentElenco di configurazione
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)
    
    # configurazione dell'evento
    event_config: EventConfig = field(default_factory=EventConfig)
    
    # Configurazione della piattaforma
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None
    
    # LLMConfigurazione
    llm_model: str = ""
    llm_base_url: str = ""
    
    # Genera metadati
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLMspiegazione del ragionamento
    
    def to_dict(self) -> Dict[str, Any]:
        """Converti in dizionario"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "nuts2_region": self.nuts2_region,
            "calibration_profile": self.calibration_profile,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Converti in stringa JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Generatore intelligente di configurazione della simulazione
    
    Utilizza LLM per analizzare i requisiti di simulazione、Contenuto del documento、Informazioni sull'entità del grafico,
    Genera automaticamente configurazioni ottimali dei parametri di simulazione
    
    Adottare una strategia di generazione passo dopo passo：
    1. Configurazione del tempo di creazione e configurazione degli eventi (leggero）
    2. Genera configurazioni dell'agente in batch (10-20 per batch)）
    3. Genera la configurazione della piattaforma
    """
    
    # Numero massimo di caratteri nel contesto
    MAX_CONTEXT_LENGTH = 50000
    # Il numero di agenti generati in ciascun batch
    AGENTS_PER_BATCH = 15
    
    # Lunghezza del troncamento del contesto per ogni passaggio (numero di caratteri）
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Configurazione dell'ora
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # configurazione dell'evento
    ENTITY_SUMMARY_LENGTH = 300          # Riepilogo dell'entità
    AGENT_SUMMARY_LENGTH = 300           # AgentRiepilogo delle entità in configurazione
    ENTITIES_PER_TYPE_DISPLAY = 20       # Visualizza la quantità di ciascun tipo di entità
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
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
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        nuts2_region: Optional[str] = None,
        calibration_profile: Optional[Dict[str, Any]] = None,
    ) -> SimulationParameters:
        """
        Generazione intelligente di configurazioni di simulazione complete (generazione passo-passo）
        
        Args:
            simulation_id: SimulazioneID
            project_id: ProgettoID
            graph_id: AtlanteID
            simulation_requirement: Descrizione dei requisiti di simulazione
            document_text: Contenuto del documento originale
            entities: Elenco di entità filtrato
            enable_twitter: Se abilitareTwitter
            enable_reddit: Se abilitareReddit
            progress_callback: Funzione di callback di avanzamento(current_step, total_steps, message)
            
        Returns:
            SimulationParameters: Parametri di simulazione completi
        """
        logger.info(f"Inizia a generare in modo intelligente configurazioni di simulazione: simulation_id={simulation_id}, Numero di entità={len(entities)}")
        
        # Calcolare il numero totale di passi
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # Configurazione temporale + configurazione eventi + N batch di Agenti + configurazione piattaforma
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. Costruisci informazioni contestuali di base
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities,
            nuts2_region=nuts2_region,
            calibration_profile=calibration_profile,
        )
        
        reasoning_parts = []
        
        # ========== passi1: Configurazione del tempo di creazione ==========
        report_progress(1, "Configurazione del tempo di creazione...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)

        if calibration_profile:
            self._apply_calibration_to_time_config(time_config, calibration_profile)
        reasoning_parts.append(f"Configurazione dell'ora: {time_config_result.get('reasoning', 'successo')}")
        
        # ========== passi2: Genera la configurazione dell'evento ==========
        report_progress(2, "Genera configurazioni di eventi e argomenti caldi...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"configurazione dell'evento: {event_config_result.get('reasoning', 'successo')}")
        
        # ========== passi3-N: Genera la configurazione dell'agente in batch ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]
            
            report_progress(
                3 + batch_idx,
                f"Genera la configurazione dell'agente ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )
            
            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement,
            )
            all_agent_configs.extend(batch_configs)

        if calibration_profile:
            self._apply_calibration_to_agent_configs(all_agent_configs, calibration_profile)
        
        reasoning_parts.append(f"AgentConfigurazione: Generato con successo {len(all_agent_configs)} un")
        
        # ========== Assegna un editore al post iniziale Agent ==========
        logger.info("Assegna l'editore appropriato al post iniziale Agent...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"Assegnazione iniziale dei posti: {assigned_count} i post sono stati assegnati agli editori")
        
        # ========== passo finale: Genera la configurazione della piattaforma ==========
        report_progress(total_steps, "Genera la configurazione della piattaforma...")
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # Costruisci i parametri finali
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            nuts2_region=nuts2_region,
            calibration_profile=calibration_profile,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(f"Generazione della configurazione della simulazione completata: {len(params.agent_configs)} Configurazione dell'agente")
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        nuts2_region: Optional[str] = None,
        calibration_profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Costruisci un contesto LLM, tronca alla lunghezza massima"""
        
        # Riepilogo dell'entità
        entity_summary = self._summarize_entities(entities)
        
        # Costruisci contesto
        context_parts = [
            f"## Requisiti di simulazione\n{simulation_requirement}",
            f"\n## Informazioni sull'entità ({len(entities)}un)\n{entity_summary}",
        ]

        if nuts2_region and calibration_profile:
            context_parts.append(
                f"\n## Calibrazione regionale\n{self._build_calibration_context_text(calibration_profile)}"
            )
        
        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # Lascia un margine di 500 caratteri
        
        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(Documento troncato)"
            context_parts.append(f"\n## Contenuto del documento originale\n{doc_text}")
        
        return "\n".join(context_parts)

    def _build_calibration_context_text(self, calibration_profile: Dict[str, Any]) -> str:
        layers = calibration_profile.get("layers", {})
        derived = calibration_profile.get("derived", {})
        economic = layers.get("economic", {}).get("indicators", {})
        cultural = layers.get("cultural", {}).get("hofstede_6d", {})
        demographic = layers.get("demographic", {}).get("indicators", {})
        social = layers.get("social", {}).get("indicators", {})

        return (
            f"Regione: {calibration_profile.get('name')} ({calibration_profile.get('nuts2_code')})\n"
            f"Zona: {calibration_profile.get('cultural_zone')}\n"
            f"Reddito mediano: €{economic.get('median_income_eur', 'n/d')} | Occupazione: {economic.get('employment_rate', 'n/d')}% | Disoccupazione: {demographic.get('unemployment_rate', 'n/d')}%\n"
            f"PDI: {cultural.get('PDI', 'n/d')} | IDV: {cultural.get('IDV', 'n/d')} | UAI: {cultural.get('UAI', 'n/d')}\n"
            f"Internet: {demographic.get('internet_users_pct', 'n/d')}% | Fiducia istituzionale: {social.get('institutional_trust', 'n/d')} | Soddisfazione: {social.get('life_satisfaction_mean', 'n/d')}\n"
            f"Indicazioni: attività ×{derived.get('activity_multiplier', 1.0)}, ritardo ×{derived.get('response_delay_multiplier', 1.0)}, influenza ×{derived.get('influence_multiplier', 1.0)}, stance {derived.get('stance', 'neutral')}"
        )

    def _apply_calibration_to_time_config(self, time_config: TimeSimulationConfig, calibration_profile: Dict[str, Any]):
        derived = calibration_profile.get("derived", {})
        multiplier = derived.get("activity_multiplier", 1.0)
        time_config.agents_per_hour_min = max(1, int(round(time_config.agents_per_hour_min * multiplier)))
        time_config.agents_per_hour_max = max(time_config.agents_per_hour_min, int(round(time_config.agents_per_hour_max * multiplier)))

    def _apply_calibration_to_agent_configs(self, agent_configs: List[AgentActivityConfig], calibration_profile: Dict[str, Any]):
        derived = calibration_profile.get("derived", {})
        activity_multiplier = derived.get("activity_multiplier", 1.0)
        response_multiplier = derived.get("response_delay_multiplier", 1.0)
        influence_multiplier = derived.get("influence_multiplier", 1.0)
        sentiment_bias = derived.get("sentiment_bias", 0.0)
        default_stance = derived.get("stance", "neutral")

        for config in agent_configs:
            config.activity_level = round(self._clamp(config.activity_level * activity_multiplier, 0.05, 1.0), 3)
            config.posts_per_hour = round(self._clamp(config.posts_per_hour * activity_multiplier, 0.05, 5.0), 3)
            config.comments_per_hour = round(self._clamp(config.comments_per_hour * activity_multiplier, 0.05, 8.0), 3)
            config.response_delay_min = max(1, int(round(config.response_delay_min * response_multiplier)))
            config.response_delay_max = max(config.response_delay_min, int(round(config.response_delay_max * response_multiplier)))
            config.influence_weight = round(self._clamp(config.influence_weight * influence_multiplier, 0.1, 5.0), 3)
            config.sentiment_bias = round(self._clamp(config.sentiment_bias + sentiment_bias, -1.0, 1.0), 3)
            if config.stance == "neutral":
                config.stance = default_stance

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Genera riepilogo dell'entità"""
        lines = []
        
        # Raggruppa per tipo
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)}un)")
            # Utilizza il numero di visualizzazione e la lunghezza del riepilogo configurati
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... Inoltre {len(type_entities) - display_count} un")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """Chiamata LLM con nuovo tentativo, inclusa la logica di riparazione JSON"""
        import re
        
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Abbassa la temperatura ogni volta che riprovi
                    # Non impostatomax_tokens，Lascia che LLM giochi liberamente
                )
                
                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason
                
                # Controlla se troncato
                if finish_reason == 'length':
                    logger.warning(f"LLML'output è troncato (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)
                
                # prova ad analizzareJSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSONAnalisi non riuscita (attempt {attempt+1}): {str(e)[:80]}")
                    
                    # provare a sistemareJSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(f"LLMchiamata fallita (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("LLMchiamata fallita")
    
    def _fix_truncated_json(self, content: str) -> str:
        """correggere troncatoJSON"""
        content = content.strip()
        
        # Contare le parentesi non chiuse
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Controlla se c'è una stringa non chiusa
        if content and content[-1] not in '",}]':
            content += '"'
        
        # closing bracket
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Prova a correggere la configurazioneJSON"""
        import re
        
        # Correggi i casi troncati
        content = self._fix_truncated_json(content)
        
        # Estrai la parte JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # Rimuovi i caratteri di nuova riga dalla stringa
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # Prova a rimuovere tutti i caratteri di controllo
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """Configurazione del tempo di creazione"""
        # Tronca la lunghezza utilizzando il contesto configurato
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
        
        # Calcolare il valore massimo consentito (80% del numero di agenti）
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""In base ai seguenti requisiti di simulazione, generare una configurazione di simulazione temporale。

{context_truncated}

## Compito
Genera la configurazione dell'oraJSON。

### Principi di base (solo come riferimento, devono essere adattati in modo flessibile in base agli eventi specifici e ai gruppi partecipanti):
- Il gruppo di utenti è cinese e deve rispettare le abitudini di lavoro e riposo dell'orario di Pechino
- Quasi nessuno è attivo dalle 0 alle 5 del mattino (coefficiente di attività0.05）
- Essere gradualmente attivi dalle 6 alle 8 (coefficiente di attività0.4）
- Moderatamente attivo durante l'orario di lavoro dalle 9 alle 18 (coefficiente di attività0.7）
- Il periodo di punta è compreso tra le 19 e le 22 di sera (coefficiente di attività1.5）
- 23L'attività diminuisce dopo aver fatto clic (coefficiente di attività0.5）
- Regola generale: scarsa attività al mattino presto、In aumento al mattino、Orario di lavoro moderato、picco serale
- **Importante**: i seguenti valori di esempio sono solo di riferimento, è necessario、Modificare il periodo di tempo specifico in base alle caratteristiche dei gruppi partecipanti
  - Ad esempio: il picco della popolazione studentesca potrebbe essere tra le 21 e le 23；Media attivi durante tutta la giornata；Le agenzie ufficiali sono aperte solo durante l'orario lavorativo
  - Ad esempio: gli argomenti caldi emergenti possono portare a discussioni a tarda notte，off_peak_hours Può essere accorciato opportunamente

### Restituisci il formato JSON (non è richiesto alcun ribasso)

Esempio：
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "Descrizione della configurazione dell'ora per questo evento"
}}

Descrizione del campo：
- total_simulation_hours (int): Durata totale della simulazione, 24-168 ore, emergenze brevi、Argomento di lunga durata
- minutes_per_round (int): Durata di ogni round, 30-120 minuti, consigliati 60 minuti
- agents_per_hour_min (int): Numero minimo di agenti attivati all'ora (intervallo di valori: 1-{max_agents_allowed}）
- agents_per_hour_max (int): Numero massimo di agenti attivati all'ora (intervallo di valori: 1-{max_agents_allowed}）
- peak_hours (intmatrice): Ore di punta, adattate in base ai gruppi di partecipanti all'evento
- off_peak_hours (intmatrice): Orari bassi, solitamente la sera tardi e la mattina presto
- morning_hours (intmatrice): Ore Mattutine
- work_hours (intmatrice): Ore Lavorative
- reasoning (string): Spiega brevemente perché è configurato in questo modo"""

        system_prompt = "Sei un esperto di simulazione dei social media. Restituisce il formato JSON puro, la configurazione dell'orario deve essere conforme alle abitudini di lavoro e di riposo dei cinesi。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Generazione LLM della configurazione dell'ora non riuscita: {e}, Utilizza la configurazione predefinita")
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """Ottieni la configurazione dell'orario predefinita (programmazione cinese）"""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # Ogni round dura 1 ora, accelerando il flusso del tempo
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "Utilizza la configurazione di pianificazione cinese predefinita (1 ora per round）"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Analizzare i risultati della configurazione dell'ora e verificareagents_per_hourIl valore non supera il numero totale di agenti"""
        # Ottieni il valore originale
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))
        
        # Verificare e correggere: assicurarsi che il numero totale di agenti non venga superato
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min ({agents_per_hour_min}) Supera il numero totale di agenti ({num_entities})，Corretto")
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max ({agents_per_hour_max}) Supera il numero totale di agenti ({num_entities})，Corretto")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        # garantire min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min >= max，è stato corretto a {agents_per_hour_min}")
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # L'impostazione predefinita è 1 ora per round
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # Quasi nessuno la mattina presto
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """Genera la configurazione dell'evento"""
        
        # Ottieni un elenco di tipi di entità disponibili come riferimento da LLM
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))
        
        # Elenca i nomi delle entità rappresentative per ciascun tipo
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # Tronca la lunghezza utilizzando il contesto configurato
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        
        prompt = f"""In base ai seguenti requisiti di simulazione, generare configurazioni di eventi.

Requisiti di simulazione: {simulation_requirement}

{context_truncated}

## Tipi di entità disponibili ed esempi
{type_info}

## Compito
Genera la configurazione dell'evento JSON:
- Estrai parole chiave di argomenti caldi
- Descrivere la direzione dello sviluppo dell'opinione pubblica
- Progettare il contenuto iniziale del post, **deve essere specificato per ogni post poster_type（Tipo di editore)**

**Importante**: poster_type deve essere dall'alto"Tipi di entità disponibili"Selezionare in modo che il post iniziale possa essere assegnato all'agente appropriato per la pubblicazione.
Ad esempio: le dichiarazioni ufficiali dovrebbero essere pubblicate dal tipo Ufficiale/Università, le notizie da MediaOutlet e le opinioni degli studenti da Studente.

Restituisce il formato JSON (non farlomarkdown）：
{{
    "hot_topics": ["parole chiave1", "parole chiave2", ...],
    "narrative_direction": "<Descrizione della direzione di sviluppo dell'opinione pubblica>",
    "initial_posts": [
        {{"content": "Pubblica contenuti", "poster_type": "Tipo di entità (deve essere selezionato tra i tipi disponibili）"}},
        ...
    ],
    "reasoning": "<Breve descrizione>"
}}"""

        system_prompt = "Sei un esperto nell'analisi dell'opinione pubblica. Restituisce il formato JSON puro. Nota poster_type Deve corrispondere esattamente ai tipi di entità disponibili。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Generazione LLM della configurazione eventi non riuscita: {e}, Utilizza la configurazione predefinita")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Utilizza la configurazione predefinita"
            }
    
    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Analizza i risultati della configurazione degli eventi"""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        Assegna l'agente editore appropriato al post iniziale
        
        Secondo ogni post poster_type Abbina il più adatto agent_id
        """
        if not event_config.initial_posts:
            return event_config
        
        # Crea un indice dell'agente per tipo di entità
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)
        
        # Tabella di mappatura dei tipi (gestisce i diversi formati che LLM può restituire）
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }
        
        # Registrare l'indice dell'agente utilizzato per ciascuna tipologia per evitare di riutilizzare lo stesso agent
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # Prova a trovare una corrispondenza agent
            matched_agent_id = None
            
            # 1. confronto diretto
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Utilizza la corrispondenza degli alias
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3. Se il problema persiste, utilizza l'impatto maggiore agent
            if matched_agent_id is None:
                logger.warning(f"tipo non trovato '{poster_type}' di agenti corrispondenti, utilizzando quello con l'influenza maggiore Agent")
                if agent_configs:
                    # Ordina per influenza e scegli quello con l'influenza più alta
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(f"Assegnazione iniziale dei posti: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
        
        event_config.initial_posts = updated_posts
        return event_config
    
    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Genera la configurazione dell'agente in batch"""
        
        # Crea informazioni sull'entità (utilizzando la lunghezza digest configurata）
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""Sulla base delle seguenti informazioni, genera una configurazione dell'attività sui social media per ciascuna entità.

Requisiti di simulazione: {simulation_requirement}

## Elenco entità
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## Compito
Genera la configurazione dell'attività per ciascuna entità, nota:
- **L'orario è conforme al programma dei cinesi**: quasi inattivo dalle 0 alle 5 del mattino, più attivo dalle 19 alle 22 della sera
- **Agenzia ufficiale** (Università/Agenzia governativa): scarsa attività(0.1-0.3)，orario di lavoro(9-17)attivo, lento a rispondere(60-240Minuti)，Alta influenza(2.5-3.0)
- **Media** (MediaOutlet): attivo(0.4-0.6)，Attività per tutta la giornata(8-23)，Risposta rapida(5-30Minuti)，Alta influenza(2.0-2.5)
- **Personale** (Studente/Persona/Alumni): Molto attivo(0.6-0.9)，Principali attività serali(18-23)，Risposta rapida(1-15Minuti)，bassa influenza(0.8-1.2)
- **Personaggio pubblico/Esperto**: Attivo(0.4-0.6)，Influenza da media ad alta(1.5-2.0)

Restituisce il formato JSON (non farlomarkdown）：
{{
    "agent_configs": [
        {{
            "agent_id": <Deve corrispondere all'input>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <Frequenza di pubblicazione>,
            "comments_per_hour": <Frequenza dei commenti>,
            "active_hours": [<Elenco delle ore attive, tenendo in considerazione il programma dei cinesi>],
            "response_delay_min": <Ritardo minimo di risposta in minuti>,
            "response_delay_max": <Ritardo massimo di risposta in minuti>,
            "sentiment_bias": <-1.0Arrivo1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <influenzare il peso>
        }},
        ...
    ]
}}"""

        system_prompt = "Sei un esperto nell'analisi del comportamento dei social media. Restituisci JSON puro, la configurazione deve essere conforme alle abitudini di lavoro e di riposo dei cinesi。"
        
        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"AgentLa configurazione della generazione LLM batch non è riuscita: {e}, Genera utilizzando le regole")
            llm_configs = {}
        
        # Costruisci l'oggetto AgentActivityConfig
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            
            # Se LLM non viene generato, utilizzare le regole per generare
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Genera una singola configurazione dell'Agente in base alle regole (lavoro cinese e riposo）"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        
        if entity_type in ["university", "governmentagency", "ngo"]:
            # Agenzia ufficiale: eventi sull'orario di lavoro, bassa frequenza, alto impatto
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # Media: eventi che durano tutto il giorno, frequenza media, impatto elevato
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Esperto/Professore: lavoro + attività serali, media frequenza
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Studenti: Principalmente la sera, alta frequenza
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # mattina + sera
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Alumni: Principalmente la sera
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Pausa pranzo + serata
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # Gente comune: picco serale
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # giorno + notte
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    

