"""
LLMincapsulamento del client
Uso unificato delle chiamate in formato OpenAI
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


from ..utils.logger import get_logger

logger = get_logger('mirofish.llm')

class LLMClient:
    """LLMcliente"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY Non configurato")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Invia richiesta di chat
        
        Args:
            messages: Elenco dei messaggi
            temperature: Parametri di temperatura
            max_tokens: Numero massimo di token
            response_format: Formato di risposta (come lo schema JSON）
            
        Returns:
            Testo della risposta del modello
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        if not response.choices:
            logger.error(f"LLM Response choices empty: {response}")
            return ""
        
        content = response.choices[0].message.content or ""
        # Alcuni modelli (esMiniMax M2.5）saranno inclusi nei contenuti<think>Il contenuto pensante deve essere rimosso
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        logger.info(f"Modello {self.model} Risposta: {content[:200]}..." if len(content) > 200 else content)
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Invia richiesta di chat e ritornaJSON
        
        Args:
            messages: Elenco dei messaggi
            temperature: Parametri di temperatura
            max_tokens: Numero massimo di token
            
        Returns:
            Oggetto JSON analizzato
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # Prova a estrarre il blocco JSON principale (cerca dalla prima parentesi graffa all'ultima)
        json_match = re.search(r'(\{[\s\S]*\})', response, re.DOTALL)
        if json_match:
            cleaned_response = json_match.group(1).strip()
        else:
            # Fallback alla rimozione dei tag markdown se non troviamo graffe
            cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', response.strip(), flags=re.IGNORECASE)
            cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
            cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            logger.error(f"JSON non valido restituito da LLM: {cleaned_response}")
            raise ValueError(f"LLM Il formato JSON restituito non è valido: {cleaned_response[:100]}...")

