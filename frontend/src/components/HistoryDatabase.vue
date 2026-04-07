<template>
  <div 
    class="history-database"
    :class="{ 'no-projects': projects.length === 0 && !loading }"
    ref="historyContainer"
  >
    <!-- Decorazione dello sfondo: Linee della griglia tecnica (mostrate solo quando sono presenti progetti） -->
    <div v-if="projects.length > 0 || loading" class="tech-grid-bg">
      <div class="grid-pattern"></div>
      <div class="gradient-overlay"></div>
    </div>

    <!-- area del titolo -->
    <div class="section-header">
      <div class="section-line"></div>
      <span class="section-title">Registro delle detrazioni</span>
      <div class="section-line"></div>
    </div>

    <!-- Contenitore della carta (visualizzato solo se sono presenti articoli） -->
    <div v-if="projects.length > 0" class="cards-container" :class="{ expanded: isExpanded }" :style="containerStyle">
      <div 
        v-for="(project, index) in projects" 
        :key="project.simulation_id"
        class="project-card"
        :class="{ expanded: isExpanded, hovering: hoveringCard === index }"
        :style="getCardStyle(index)"
        @mouseenter="hoveringCard = index"
        @mouseleave="hoveringCard = null"
        @click="navigateToProject(project)"
      >
        <button
          class="delete-card-btn"
          type="button"
          title="Elimina simulazione"
          :disabled="loadingDeleteId === project.simulation_id"
          @click.stop="confirmDeleteProject(project)"
        >
          <span v-if="loadingDeleteId === project.simulation_id">...</span>
          <span v-else>✕</span>
        </button>

        <!-- intestazione della carta：simulation_id e lo stato di disponibilità delle funzioni -->
        <div class="card-header">
          <span class="card-id">{{ formatSimulationId(project.simulation_id) }}</span>
          <div class="card-status-icons">
            <span 
              class="status-icon" 
              :class="{ available: project.project_id, unavailable: !project.project_id }"
              title="Costruzione della mappa"
            >◇</span>
            <span 
              class="status-icon available" 
              title="Configurazione dell'ambiente"
            >◈</span>
            <span 
              class="status-icon" 
              :class="{ available: project.report_id, unavailable: !project.report_id }"
              title="rapporto di analisi"
            >◆</span>
          </div>
        </div>

        <!-- area elenco file -->
        <div class="card-files-wrapper">
          <!-- Decorazione d'angolo - Stile di inquadratura -->
          <div class="corner-mark top-left-only"></div>
          
          <!-- elenco dei file -->
          <div class="files-list" v-if="project.files && project.files.length > 0">
            <div 
              v-for="(file, fileIndex) in project.files.slice(0, 3)" 
              :key="fileIndex"
              class="file-item"
            >
              <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
              <span class="file-name">{{ truncateFilename(file.filename, 20) }}</span>
            </div>
            <!-- Se sono presenti più file, mostra un messaggio -->
            <div v-if="project.files.length > 3" class="files-more">
              +{{ project.files.length - 3 }} file
            </div>
          </div>
          <!-- Segnaposto quando non è presente alcun file -->
          <div class="files-empty" v-else>
            <span class="empty-file-icon">◇</span>
            <span class="empty-file-text">Nessun file ancora</span>
          </div>
        </div>

        <!-- Titolo della carta (utilizzare le prime 20 parole dei requisiti di simulazione come titolo） -->
        <h3 class="card-title">{{ getSimulationTitle(project.simulation_requirement) }}</h3>

        <!-- Descrizione della scheda (visualizzazione completa dei requisiti della simulazione） -->
        <p class="card-desc">{{ truncateText(project.simulation_requirement, 55) }}</p>

        <!-- fondo della carta -->
        <div class="card-footer">
          <div class="card-datetime">
            <span class="card-date">{{ formatDate(project.created_at) }}</span>
            <span class="card-time">{{ formatTime(project.created_at) }}</span>
          </div>
          <span class="card-progress" :class="getProgressClass(project)">
            <span class="status-dot">●</span> {{ formatRounds(project) }}
          </span>
        </div>
        
        <!-- Linea decorativa inferiore (hovertempo per espandersi) -->
        <div class="card-bottom-line"></div>
      </div>
    </div>

    <!-- Stato di caricamento -->
    <div v-if="loading" class="loading-state">
      <span class="loading-spinner"></span>
      <span class="loading-text">Caricamento in corso...</span>
    </div>

    <!-- Finestra pop-up con i dettagli del replay storico -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="selectedProject" class="modal-overlay" @click.self="closeModal">
          <div class="modal-content">
            <!-- Intestazione popup -->
            <div class="modal-header">
              <div class="modal-title-section">
                <span class="modal-id">{{ formatSimulationId(selectedProject.simulation_id) }}</span>
                <span class="modal-progress" :class="getProgressClass(selectedProject)">
                  <span class="status-dot">●</span> {{ formatRounds(selectedProject) }}
                </span>
                <span class="modal-create-time">{{ formatDate(selectedProject.created_at) }} {{ formatTime(selectedProject.created_at) }}</span>
              </div>
              <button class="modal-close" @click="closeModal">×</button>
            </div>

            <!-- Contenuti pop-up -->
            <div class="modal-body">
              <!-- Requisiti di simulazione -->
              <div class="modal-section">
                <div class="modal-label">Requisiti di simulazione</div>
                <div class="modal-requirement">{{ selectedProject.simulation_requirement || 'Nessuno' }}</div>
              </div>

              <!-- elenco dei file -->
              <div class="modal-section">
                <div class="modal-label">file associati</div>
                <div class="modal-files" v-if="selectedProject.files && selectedProject.files.length > 0">
                  <div v-for="(file, index) in selectedProject.files" :key="index" class="modal-file-item">
                    <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                    <span class="modal-file-name">{{ file.filename }}</span>
                  </div>
                </div>
                <div class="modal-empty" v-else>Nessun file associato ancora</div>
              </div>
            </div>

            <!-- Linea di divisione della riproduzione della deduzione -->
            <div class="modal-divider">
              <span class="divider-line"></span>
              <span class="divider-text">Riproduzione di detrazione</span>
              <span class="divider-line"></span>
            </div>

            <!-- Pulsanti di navigazione -->
            <div class="modal-actions">
              <button 
                class="modal-btn btn-project" 
                @click="goToProject"
                :disabled="!selectedProject.project_id"
              >
                <span class="btn-step">Step1</span>
                <span class="btn-icon">◇</span>
                <span class="btn-text">Costruzione della mappa</span>
              </button>
              <button 
                class="modal-btn btn-simulation" 
                @click="goToSimulation"
              >
                <span class="btn-step">Step2</span>
                <span class="btn-icon">◈</span>
                <span class="btn-text">Configurazione dell'ambiente</span>
              </button>
              <button 
                class="modal-btn btn-report" 
                @click="goToReport"
                :disabled="!selectedProject.report_id"
              >
                <span class="btn-step">Step4</span>
                <span class="btn-icon">◆</span>
                <span class="btn-text">rapporto di analisi</span>
              </button>
            </div>
            <div class="modal-danger-zone">
              <button
                class="modal-delete-btn"
                type="button"
                :disabled="loadingDeleteId === selectedProject.simulation_id"
                @click="confirmDeleteProject(selectedProject)"
              >
                <span v-if="loadingDeleteId === selectedProject.simulation_id">Eliminazione...</span>
                <span v-else>Elimina simulazione</span>
              </button>
            </div>
            <!-- Prompt non riproducibile -->
            <div class="modal-playback-hint">
              <span class="hint-text">Step3「Avvia la simulazione」con Step5「Interazione profonda」È necessario avviarlo durante il funzionamento e la riproduzione della cronologia non è supportata.</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getSimulationHistory, deleteSimulation } from '../api/simulation'

const router = useRouter()
const route = useRoute()

// Stato
const projects = ref([])
const loading = ref(true)
const isExpanded = ref(false)
const hoveringCard = ref(null)
const historyContainer = ref(null)
const selectedProject = ref(null)  // L'elemento attualmente selezionato (per le finestre pop-up）
const loadingDeleteId = ref(null)
let observer = null
let isAnimating = false  // Blocco dell'animazione per evitare sfarfallio
let expandDebounceTimer = null  // Temporizzatore anti-vibrazione
let pendingState = null  // Registrare lo stato del target da eseguire

// Configurazione del layout della scheda: adatta a un rapporto più ampio
const CARDS_PER_ROW = 4
const CARD_WIDTH = 280  
const CARD_HEIGHT = 280 
const CARD_GAP = 24

// Calcola dinamicamente lo stile dell'altezza del contenitore
const containerStyle = computed(() => {
  if (!isExpanded.value) {
    // Stato piegato: altezza fissa
    return { minHeight: '420px' }
  }
  
  // Stato espanso: calcola dinamicamente l'altezza in base al numero di carte
  const total = projects.value.length
  if (total === 0) {
    return { minHeight: '280px' }
  }
  
  const rows = Math.ceil(total / CARDS_PER_ROW)
  // Calcola l'altezza effettiva richiesta: numero di righe * altezza della carta + (Numero di righe-1) * spaziatura + una piccola quantità di spaziatura inferiore
  const expandedHeight = rows * CARD_HEIGHT + (rows - 1) * CARD_GAP + 10
  
  return { minHeight: `${expandedHeight}px` }
})

// Ottieni lo stile della carta
const getCardStyle = (index) => {
  const total = projects.value.length
  
  if (isExpanded.value) {
    // Stato espanso: layout a griglia
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'

    const col = index % CARDS_PER_ROW
    const row = Math.floor(index / CARDS_PER_ROW)
    
    // Conta il numero di carte nella riga corrente, assicurandoti che ogni riga sia centrata
    const currentRowStart = row * CARDS_PER_ROW
    const currentRowCards = Math.min(CARDS_PER_ROW, total - currentRowStart)
    
    const rowWidth = currentRowCards * CARD_WIDTH + (currentRowCards - 1) * CARD_GAP
    
    const startX = -(rowWidth / 2) + (CARD_WIDTH / 2)
    const colInRow = index % CARDS_PER_ROW
    const x = startX + colInRow * (CARD_WIDTH + CARD_GAP)
    
    // Espandi verso il basso per aumentare lo spazio tra il titolo e il titolo
    const y = 20 + row * (CARD_HEIGHT + CARD_GAP)

    return {
      transform: `translate(${x}px, ${y}px) rotate(0deg) scale(1)`,
      zIndex: 100 + index,
      opacity: 1,
      transition: transition
    }
  } else {
    // Stato piegato: impilamento a forma di ventaglio
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'

    const centerIndex = (total - 1) / 2
    const offset = index - centerIndex
    
    const x = offset * 35
    // Regola la posizione iniziale in modo che sia vicina al titolo ma mantieni una spaziatura adeguata
    const y = 25 + Math.abs(offset) * 8
    const r = offset * 3
    const s = 0.95 - Math.abs(offset) * 0.05
    
    return {
      transform: `translate(${x}px, ${y}px) rotate(${r}deg) scale(${s})`,
      zIndex: 10 + index,
      opacity: 1,
      transition: transition
    }
  }
}

// Ottieni lezioni di stile in base ai progressi del round
const getProgressClass = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  
  if (total === 0 || current === 0) {
    // Non iniziato
    return 'not-started'
  } else if (current >= total) {
    // Completato
    return 'completed'
  } else {
    // In corso
    return 'in-progress'
  }
}

// FormatoData (viene visualizzata solo la parte della datapunti）
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toISOString().slice(0, 10)
  } catch {
    return dateStr?.slice(0, 10) || ''
  }
}

// Formato ora (quando visualizzato:punti）
const formatTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    const hours = date.getHours().toString().padStart(2, '0')
    const minutes = date.getMinutes().toString().padStart(2, '0')
    return `${hours}:${minutes}`
  } catch {
    return ''
  }
}

// Troncare il testo
const truncateText = (text, maxLength) => {
  if (!text) return ''
  return text.length > maxLength ? text.slice(0, maxLength) + '...' : text
}

// Genera titolo da requisiti simulati (prendi le prime 20 parole）
const getSimulationTitle = (requirement) => {
  if (!requirement) return 'Simulazione senza nome'
  const title = requirement.slice(0, 20)
  return requirement.length > 20 ? title + '...' : title
}

// Formato simulation_id Display (troncare le prime 6 cifre）
const formatSimulationId = (simulationId) => {
  if (!simulationId) return 'SIM_UNKNOWN'
  const prefix = simulationId.replace('sim_', '').slice(0, 6)
  return `SIM_${prefix.toUpperCase()}`
}

// Visualizzazione del numero del round formattato (round corrente/numero totale di round）
const formatRounds = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  if (total === 0) return 'Non iniziato'
  return `${current}/${total} ruota`
}

// Get the file type (used in styles）
const getFileType = (filename) => {
  if (!filename) return 'other'
  const ext = filename.split('.').pop()?.toLowerCase()
  const typeMap = {
    'pdf': 'pdf',
    'doc': 'doc', 'docx': 'doc',
    'xls': 'xls', 'xlsx': 'xls', 'csv': 'xls',
    'ppt': 'ppt', 'pptx': 'ppt',
    'txt': 'txt', 'md': 'txt', 'json': 'code',
    'jpg': 'img', 'jpeg': 'img', 'png': 'img', 'gif': 'img',
    'zip': 'zip', 'rar': 'zip', '7z': 'zip'
  }
  return typeMap[ext] || 'other'
}

// Ottieni il testo dell'etichetta del tipo di file
const getFileTypeLabel = (filename) => {
  if (!filename) return 'FILE'
  const ext = filename.split('.').pop()?.toUpperCase()
  return ext || 'FILE'
}

// Tronca il nome del file (mantieni l'estensione）
const truncateFilename = (filename, maxLength) => {
  if (!filename) return 'file sconosciuto'
  if (filename.length <= maxLength) return filename
  
  const ext = filename.includes('.') ? '.' + filename.split('.').pop() : ''
  const nameWithoutExt = filename.slice(0, filename.length - ext.length)
  const truncatedName = nameWithoutExt.slice(0, maxLength - ext.length - 3) + '...'
  return truncatedName + ext
}

// Apri la finestra pop-up dei dettagli del progetto
const navigateToProject = (simulation) => {
  selectedProject.value = simulation
}

// Chiudi la finestra pop-up
const closeModal = () => {
  selectedProject.value = null
}

// Passare alla pagina di costruzione del grafico（Project）
const goToProject = () => {
  if (selectedProject.value?.project_id) {
    router.push({
      name: 'Process',
      params: { projectId: selectedProject.value.project_id }
    })
    closeModal()
  }
}

// Passare alla pagina di configurazione dell'ambiente（Simulation）
const goToSimulation = () => {
  if (selectedProject.value?.simulation_id) {
    router.push({
      name: 'Simulation',
      params: { simulationId: selectedProject.value.simulation_id }
    })
    closeModal()
  }
}

// Passare alla pagina del report di analisi（Report）
const goToReport = () => {
  if (selectedProject.value?.report_id) {
    router.push({
      name: 'Report',
      params: { reportId: selectedProject.value.report_id }
    })
    closeModal()
  }
}

const confirmDeleteProject = async (project) => {
  if (!project?.simulation_id) return

  const label = formatSimulationId(project.simulation_id)
  const confirmed = window.confirm(`Eliminare la simulazione ${label}? L'operazione non può essere annullata.`)
  if (!confirmed) return

  loadingDeleteId.value = project.simulation_id
  try {
    const response = await deleteSimulation(project.simulation_id)
    if (response?.success) {
      if (selectedProject.value?.simulation_id === project.simulation_id) {
        closeModal()
      }
      await loadHistory()
    } else {
      alert(response?.error || 'Impossibile eliminare la simulazione')
    }
  } catch (error) {
    console.error('Errore eliminazione simulazione:', error)
    alert(error?.message || 'Errore durante l’eliminazione della simulazione')
  } finally {
    loadingDeleteId.value = null
  }
}

// Carica elementi storici
const loadHistory = async () => {
  try {
    loading.value = true
    const response = await getSimulationHistory(20)
    if (response.success) {
      projects.value = response.data || []
    }
  } catch (error) {
    console.error('Carica elementi storicifallire:', error)
    projects.value = []
  } finally {
    loading.value = false
  }
}

// inizializzazione IntersectionObserver
const initObserver = () => {
  if (observer) {
    observer.disconnect()
  }
  
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const shouldExpand = entry.isIntersecting
        
        // Aggiorna lo stato di destinazione da eseguire (l'ultimo stato di destinazione deve essere registrato indipendentemente dal fatto che sia in animazione o meno)）
        pendingState = shouldExpand
        
        // Cancella il timer anti-shake precedente (il nuovo intento di scorrimento sovrascriverà quello vecchio）
        if (expandDebounceTimer) {
          clearTimeout(expandDebounceTimer)
          expandDebounceTimer = null
        }
        
        // Se l'animazione è in corso, solo lo stato viene registrato ed elaborato al termine dell'animazione.
        if (isAnimating) return
        
        // Se lo stato di destinazione è lo stesso dello stato corrente, non è richiesta alcuna elaborazione
        if (shouldExpand === isExpanded.value) {
          pendingState = null
          return
        }
        
        // Utilizzare la commutazione dello stato di ritardo anti-shake per evitare un rapido sfarfallio
        // Ritardo più breve durante l'espansione(50ms)，Ritardo più lungo durante la retrazione(200ms)per aumentare la stabilità
        const delay = shouldExpand ? 50 : 200
        
        expandDebounceTimer = setTimeout(() => {
          // Controlla se l'animazione è in corso
          if (isAnimating) return
          
          // Verificare se lo stato di esecuzione in sospeso deve ancora essere eseguito (potrebbe essere stato sovrascritto dallo scorrimento successivo）
          if (pendingState === null || pendingState === isExpanded.value) return
          
          // Imposta il blocco dell'animazione
          isAnimating = true
          isExpanded.value = pendingState
          pendingState = null
          
          // Sblocca quando l'animazione è completa e controlla se ci sono cambiamenti di stato in sospeso
          setTimeout(() => {
            isAnimating = false
            
            // Al termine dell'animazione, controlla se c'è un nuovo stato da eseguire
            if (pendingState !== null && pendingState !== isExpanded.value) {
              // Ritardare l'esecuzione per un breve periodo di tempo per evitare di passare troppo rapidamente
              expandDebounceTimer = setTimeout(() => {
                if (pendingState !== null && pendingState !== isExpanded.value) {
                  isAnimating = true
                  isExpanded.value = pendingState
                  pendingState = null
                  setTimeout(() => {
                    isAnimating = false
                  }, 750)
                }
              }, 100)
            }
          }, 750)
        }, delay)
      })
    },
    {
      // Utilizza più soglie per rendere il rilevamento più fluido
      threshold: [0.4, 0.6, 0.8],
      // Regola rootMargin, la parte inferiore della finestra si restringe verso l'alto ed è necessario uno scorrimento maggiore per attivare l'espansione.
      rootMargin: '0px 0px -150px 0px'
    }
  )
  
  // iniziare ad osservare
  if (historyContainer.value) {
    observer.observe(historyContainer.value)
  }
}

// Monitora le modifiche al routing e ricarica i dati quando torni alla home page
watch(() => route.path, (newPath) => {
  if (newPath === '/') {
    loadHistory()
  }
})

onMounted(async () => {
  // Assicurati che il rendering DOM sia completo prima di caricare i dati
  await nextTick()
  await loadHistory()
  
  // Attendi il rendering del DOM prima di inizializzare l'osservatore
  setTimeout(() => {
    initObserver()
  }, 100)
})

// Se si utilizza il metodo keep-alive, ricaricare i dati quando il componente viene attivato
onActivated(() => {
  loadHistory()
})

onUnmounted(() => {
  // pulire Intersection Observer
  if (observer) {
    observer.disconnect()
    observer = null
  }
  // Cancella timer anti-shake
  if (expandDebounceTimer) {
    clearTimeout(expandDebounceTimer)
    expandDebounceTimer = null
  }
})
</script>

<style scoped>
/* contenitore */
.history-database {
  position: relative;
  width: 100%;
  min-height: 280px;
  margin-top: 40px;
  padding: 35px 0 40px;
  overflow: visible;
}

/* Visualizzazione semplificata quando non sono presenti elementi */
.history-database.no-projects {
  min-height: auto;
  padding: 40px 0 20px;
}

/* Sfondo della griglia tecnologica */
.tech-grid-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  pointer-events: none;
}

/* Crea una griglia di quadrati a spaziatura fissa utilizzando un motivo di sfondo CSS */
.grid-pattern {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    linear-gradient(to right, rgba(0, 0, 0, 0.05) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(0, 0, 0, 0.05) 1px, transparent 1px);
  background-size: 50px 50px;
  /* Il posizionamento inizia dall'angolo in alto a sinistra. Quando l'altezza cambia, si espande solo nella parte inferiore e non influisce sulla posizione della griglia esistente. */
  background-position: top left;
}

.gradient-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    linear-gradient(to right, rgba(255, 255, 255, 0.9) 0%, transparent 15%, transparent 85%, rgba(255, 255, 255, 0.9) 100%),
    linear-gradient(to bottom, rgba(255, 255, 255, 0.8) 0%, transparent 20%, transparent 80%, rgba(255, 255, 255, 0.8) 100%);
  pointer-events: none;
}

/* area del titolo */
.section-header {
  position: relative;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  margin-bottom: 24px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  padding: 0 40px;
}

.section-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #E5E7EB, transparent);
  max-width: 300px;
}

.section-title {
  font-size: 0.8rem;
  font-weight: 500;
  color: #9CA3AF;
  letter-spacing: 3px;
  text-transform: uppercase;
}

/* contenitore per carte */
.cards-container {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 0 40px;
  transition: min-height 700ms cubic-bezier(0.23, 1, 0.32, 1);
  /* min-height Calcolato dinamicamente da JS, adattivo in base al numero di carte */
}

/* scheda progetto */
.project-card {
  position: absolute;
  width: 280px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 0;
  padding: 14px;
  cursor: pointer;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  transition: box-shadow 0.3s ease, border-color 0.3s ease, transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1);
}

.delete-card-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 5;
  width: 28px;
  height: 28px;
  border: 1px solid #F3D3D3;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.95);
  color: #B42318;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.delete-card-btn:hover {
  background: #FFF5F5;
  border-color: #F5A6A6;
}

.delete-card-btn:disabled,
.modal-delete-btn:disabled {
  opacity: 0.6;
  cursor: progress;
}

.project-card:hover {
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
  border-color: rgba(0, 0, 0, 0.4);
  z-index: 1000 !important;
}

.project-card.hovering {
  z-index: 1000 !important;
}

/* intestazione della carta */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F3F4F6;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.7rem;
}

.card-id {
  color: #6B7280;
  letter-spacing: 0.5px;
  font-weight: 500;
}

/* Set di icone di stato della funzione */
.card-status-icons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-icon {
  font-size: 0.75rem;
  transition: all 0.2s ease;
  cursor: default;
}

.status-icon.available {
  opacity: 1;
}

/* Colori per diverse funzioni */
.status-icon:nth-child(1).available { color: #3B82F6; } /* Costruzione del grafico - blu */
.status-icon:nth-child(2).available { color: #F59E0B; } /* Configurazione dell'ambiente: arancione */
.status-icon:nth-child(3).available { color: #10B981; } /* Rapporto di analisi - Verde */

.status-icon.unavailable {
  color: #D1D5DB;
  opacity: 0.5;
}

/* Visualizzazione dell'avanzamento del giro */
.card-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  letter-spacing: 0.5px;
  font-weight: 600;
  font-size: 0.65rem;
}

.status-dot {
  font-size: 0.5rem;
}

/* Colore dello stato di avanzamento */
.card-progress.completed { color: #10B981; }    /* Completato - Verde */
.card-progress.in-progress { color: #F59E0B; }  /* In corso - Arancione */
.card-progress.not-started { color: #9CA3AF; }  /* Non avviato: grigio */
.card-status.pending { color: #9CA3AF; }

/* area elenco file */
.card-files-wrapper {
  position: relative;
  width: 100%;
  min-height: 48px;
  max-height: 110px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f4 100%);
  border-radius: 4px;
  border: 1px solid #e8eaed;
  overflow: hidden;
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* Altri suggerimenti sui file */
.files-more {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3px 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  color: #6B7280;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 3px;
  letter-spacing: 0.3px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 3px;
  transition: all 0.2s ease;
}

.file-item:hover {
  background: rgba(255, 255, 255, 1);
  transform: translateX(2px);
  border-color: #e5e7eb;
}

/* Stile semplice dell'etichetta del file */
.file-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 16px;
  padding: 0 4px;
  border-radius: 2px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  font-weight: 600;
  line-height: 1;
  text-transform: uppercase;
  letter-spacing: 0.2px;
  flex-shrink: 0;
  min-width: 28px;
}

/* Combinazione di colori a bassa saturazione - Sistema di colori Morandi */
.file-tag.pdf { background: #f2e6e6; color: #a65a5a; }
.file-tag.doc { background: #e6eff5; color: #5a7ea6; }
.file-tag.xls { background: #e6f2e8; color: #5aa668; }
.file-tag.ppt { background: #f5efe6; color: #a6815a; }
.file-tag.txt { background: #f0f0f0; color: #757575; }
.file-tag.code { background: #eae6f2; color: #815aa6; }
.file-tag.img { background: #e6f2f2; color: #5aa6a6; }
.file-tag.zip { background: #f2f0e6; color: #a69b5a; }
.file-tag.other { background: #f3f4f6; color: #6b7280; }

.file-name {
  font-family: 'Inter', sans-serif;
  font-size: 0.7rem;
  color: #4b5563;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.1px;
}

/* Segnaposto quando non è presente alcun file */
.files-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 48px;
  color: #9CA3AF;
}

.empty-file-icon {
  font-size: 1rem;
  opacity: 0.5;
}

.empty-file-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  letter-spacing: 0.5px;
}

/* Effetto area file quando si passa con il mouse */
.project-card:hover .card-files-wrapper {
  border-color: #d1d5db;
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
}

/* decorazione d'angolo */
.corner-mark.top-left-only {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 8px;
  height: 8px;
  border-top: 1.5px solid rgba(0, 0, 0, 0.4);
  border-left: 1.5px solid rgba(0, 0, 0, 0.4);
  pointer-events: none;
  z-index: 10;
}

/* titolo della carta */
.card-title {
  font-family: 'Inter', -apple-system, sans-serif;
  font-size: 0.9rem;
  font-weight: 700;
  color: #111827;
  margin: 0 0 6px 0;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.3s ease;
}

.project-card:hover .card-title {
  color: #2563EB;
}

/* Descrizione della carta */
.card-desc {
  font-family: 'Inter', sans-serif;
  font-size: 0.75rem;
  color: #6B7280;
  margin: 0 0 16px 0;
  line-height: 1.5;
  height: 34px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* fondo della carta */
.card-footer {
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #F3F4F6;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #9CA3AF;
  font-weight: 500;
}

/* combinazione data/ora */
.card-datetime {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Visualizzazione dell'avanzamento del giro inferiore */
.card-footer .card-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  letter-spacing: 0.5px;
  font-weight: 600;
  font-size: 0.65rem;
}

.card-footer .status-dot {
  font-size: 0.5rem;
}

/* Colore dello stato di avanzamento: in basso */
.card-footer .card-progress.completed { color: #10B981; }
.card-footer .card-progress.in-progress { color: #F59E0B; }
.card-footer .card-progress.not-started { color: #9CA3AF; }

/* Linea decorativa inferiore */
.card-bottom-line {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  width: 0;
  background-color: #000;
  transition: width 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  z-index: 20;
}

.project-card:hover .card-bottom-line {
  width: 100%;
}

/* Stato vuoto */
.empty-state, .loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 48px;
  color: #9CA3AF;
}

.empty-icon {
  font-size: 2rem;
  opacity: 0.5;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #E5E7EB;
  border-top-color: #6B7280;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Reattivo */
@media (max-width: 1200px) {
  .project-card {
    width: 240px;
  }
}

@media (max-width: 768px) {
  .cards-container {
    padding: 0 20px;
  }
  .project-card {
    width: 200px;
  }
}

/* ===== Historical replay details pop-up window style ===== */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: #FFFFFF;
  width: 560px;
  max-width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
}

/* transizione animata */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-content {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .modal-content {
  transition: all 0.2s ease-in;
}

.modal-enter-from .modal-content {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

.modal-leave-to .modal-content {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

/* Intestazione popup */
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  border-bottom: 1px solid #F3F4F6;
  background: #FFFFFF;
}

.modal-title-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.modal-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
  letter-spacing: 0.5px;
}

.modal-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  background: #F9FAFB;
}

.modal-progress.completed { color: #10B981; background: rgba(16, 185, 129, 0.1); }
.modal-progress.in-progress { color: #F59E0B; background: rgba(245, 158, 11, 0.1); }
.modal-progress.not-started { color: #9CA3AF; background: #F3F4F6; }

.modal-create-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #9CA3AF;
  letter-spacing: 0.3px;
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  font-size: 1.5rem;
  color: #9CA3AF;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border-radius: 6px;
}

.modal-close:hover {
  background: #F3F4F6;
  color: #111827;
}

/* Contenuti pop-up */
.modal-body {
  padding: 24px 32px;
}

.modal-section {
  margin-bottom: 24px;
}

.modal-section:last-child {
  margin-bottom: 0;
}

.modal-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  font-weight: 500;
}

.modal-requirement {
  font-size: 0.95rem;
  color: #374151;
  line-height: 1.6;
  padding: 16px;
  background: #F9FAFB;
  border: 1px solid #F3F4F6;
  border-radius: 8px;
}

.modal-files {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 200px;
  overflow-y: auto;
  padding-right: 4px;
}

/* Stile personalizzato della barra di scorrimento */
.modal-files::-webkit-scrollbar {
  width: 4px;
}

.modal-files::-webkit-scrollbar-track {
  background: #F3F4F6;
  border-radius: 2px;
}

.modal-files::-webkit-scrollbar-thumb {
  background: #D1D5DB;
  border-radius: 2px;
}

.modal-files::-webkit-scrollbar-thumb:hover {
  background: #9CA3AF;
}

.modal-file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.modal-file-item:hover {
  border-color: #D1D5DB;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}

.modal-file-name {
  font-size: 0.85rem;
  color: #4B5563;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-empty {
  font-size: 0.85rem;
  color: #9CA3AF;
  padding: 16px;
  background: #F9FAFB;
  border: 1px dashed #E5E7EB;
  border-radius: 6px;
  text-align: center;
}

/* Linea di divisione della riproduzione della deduzione */
.modal-divider {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 32px 0;
  background: #FFFFFF;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #E5E7EB, transparent);
}

.divider-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #9CA3AF;
  letter-spacing: 2px;
  text-transform: uppercase;
  white-space: nowrap;
}

/* Pulsanti di navigazione */
.modal-actions {
  display: flex;
  gap: 16px;
  padding: 20px 32px;
  background: #FFFFFF;
}

.modal-danger-zone {
  display: flex;
  justify-content: flex-end;
  padding: 0 32px 20px;
  background: #FFFFFF;
}

.modal-delete-btn {
  border: 1px solid #F3D3D3;
  background: #FFF5F5;
  color: #B42318;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.modal-delete-btn:hover:not(:disabled) {
  background: #FFECEC;
}

.modal-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  background: #FFFFFF;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
}

.modal-btn:hover:not(:disabled) {
  border-color: #000000;
  transform: translateY(-2px);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #F9FAFB;
}

.btn-step {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 500;
  color: #9CA3AF;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.btn-icon {
  font-size: 1.4rem;
  line-height: 1;
  transition: color 0.2s ease;
}

.btn-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #4B5563;
}

.modal-btn.btn-project .btn-icon { color: #3B82F6; }
.modal-btn.btn-simulation .btn-icon { color: #F59E0B; }
.modal-btn.btn-report .btn-icon { color: #10B981; }

.modal-btn:hover:not(:disabled) .btn-text {
  color: #111827;
}

/* Prompt non riproducibile */
.modal-playback-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 32px 20px;
  background: #FFFFFF;
}

.hint-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #9CA3AF;
  letter-spacing: 0.3px;
  text-align: center;
  line-height: 1.5;
}
</style>
