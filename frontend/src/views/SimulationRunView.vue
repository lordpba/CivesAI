<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">MIROFISH</div>
      </div>
      
      <div class="header-center">
        <div class="view-switcher">
          <button 
            v-for="mode in ['graph', 'split', 'workbench']" 
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: 'Atlante', split: 'doppia colonna', workbench: 'banco da lavoro' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Step 3/5</span>
          <span class="step-name">Avvia la simulazione</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel 
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="3"
          :isSimulating="isSimulating"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step3 Avvia la simulazione -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <Step3Simulation
          :simulationId="currentSimulationId"
          :maxRounds="maxRounds"
          :minutesPerRound="minutesPerRound"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step3Simulation from '../components/Step3Simulation.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation, getSimulationConfig, stopSimulation, closeSimulationEnv, getEnvStatus } from '../api/simulation'

const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  simulationId: String
})

// Layout State
const viewMode = ref('split')

// Data State
const currentSimulationId = ref(route.params.simulationId)
// Ottieni maxRounds direttamente dal parametro di query durante l'inizializzazione per garantire che il sottocomponente possa ottenere immediatamente il valore
const maxRounds = ref(route.query.maxRounds ? parseInt(route.query.maxRounds) : null)
const minutesPerRound = ref(30) // L'impostazione predefinita è 30 minuti per round
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('processing') // processing | completed | error

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Completed'
  return 'Running'
})

const isSimulating = computed(() => currentStatus.value === 'processing')

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
    systemLogs.value.shift()
  }
}

const updateStatus = (status) => {
  currentStatus.value = status
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleGoBack = async () => {
  // Prima di tornare al passaggio 2, chiudere la simulazione in esecuzione
  addLog('Prepararsi a tornare al passaggio 2, chiudere la simulazione...')
  
  // Smetti di votare
  stopGraphRefresh()
  
  try {
    // Per prima cosa prova a chiudere con garbo l'ambiente di simulazione
    const envStatusRes = await getEnvStatus({ simulation_id: currentSimulationId.value })
    
    if (envStatusRes.success && envStatusRes.data?.env_alive) {
      addLog("Chiusura dell'ambiente di simulazione...")
      try {
        await closeSimulationEnv({ 
          simulation_id: currentSimulationId.value,
          timeout: 10
        })
        addLog("✓ L'ambiente di simulazione è chiuso")
      } catch (closeErr) {
        addLog(`Impossibile chiudere l'ambiente di simulazione, provare a forzare l'arresto...`)
        try {
          await stopSimulation({ simulation_id: currentSimulationId.value })
          addLog('✓ La simulazione è stata costretta a fermarsi')
        } catch (stopErr) {
          addLog(`L'arresto forzato non è riuscito: ${stopErr.message}`)
        }
      }
    } else {
      // L'ambiente non è in esecuzione, controlla se è necessario interrompere il processo
      if (isSimulating.value) {
        addLog('Arresto del processo di simulazione...')
        try {
          await stopSimulation({ simulation_id: currentSimulationId.value })
          addLog('✓ La simulazione è stata interrotta')
        } catch (err) {
          addLog(`Interruzione della simulazione non riuscita: ${err.message}`)
        }
      }
    }
  } catch (err) {
    addLog(`Il controllo dello stato della simulazione non è riuscito: ${err.message}`)
  }
  
  // Ritorna a Step 2 (Configurazione dell'ambiente)
  router.push({ name: 'Simulation', params: { simulationId: currentSimulationId.value } })
}

const handleNextStep = () => {
  // Step3Simulation Il componente gestirà direttamente la generazione dei report e i salti di routing
  //Questo metodo viene utilizzato solo come backup
  addLog('entrare Step 4: Generazione di rapporti')
}

// --- Data Logic ---
const loadSimulationData = async () => {
  try {
    addLog(`Carica i dati di simulazione: ${currentSimulationId.value}`)
    
    // Ottieni informazioni sulla simulazione
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data) {
      const simData = simRes.data
      
      // Ottieni la configurazione della simulazione per ottenere minutes_per_round
      try {
        const configRes = await getSimulationConfig(currentSimulationId.value)
        if (configRes.success && configRes.data?.time_config?.minutes_per_round) {
          minutesPerRound.value = configRes.data.time_config.minutes_per_round
          addLog(`Configurazione dell'ora: ogni giro ${minutesPerRound.value} Minuti`)
        }
      } catch (configErr) {
        addLog(`Impossibile ottenere la configurazione dell'ora, utilizzare il valore predefinito: ${minutesPerRound.value}minuti/giro`)
      }
      
      // Ottieni informazioni sul progetto
      if (simData.project_id) {
        const projRes = await getProject(simData.project_id)
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          addLog(`Progetto caricato con successo: ${projRes.data.project_id}`)
          
          // Ottieni dati grafici
          if (projRes.data.graph_id) {
            await loadGraph(projRes.data.graph_id)
          }
        }
      }
    } else {
      addLog(`Impossibile caricare i dati di simulazione: ${simRes.error || 'errore sconosciuto'}`)
    }
  } catch (err) {
    addLog(`Eccezione di caricamento: ${err.message}`)
  }
}

const loadGraph = async (graphId) => {
  // Durante la simulazione, l'aggiornamento automatico non visualizza il caricamento a schermo intero per evitare sfarfallio
  // Visualizzato durante l'aggiornamento manuale o il caricamento iniziale loading
  if (!isSimulating.value) {
    graphLoading.value = true
  }
  
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      if (!isSimulating.value) {
        addLog('Dati dello spettro caricati correttamente')
      }
    }
  } catch (err) {
    addLog(`Impossibile caricare la mappa: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    loadGraph(projectData.value.graph_id)
  }
}

// --- Auto Refresh Logic ---
let graphRefreshTimer = null

const startGraphRefresh = () => {
  if (graphRefreshTimer) return
  addLog("Abilita l'aggiornamento della mappa in tempo reale (30s)")
  // Aggiorna immediatamente, quindi ogni 30 secondi
  graphRefreshTimer = setInterval(refreshGraph, 30000)
}

const stopGraphRefresh = () => {
  if (graphRefreshTimer) {
    clearInterval(graphRefreshTimer)
    graphRefreshTimer = null
    addLog("Interrompe l'aggiornamento in tempo reale della mappa")
  }
}

watch(isSimulating, (newValue) => {
  if (newValue) {
    startGraphRefresh()
  } else {
    stopGraphRefresh()
  }
}, { immediate: true })

onMounted(() => {
  addLog('SimulationRunView inizializzazione')
  
  // Registrazione della configurazione maxRounds (il valore è stato ottenuto dal parametro di query al momento dell'inizializzazione）
  if (maxRounds.value) {
    addLog(`Turni di simulazione personalizzati: ${maxRounds.value}`)
  }
  
  loadSimulationData()
})

onUnmounted(() => {
  stopGraphRefresh()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #FFF;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: #F5F5F5;
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid #EAEAEA;
}
</style>

