"""
ZepServizio di aggiornamento della memoria della mappa
Aggiorna dinamicamente le attività dell'Agente nella simulazione sulla mappa Zep
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Agentregistro delle attività"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Converti le attività in descrizioni testuali che possono essere inviate a Zep
        
        Adotta un formato di descrizione in linguaggio naturale da cui Zep può estrarre entità e relazioni
        Non aggiungere prefissi relativi alla simulazione per evitare aggiornamenti delle mappe fuorvianti
        """
        # Genera descrizioni diverse in base ai diversi tipi di azione
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # Ritorna direttamente "agentNome: Descrizione dell'attività" formato, senza aggiungere il prefisso di simulazione
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"ha pubblicato un post：「{content}」"
        return "ha pubblicato un post"
    
    def _describe_like_post(self) -> str:
        """Metti "Mi piace" al post, incluso il testo originale e le informazioni sull'autore del post"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"Mi è piaciuto{post_author}i post：「{post_content}」"
        elif post_content:
            return f"Mi è piaciuto un post：「{post_content}」"
        elif post_author:
            return f"Mi è piaciuto{post_author}un post di"
        return "Mi è piaciuto un post"
    
    def _describe_dislike_post(self) -> str:
        """Non mi piace il post: include il testo originale e le informazioni sull'autore del post"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"calpestato{post_author}i post：「{post_content}」"
        elif post_content:
            return f"Non mi è piaciuto un post：「{post_content}」"
        elif post_author:
            return f"calpestato{post_author}un post di"
        return "Non mi è piaciuto un post"
    
    def _describe_repost(self) -> str:
        """Ripubblica un post: includi il contenuto del post originale e le informazioni sull'autore"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"Inoltrato{original_author}i post：「{original_content}」"
        elif original_content:
            return f"ha ritwittato un post：「{original_content}」"
        elif original_author:
            return f"Inoltrato{original_author}un post di"
        return "ha ritwittato un post"
    
    def _describe_quote_post(self) -> str:
        """Post con citazione: contiene il contenuto del post originale、Informazioni sull'autore e commenti sulle citazioni"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"citato{original_author}i post「{original_content}」"
        elif original_content:
            base = f"citato un post「{original_content}」"
        elif original_author:
            base = f"citato{original_author}un post di"
        else:
            base = "citato un post"
        
        if quote_content:
            base += f"，e commentato：「{quote_content}」"
        return base
    
    def _describe_follow(self) -> str:
        """Utenti seguiti: contiene i nomi degli utenti seguiti"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"Utenti seguiti「{target_user_name}」"
        return "Ho seguito un utente"
    
    def _describe_create_comment(self) -> str:
        """Pubblica un commento: include il contenuto del commento e le informazioni sul post commentato"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"dentro{post_author}i post「{post_content}」Commentato sotto：「{content}」"
            elif post_content:
                return f"in posta「{post_content}」Commentato sotto：「{content}」"
            elif post_author:
                return f"dentro{post_author}ha commentato il post：「{content}」"
            return f"commentato：「{content}」"
        return "Ha pubblicato un commento"
    
    def _describe_like_comment(self) -> str:
        """Mi piace ai commenti: inclusi il contenuto dei commenti e le informazioni sull'autore"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"Mi è piaciuto{comment_author}commenti：「{comment_content}」"
        elif comment_content:
            return f"Mi è piaciuto un commento：「{comment_content}」"
        elif comment_author:
            return f"Mi è piaciuto{comment_author}un commento di"
        return "Mi è piaciuto un commento"
    
    def _describe_dislike_comment(self) -> str:
        """Commenti non mi piace: include il contenuto del commento e le informazioni sull'autore"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"calpestato{comment_author}commenti：「{comment_content}」"
        elif comment_content:
            return f"Non mi è piaciuto un commento：「{comment_content}」"
        elif comment_author:
            return f"calpestato{comment_author}un commento di"
        return "Non mi è piaciuto un commento"
    
    def _describe_search(self) -> str:
        """Post di ricerca: contengono parole chiave di ricerca"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"Cercato「{query}」" if query else "Cercato"
    
    def _describe_search_user(self) -> str:
        """Cerca utente: contiene le parole chiave di ricerca"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"Ricerca utenti「{query}」" if query else "Ricerca utenti"
    
    def _describe_mute(self) -> str:
        """Utente bloccato: contiene il nome dell'utente bloccato"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"Utente bloccato「{target_user_name}」"
        return "Bloccato un utente"
    
    def _describe_generic(self) -> str:
        # Per i tipi di azione sconosciuti, generare una descrizione generica
        return f"Eseguito{self.action_type}Operazione"


class ZepGraphMemoryUpdater:
    """
    ZepAggiornamento della memoria della mappa
    
    Monitora i file di registro delle azioni simulate e aggiorna le nuove attività degli agenti sul grafico Zep in tempo reale.
    Raggruppati per piattaforma, ciascuno accumulatoBATCH_SIZEInviato a Zep in batch dopo l'attività.
    
    Tutte le azioni significative verranno aggiornate aZep，action_argsconterrà informazioni contestuali complete:
    - Il testo originale del post a cui è piaciuto/non piaciuto
    - Il testo originale del post inoltrato/citato
    - Nomi utente da seguire/bloccare
    - Il testo originale del commento che ha apprezzato/non apprezzato
    """
    
    # Dimensioni di invio batch (quanti articoli accumula ciascuna piattaforma prima dell'invio)）
    BATCH_SIZE = 5
    
    # Mappatura del nome della piattaforma (per la visualizzazione della console）
    PLATFORM_DISPLAY_NAMES = {
        'twitter': 'mondo1',
        'reddit': 'mondo2',
    }
    
    # Intervallo di invio (secondi) per evitare richieste troppo rapide
    SEND_INTERVAL = 0.5
    
    # Riprovare la configurazione
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # secondi
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        Inizializza l'aggiornamento
        
        Args:
            graph_id: ZepAtlanteID
            api_key: Zep API Key（Facoltativo, per impostazione predefinita viene letto dalla configurazione）
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY
        
        if not self.api_key:
            raise ValueError("ZEP_API_KEYNon configurato")
        
        self.client = Zep(api_key=self.api_key)
        
        # coda di attività
        self._activity_queue: Queue = Queue()
        
        # Buffer di attività raggruppato per piattaforma (ogni piattaforma si accumula inBATCH_SIZEInvia in lotti）
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # bandiera di controllo
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistiche
        self._total_activities = 0  # Numero di attività effettivamente aggiunte alla coda
        self._total_sent = 0        # Numero di batch inviati con successo a Zep
        self._total_items_sent = 0  # Numero di eventi inviati con successo a Zep
        self._failed_count = 0      # Numero di batch che non sono stati inviati
        self._skipped_count = 0     # Numero di attività saltate per filtro（DO_NOTHING）
        
        logger.info(f"ZepGraphMemoryUpdater Inizializzazione completata: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """Ottieni il nome visualizzato della piattaforma"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """Avvia il thread di lavoro in background"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater Iniziato: graph_id={self.graph_id}")
    
    def stop(self):
        """Arresta il thread di lavoro in background"""
        self._running = False
        
        # Invia le attività rimanenti
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"ZepGraphMemoryUpdater Fermato: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        Aggiungi un'attività dell'agente alla coda
        
        Tutte le azioni significative vengono aggiunte alla coda, incluso：
        - CREATE_POST（posta）
        - CREATE_COMMENT（Commento）
        - QUOTE_POST（messaggio di citazione）
        - SEARCH_POSTS（Cerca post）
        - SEARCH_USER（Cerca utenti）
        - LIKE_POST/DISLIKE_POST（Mi piace/non mi piace il post)
        - REPOST (avanti)
        - SEGUI
        - MUTO (muto）
        - LIKE_COMMENT/DISLIKE_COMMENT（Commenti Mi piace/Non mi piace）
        
        action_argsconterrà informazioni contestuali complete (come il testo originale del post、Nome utente ecc.）。
        
        Args:
            activity: Agentregistro delle attività
        """
        # saltaDO_NOTHINGtipo di attività
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Aggiungi attività alla coda Zep: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        Aggiungi attività dai dati del dizionario
        
        Args:
            data: daactions.jsonldati del dizionario analizzati
            platform: Nome della piattaforma (twitter/reddit)
        """
        # Salta le voci per il tipo di evento
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self):
        """Ciclo di lavoro in background: invia attività in batch in base alla piattaformaZep"""
        while self._running or not self._activity_queue.empty():
            try:
                # Prova a ottenere l'attività dalla coda (timeout 1 secondo）
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # Aggiungi l'attività al buffer per la piattaforma corrispondente
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # Controlla se la piattaforma ha raggiunto la dimensione del batch
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Rilasciare il blocco prima dell'invio
                            self._send_batch_activities(batch, platform)
                            # Invia intervallo per evitare richieste troppo rapide
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"Ciclo di lavoro anomalo: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Invia attività al grafico Zep in batch (consolidate in un unico testo)）
        
        Args:
            activities: AgentElenco attività
            platform: Nome della piattaforma
        """
        if not activities:
            return
        
        # Combina più attività in un unico testo, separate da ritorni a capo
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # Invia con riprova
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"Inviati in batch con successo {len(activities)} Articolo{display_name}Attività da mappare {self.graph_id}")
                logger.debug(f"Anteprima del contenuto batch: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Batch sending to Zep failed (provare {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Invio batch a Zep non riuscito, riprovato{self.MAX_RETRIES}volte: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """Invia l'attività rimanente in coda e nel buffer"""
        # Per prima cosa elabora le attività rimanenti nella coda e aggiungile al buffer
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # Quindi invia l'attività rimanente nel buffer di ciascuna piattaforma (anche se non ce n'è abbastanzaBATCH_SIZEArticolo）
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"inviare{display_name}Il resto della piattaforma {len(buffer)} Attività")
                    self._send_batch_activities(buffer, platform)
            # Cancella tutti i buffer
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Ottieni statistiche"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # Il numero totale di attività aggiunte alla coda
            "batches_sent": self._total_sent,            # Numero di batch inviati correttamente
            "items_sent": self._total_items_sent,        # Numero di eventi inviati con successo
            "failed_count": self._failed_count,          # Numero di batch che non sono stati inviati
            "skipped_count": self._skipped_count,        # Numero di attività saltate per filtro（DO_NOTHING）
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # Dimensioni del buffer per ciascuna piattaforma
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    Aggiornamento della memoria della mappa Zep per la gestione di più simulazioni
    
    Ogni simulazione può avere la propria istanza di aggiornamento
    """
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        Creare un programma di aggiornamento della memoria della mappa per la simulazione
        
        Args:
            simulation_id: SimulazioneID
            graph_id: ZepAtlanteID
            
        Returns:
            ZepGraphMemoryUpdaterEsempio
        """
        with cls._lock:
            # Se esiste già, arresta prima quello vecchio
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"Crea un aggiornamento della memoria della mappa: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Ottieni l'aggiornamento simulato"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Arresta e rimuovi l'aggiornamento simulato"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Aggiornamento della memoria della mappa interrotto: simulation_id={simulation_id}")
    
    # prevenire stop_all Contrassegno per chiamate ripetute
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """Arresta tutti gli aggiornamenti"""
        # Evita chiamate ripetute
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"Impossibile interrompere l'aggiornamento: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("Tutti gli aggiornamenti della memoria della mappa sono stati interrotti")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Ottieni statistiche per tutti gli aggiornamenti"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
