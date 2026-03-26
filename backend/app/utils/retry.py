"""
APIMeccanismo di ripetizione della chiamata
Riprovare la logica per la gestione delle chiamate API esterne come LLM
"""

import time
import random
import functools
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger

logger = get_logger('mirofish.retry')


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Riprova il decoratore con backoff esponenziale
    
    Args:
        max_retries: Numero massimo di tentativi
        initial_delay: Ritardo iniziale (secondi）
        max_delay: Ritardo massimo (secondi）
        backoff_factor: fattore di backoff
        jitter: Se aggiungere jitter casuale
        exceptions: Tipo di eccezione che deve essere riprovato
        on_retry: funzione di richiamata quando si riprova (exception, retry_count)
    
    Usage:
        @retry_with_backoff(max_retries=3)
        def call_llm_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"funzione {func.__name__} dentro {max_retries} Ancora fallito dopo i tentativi: {str(e)}")
                        raise
                    
                    # Ritardo nel calcolo
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"funzione {func.__name__} No. {attempt + 1} tentativi falliti: {str(e)}, "
                        f"{current_delay:.1f}Riprova tra qualche secondo..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    time.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Versione asincrona del decoratore dei tentativi
    """
    import asyncio
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"funzione asincrona {func.__name__} dentro {max_retries} Ancora fallito dopo i tentativi: {str(e)}")
                        raise
                    
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"funzione asincrona {func.__name__} No. {attempt + 1} tentativi falliti: {str(e)}, "
                        f"{current_delay:.1f}Riprova tra qualche secondo..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


class RetryableAPIClient:
    """
    Wrapper client API riproducibile
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """
        Eseguire chiamate di funzione e riprovare in caso di errore
        
        Args:
            func: funzione da chiamare
            *args: Parametri di funzione
            exceptions: Tipo di eccezione che deve essere riprovato
            **kwargs: argomenti delle parole chiave della funzione
            
        Returns:
            valore restituito dalla funzione
        """
        last_exception = None
        delay = self.initial_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
                
            except exceptions as e:
                last_exception = e
                
                if attempt == self.max_retries:
                    logger.error(f"APIChiamato a {self.max_retries} Ancora fallito dopo i tentativi: {str(e)}")
                    raise
                
                current_delay = min(delay, self.max_delay)
                current_delay = current_delay * (0.5 + random.random())
                
                logger.warning(
                    f"APIChiama il n. {attempt + 1} tentativi falliti: {str(e)}, "
                    f"{current_delay:.1f}Riprova tra qualche secondo..."
                )
                
                time.sleep(current_delay)
                delay *= self.backoff_factor
        
        raise last_exception
    
    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """
        Chiama in batch e riprova individualmente ogni elemento fallito
        
        Args:
            items: Elenco degli elementi su cui lavorare
            process_func: Funzione di elaborazione, ricevendo un singolo articolo come parametro
            exceptions: Tipo di eccezione che deve essere riprovato
            continue_on_failure: Se continuare l'elaborazione di altri elementi dopo che un singolo elemento ha avuto esito negativo
            
        Returns:
            (Elenco dei risultati positivi, Elenco degli elementi non riusciti)
        """
        results = []
        failures = []
        
        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions
                )
                results.append(result)
                
            except Exception as e:
                logger.error(f"sezione di elaborazione {idx + 1} Articolo non riuscito: {str(e)}")
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })
                
                if not continue_on_failure:
                    raise
        
        return results, failures

