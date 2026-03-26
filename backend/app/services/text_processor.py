"""
servizio di elaborazione testi
"""

from typing import List, Optional
from ..utils.file_parser import FileParser, split_text_into_chunks


class TextProcessor:
    """elaboratore di testi"""
    
    @staticmethod
    def extract_from_files(file_paths: List[str]) -> str:
        """Estrai testo da più file"""
        return FileParser.extract_from_multiple(file_paths)
    
    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """
        dividere il testo
        
        Args:
            text: testo originale
            chunk_size: dimensione del blocco
            overlap: dimensione della sovrapposizione
            
        Returns:
            elenco dei blocchi di testo
        """
        return split_text_into_chunks(text, chunk_size, overlap)
    
    @staticmethod
    def preprocess_text(text: str) -> str:
        """
        Preelaborare il testo
        - Rimuovere lo spazio bianco extra
        - Interruzioni di riga standardizzate
        
        Args:
            text: testo originale
            
        Returns:
            testo elaborato
        """
        import re
        
        # Interruzioni di riga standardizzate
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Rimuovi le righe vuote consecutive (mantieni fino a due ritorni a capo）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Rimuovi gli spazi bianchi iniziali e finali
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    @staticmethod
    def get_text_stats(text: str) -> dict:
        """Ottieni statistiche sul testo"""
        return {
            "total_chars": len(text),
            "total_lines": text.count('\n') + 1,
            "total_words": len(text.split()),
        }

