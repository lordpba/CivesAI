"""
Servizio di generazione di ontologie
Interfaccia 1: analizza il contenuto del testo e genera definizioni di entità e tipi di relazione adatte alla simulazione sociale
"""

import json
import time
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# Parole di prompt del sistema generate dall'ontologia
ONTOLOGY_SYSTEM_PROMPT = """Sei un esperto di progettazione di ontologie di grafici della conoscenza professionale. Il tuo compito è analizzare il contenuto testuale fornito e i requisiti di simulazione e progettare tipi di entità e tipi di relazione adatti per la **Simulazione dell'opinione sui social media**.

**Importante: è necessario emettere dati validi in formato JSON, non emettere nient'altro.**

## Background della missione principale

Stiamo costruendo un **sistema di simulazione dell'opinione pubblica sui social media**. In questo sistema:
- Ogni entità ha voce sui social media, interazione, diffusione di informazioni "Account" o "Soggetto"
- Le entità si influenzano a vicenda、avanti、Commento、rispondere
- Dobbiamo simulare le reazioni di tutti i partiti e i percorsi di diffusione delle informazioni negli eventi dell'opinione pubblica

Pertanto, l'entità ** deve essere reale nella realtà、Soggetti che possono esprimersi e interagire sui social media**:

**può essere**:
- Soggetti specifici (personaggi pubblici、partiti、leader d'opinione、Esperti e studiosi、gente comune)
- Compagnia、Enterprise (incluso il suo account ufficiale)
- Struttura organizzativa (università、associazione、NGO、sindacati, ecc.)
- Dipartimenti governativi、agenzia di regolamentazione
- Organismi di informazione (giornali、Stazione televisiva、automediali、sito web)
- La stessa piattaforma di social media
- Rappresentanti di gruppi specifici (come le associazioni degli ex alumni, fanclub, gruppi di tutela dei diritti, ecc.)

**non può essere**:
- concetti astratti (es. "opinione pubblica", "emozioni", "Tendenza", "ZTL", "Tari" - questi sono concetti o argomenti, non entità che parlano)
- Tema/Argomento (es."Tasse Comunali", "Viabilità"）
- opinioni/atteggiamenti (es."Favorevole al Sindaco", "Contro la ZTL"）

## Formato di uscita

Si prega di produrre il formato JSON, inclusa la seguente struttura：

```json
{
    "entity_types": [
        {
            "name": "Nome del tipo di entità (inglese, PascalCase)",
            "description": "Breve descrizione (inglese, non più di 100 caratteri)",
            "attributes": [
                {
                    "name": "Nome dell'attributo (inglese, snake_case)",
                    "type": "text",
                    "description": "Descrizione della proprietà"
                }
            ],
            "examples": ["Entità di esempio1", "Entità di esempio2"]
        }
    ],
    "edge_types": [
        {
            "name": "Nome del tipo di relazione (inglese, SCREAMING_SNAKE_CASE)",
            "description": "Breve descrizione (inglese, non più di 100 caratteri)",
            "source_targets": [
                {"source": "Tipo di entità di origine (PascalCase)", "target": "tipo di entità di destinazione (PascalCase)"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Una breve analisi del contenuto del testo (italiano)"
}
```

## Linee guida per la progettazione (estremamente importanti!)

### 1. Progettazione del tipo di entità: deve essere rigorosamente rispettata

**Requisito quantitativo: devono esserci esattamente 10 tipi di entità**

**Requisiti di gerarchia (devono contenere sia tipi concreti che tipi astratti)**:

I tuoi 10 tipi di entità devono contenere i seguenti livelli:

A. **Tipo di categoria generale (deve essere inclusa, inserita negli ultimi 2 elementi dell'elenco)**:
   - `Person`: Il tipo di copertura di qualsiasi persona fisica. Una persona viene classificata in questa categoria quando non rientra in nessuno degli altri tipi di persone più specifici.
   - `Organization`: Il tipo di riferimento per qualsiasi organizzazione. Un'organizzazione viene classificata in questa categoria quando non appartiene ad un altro tipo di organizzazione più specifica.

B. **Tipi specifici (8, progettati in base al contenuto del testo)**:
   - Progetta tipologie più specifiche per i personaggi principali che appaiono nel testo
   - Ad esempio: se il testo si riferisce ad eventi accademici, potrebbe esserci `Student`, `Professor`, `University`
   - Ad esempio: se il testo si riferisce ad un evento aziendale, potrebbe esserci `Company`, `CEO`, `Employee`

**Perché hai bisogno di un tipo di categoria generale**:
- Vari personaggi appariranno nel testo, come ad esempio "Insegnanti della scuola primaria e secondaria", "Passante", "Un certo netizen"
- Se non esiste una corrispondenza di tipo specifico, devono essere classificati in `Person`
- Allo stesso modo, le piccole organizzazioni, i gruppi temporanei, ecc. dovrebbero essere classificati sotto `Organization`

**Principi di progettazione specifici del tipo**:
- Identificare i tipi di personaggi chiave o ricorrenti nel testo
- Ciascun tipo di entità specifica dovrebbe avere confini chiari per evitare sovrapposizioni
- La descrizione deve spiegare chiaramente la differenza tra questa tipologia e quella generale

### 2. Progettazione del tipo di relazione

- Quantità: 6-10 elementi
- Le relazioni dovrebbero riflettere connessioni reali nelle interazioni sui social media
- Garantire che la relazione source_targets copra i tipi di entità definiti

### 3. Progettazione degli attributi

- 1-3 attributi chiave per tipo di entità
- **Nota**: i nomi degli attributi non possono essere utilizzati `name`, `uuid`, `group_id`, `created_at`, `summary` (Queste sono parole riservate al sistema)
- Consigliato: `full_name`, `title`, `role`, `position`, `location`, `description` ecc.

## Riferimento al tipo di entità

**Categoria personale (specifica）**：
- StudenteFuoriSede: Studenti universitari fuori sede
- PensionatoINPS: Persona anziana in pensione
- PartitaIVA: Professionista, commerciante o lavoratore autonomo
- CittadinoResidente: Cittadino locale generico
- Sindaco: Il Sindaco o membro della Giunta
- GiornalistaLocale: Giornalista della cronaca locale
- DipendentePubblico: Lavoratore del Comune o statale

**Categoria personale (Generica)**:
- Person: Qualsiasi persona fisica (utilizzato quando non rientra nelle categorie specifiche di cui sopra)

**Tipo di organizzazione (specifico)**:
- Comune: Ente locale
- PoliziaLocale: Vigili urbani
- PartitoPolitico: Sezione locale di un partito
- MediaLocale: Testata giornalistica della città
- ASL: Azienda Sanitaria Locale
- ComitatoVerde: Associazione di cittadini o di quartiere
- AssociazioneCategoria: Es. Confcommercio, Confindustria

**Tipo di organizzazione (Generica)**:
- Organization: Qualsiasi organizzazione (utilizzata quando non è una delle tipologie specifiche elencate sopra)

## Riferimento al tipo di relazione

- WORKS_FOR: lavorando su
- STUDIES_AT: Ha studiato a
- AFFILIATED_WITH: Appartengono a
- REPRESENTS: rappresentare
- REGULATES: supervisione
- REPORTS_ON: rapporto
- COMMENTS_ON: Commento
- RESPONDS_TO: rispondere
- SUPPORTS: supporto
- OPPOSES: oggetto
- COLLABORATES_WITH: cooperazione
- COMPETES_WITH: concorrenza
"""


class OntologyGenerator:
    """
    generatore di ontologie
    Analizzare il contenuto del testo e generare definizioni di entità e tipi di relazione
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    MAX_LLM_ATTEMPTS = 3
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Genera una definizione di ontologia
        
        Args:
            document_texts: Elenco testi dei documenti
            simulation_requirement: Descrizione dei requisiti di simulazione
            additional_context: contesto aggiuntivo
            
        Returns:
            definizione di ontologia（entity_types, edge_typesAspetta）
        """
        # Crea messaggi per gli utenti
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # chiamareLLM con retry per errori transienti (risposta vuota/JSON non valido)
        last_error: Optional[Exception] = None
        result: Optional[Dict[str, Any]] = None
        for attempt in range(self.MAX_LLM_ATTEMPTS):
            temperature = max(0.1, 0.3 - (attempt * 0.1))
            try:
                result = self.llm_client.chat_json(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096
                )
                break
            except Exception as e:
                last_error = e
                if attempt < self.MAX_LLM_ATTEMPTS - 1:
                    from ..utils.logger import get_logger
                    logger = get_logger('mirofish.ontology')
                    logger.warning(
                        f"Generazione ontologia fallita (tentativo {attempt + 1}/{self.MAX_LLM_ATTEMPTS}): "
                        f"{str(e)[:120]}. Riprovo..."
                    )
                    time.sleep(2 * (attempt + 1))
                else:
                    raise

        if result is None:
            raise last_error or ValueError("Generazione ontologia fallita")
        
        # Validazione e post-elaborazione
        result = self._validate_and_process(result)
        
        return result
    
    # La lunghezza massima del testo trasmesso a LLM (50.000 parole）
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Crea messaggi per gli utenti"""
        
        # Unisci testo
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # Se il testo supera le 50.000 parole, verrà troncato (influisce solo sul contenuto passato a LLM, non sulla costruzione del grafico)）
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Testo originale totale{original_length}parole, prima dell'intercettazione{self.MAX_TEXT_LENGTH_FOR_LLM}Parole usate per l'analisi ontologica)..."
        
        message = f"""## Requisiti di simulazione

{simulation_requirement}

## Contenuto del documento

{combined_text}
"""
        
        if additional_context:
            message += f"""
## Ulteriori istruzioni

{additional_context}
"""
        
        message += """
Si prega di progettare tipi di entità e tipi di relazione adatti alla simulazione dell'opinione pubblica sociale in base al contenuto di cui sopra.

**Regole da rispettare**:
1. Devono essere restituiti esattamente 10 tipi di entità
2. Gli ultimi due devono essere tipi di categoria generale: Person (persona fisica generica) e Organization (organizzazione generica)
3. I primi 8 sono tipi specifici progettati in base al contenuto testuale
4. Tutti i tipi di entità devono essere soggetti che possano parlare nella realtà e non possano essere concetti astratti.
5. Impossibile utilizzare nomi di attributi riservati come name, uuid, group_id ecc. Usa full_name, org_name ecc. come sostituti.
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Risultati di validazione e post-elaborazione"""
        
        def to_pascal_case(s: str) -> str:
            """Converte una stringa in PascalCase"""
            return ''.join(word.capitalize() for word in s.replace('_', ' ').replace('-', ' ').split())
        
        def to_screaming_snake_case(s: str) -> str:
            """Converte una stringa in SCREAMING_SNAKE_CASE"""
            # Sostituisci gli spazi e i trattini con underscore, poi converti tutto a maiuscolo
            s = s.replace(' ', '_').replace('-', '_')
            # Rimuovi underscores multipli
            while '__' in s:
                s = s.replace('__', '_')
            return s.upper()
        
        # Assicurati che il risultato sia un dizionario
        if not isinstance(result, dict):
            from ..utils.logger import get_logger
            logger = get_logger('mirofish.ontology')
            logger.error(f"L'LLM ha restituito un formato non valido (previsto dizionario, ricevuto {type(result)}): {result}")
            raise ValueError(f"L'LLM ha restituito un formato non valido (ricevuto {type(result)})")

        # Assicurati che i campi obbligatori esistano
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # Convalida il tipo di entità
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Assicurati che la descrizione non superi i 100 caratteri
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
            # Converti il nome in PascalCase
            entity["name"] = to_pascal_case(entity["name"])
        
        # Verifica il tipo di relazione
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
            # Converti il nome in SCREAMING_SNAKE_CASE per le relazioni
            edge["name"] = to_screaming_snake_case(edge["name"])
            # Converti source e target in PascalCase
            for st in edge["source_targets"]:
                st["source"] = to_pascal_case(st["source"])
                st["target"] = to_pascal_case(st["target"])
        
        # Zep API Limitazioni: massimo 10 tipi di entità personalizzati, massimo 10 tipi di bordi personalizzati
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10
        
        # Definizione del tipo di zaino
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # Controlla se esiste già un tipo tascabile
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # Il tipo di copertura che deve essere aggiunta
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # Se dopo l'aggiunta ce ne saranno più di 10, alcuni tipi esistenti dovranno essere rimossi
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # Calcola quanti devono essere rimossi
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Rimosso dalla fine (mantenendo i tipi di cemento più importanti nella parte anteriore）
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # Aggiungi tipo di copertina
            result["entity_types"].extend(fallbacks_to_add)
        
        # In definitiva, garantire che i limiti non vengano superati (programmazione difensiva).）
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Converti le definizioni di ontologia in codice Python (qualcosa comeontology.py）
        
        Args:
            ontology: definizione di ontologia
            
        Returns:
            Pythonstringa di codice
        """
        code_lines = [
            '"""',
            'Definizione del tipo di entità personalizzata',
            "Generato automaticamente da MiroFish per la simulazione dell'opinione sociale",
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Definizione del tipo di entità ==============',
            '',
        ]
        
        # Genera tipo di entità
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== Definizione del tipo di relazione ==============')
        code_lines.append('')
        
        # Genera tipo di relazione
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Converti nel nome della classe PascalCase
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # Genera dizionario dei tipi
        code_lines.append('# ============== Digitare la configurazione ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # generare bordisource_targetsmappatura
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

