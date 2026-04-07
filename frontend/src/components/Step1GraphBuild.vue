<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <!-- Step 01: Ontology -->
      <div class="step-card" :class="{ 'active': currentPhase === 0, 'completed': currentPhase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">Generazione Ontologia PA</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 0" class="badge success">Completato</span>
            <span v-else-if="currentPhase === 0" class="badge processing">In Corso</span>
            <span v-else class="badge pending">In Attesa</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/graph/ontology/generate</p>
          <p class="description">
            L'Intelligenza Artificiale analizza il documento della PA per estrarre le radici normative e la struttura civica.
          </p>

          <!-- Loading / Progress -->
          <div v-if="currentPhase === 0 && ontologyProgress" class="progress-section">
            <div class="spinner-sm"></div>
            <span>{{ ontologyProgress.message || 'Analisi delibere in corso...' }}</span>
          </div>

          <!-- Detail Overlay -->
          <div v-if="selectedOntologyItem" class="ontology-detail-overlay">
            <div class="detail-header">
               <div class="detail-title-group">
                  <span class="detail-type-badge">{{ selectedOntologyItem.itemType === 'entity' ? 'ENTITY' : 'RELATION' }}</span>
                  <span class="detail-name">{{ selectedOntologyItem.name }}</span>
               </div>
               <button class="close-btn" @click="selectedOntologyItem = null">×</button>
            </div>
            <div class="detail-body">
               <div class="detail-desc">{{ selectedOntologyItem.description }}</div>
               
               <!-- Attributes -->
               <div class="detail-section" v-if="selectedOntologyItem.attributes?.length">
                  <span class="section-label">ATTRIBUTES</span>
                  <div class="attr-list">
                     <div v-for="attr in selectedOntologyItem.attributes" :key="attr.name" class="attr-item">
                        <span class="attr-name">{{ attr.name }}</span>
                        <span class="attr-type">({{ attr.type }})</span>
                        <span class="attr-desc">{{ attr.description }}</span>
                     </div>
                  </div>
               </div>

               <!-- Examples (Entity) -->
               <div class="detail-section" v-if="selectedOntologyItem.examples?.length">
                  <span class="section-label">EXAMPLES</span>
                  <div class="example-list">
                     <span v-for="ex in selectedOntologyItem.examples" :key="ex" class="example-tag">{{ ex }}</span>
                  </div>
               </div>

               <!-- Source/Target (Relation) -->
               <div class="detail-section" v-if="selectedOntologyItem.source_targets?.length">
                  <span class="section-label">CONNECTIONS</span>
                  <div class="conn-list">
                     <div v-for="(conn, idx) in selectedOntologyItem.source_targets" :key="idx" class="conn-item">
                        <span class="conn-node">{{ conn.source }}</span>
                        <span class="conn-arrow">→</span>
                        <span class="conn-node">{{ conn.target }}</span>
                     </div>
                  </div>
               </div>
            </div>
          </div>

          <!-- Generated Entity Tags -->
          <div v-if="projectData?.ontology?.entity_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED ENTITY TYPES</span>
            <div class="tags-list">
              <span 
                v-for="entity in projectData.ontology.entity_types" 
                :key="entity.name" 
                class="entity-tag clickable"
                @click="selectOntologyItem(entity, 'entity')"
              >
                {{ entity.name }}
              </span>
            </div>
          </div>

          <!-- Generated Relation Tags -->
          <div v-if="projectData?.ontology?.edge_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED RELATION TYPES</span>
            <div class="tags-list">
              <span 
                v-for="rel in projectData.ontology.edge_types" 
                :key="rel.name" 
                class="entity-tag clickable"
                @click="selectOntologyItem(rel, 'relation')"
              >
                {{ rel.name }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: Graph Build -->
      <div class="step-card" :class="{ 'active': currentPhase === 1, 'completed': currentPhase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">Creazione GraphRAG</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 1" class="badge success">Completato</span>
            <span v-else-if="currentPhase === 1" class="badge processing">{{ buildProgress?.progress || 0 }}%</span>
            <span v-else class="badge pending">In Attesa</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/graph/build</p>
          <p class="description">
            Sfruttando l'ontologia PA, ZEP Memory scansiona i documenti ed estrae reti, attori locali e la sintesi cittadina.
          </p>
          
          <!-- Stats Cards -->
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.nodes }}</span>
              <span class="stat-label">Nodi Entità</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.edges }}</span>
              <span class="stat-label">Relazioni</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.types }}</span>
              <span class="stat-label">Tipi Schema</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 03: Complete -->
      <div class="step-card" :class="{ 'active': currentPhase === 2, 'completed': currentPhase >= 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">Pronto all'Uso</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase >= 2" class="badge accent">Operativo</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">La Mappa Relazionale è completata. Puoi avviare la simulazione cittadina.</p>
          <div class="calibration-panel">
            <div class="calibration-header">
              <div>
                <span class="preview-title">Calibrazione NUTS-2</span>
                <p class="calibration-subtitle">La regione aggiorna il reality seed e guida la generazione delle personas.</p>
              </div>
              <button class="refresh-btn" type="button" :disabled="calibrationLoading" @click="reloadCalibrationData">
                {{ calibrationLoading ? 'Aggiornamento...' : 'Ricarica dati' }}
              </button>
            </div>

            <div class="calibration-grid">
              <div class="calibration-select-card">
                <label class="select-label">Regione NUTS-2</label>
                <select v-model="selectedRegionCode" class="region-select" :disabled="calibrationLoading || calibrationRegions.length === 0">
                  <option v-for="region in calibrationRegions" :key="region.nuts2_code" :value="region.nuts2_code">
                    {{ region.nuts2_code }} - {{ region.name }}
                  </option>
                </select>
                <p class="select-hint">I dati si aggiornano subito qui sotto e vengono usati nella simulazione.</p>
              </div>

              <div class="calibration-summary-card" v-if="calibrationProfile">
                <div class="summary-row">
                  <span class="summary-label">Zona</span>
                  <span class="summary-value">{{ calibrationProfile.cultural_zone }}</span>
                </div>
                <div class="summary-row">
                  <span class="summary-label">Codice NUTS</span>
                  <span class="summary-value mono">{{ calibrationProfile.nuts2_code }}</span>
                </div>
                <div class="summary-row">
                  <span class="summary-label">Stile</span>
                  <span class="summary-value">{{ calibrationProfile.derived?.communication_style }}</span>
                </div>
                <div class="summary-row">
                  <span class="summary-label">Attività</span>
                  <span class="summary-value">×{{ calibrationProfile.derived?.activity_multiplier }}</span>
                </div>
              </div>
            </div>

            <div v-if="calibrationProfile" class="calibration-layers">
              <div class="layer-card">
                <span class="layer-title">Economico</span>
                <div class="layer-item">PIL pro capite: €{{ calibrationProfile.layers?.economic?.indicators?.gdp_per_capita }}</div>
                <div class="layer-item">Reddito mediano: €{{ calibrationProfile.layers?.economic?.indicators?.median_income_eur }}</div>
                <div class="layer-item">Occupazione: {{ calibrationProfile.layers?.economic?.indicators?.employment_rate }}%</div>
                <div class="layer-source">{{ calibrationProfile.layers?.economic?.source }}</div>
              </div>

              <div class="layer-card">
                <span class="layer-title">Culturale</span>
                <div class="layer-item">PDI: {{ calibrationProfile.layers?.cultural?.hofstede_6d?.PDI }}</div>
                <div class="layer-item">IDV: {{ calibrationProfile.layers?.cultural?.hofstede_6d?.IDV }}</div>
                <div class="layer-item">UAI: {{ calibrationProfile.layers?.cultural?.hofstede_6d?.UAI }}</div>
                <div class="layer-source">{{ calibrationProfile.layers?.cultural?.source }}</div>
              </div>

              <div class="layer-card">
                <span class="layer-title">Demografico</span>
                <div class="layer-item">Età mediana: {{ calibrationProfile.layers?.demographic?.indicators?.median_age }}</div>
                <div class="layer-item">Disoccupazione: {{ calibrationProfile.layers?.demographic?.indicators?.unemployment_rate }}%</div>
                <div class="layer-item">Internet: {{ calibrationProfile.layers?.demographic?.indicators?.internet_users_pct }}%</div>
                <div class="layer-source">{{ calibrationProfile.layers?.demographic?.source }}</div>
              </div>

              <div class="layer-card">
                <span class="layer-title">Sociale</span>
                <div class="layer-item">Fiducia interpersonale: {{ calibrationProfile.layers?.social?.indicators?.interpersonal_trust }}</div>
                <div class="layer-item">Fiducia istituzionale: {{ calibrationProfile.layers?.social?.indicators?.institutional_trust }}</div>
                <div class="layer-item">Soddisfazione vita: {{ calibrationProfile.layers?.social?.indicators?.life_satisfaction_mean }}</div>
                <div class="layer-source">{{ calibrationProfile.layers?.social?.source }}</div>
              </div>
            </div>

            <div v-if="calibrationProfile?.summary" class="calibration-note">
              {{ calibrationProfile.summary }}
            </div>
          </div>
          <button 
            class="action-btn" 
            :disabled="currentPhase < 2 || creatingSimulation"
            @click="handleEnterEnvSetup"
          >
            <span v-if="creatingSimulation" class="spinner-sm"></span>
            {{ creatingSimulation ? 'Allestimento in corso...' : 'Inizializza Ambiente con NUTS ➝' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SYSTEM DASHBOARD</span>
        <span class="log-id">{{ projectData?.project_id || 'NO_PROJECT' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createSimulation, getCalibrationRegions, getCalibrationRegion } from '../api/simulation'

const router = useRouter()

const props = defineProps({
  currentPhase: { type: Number, default: 0 },
  projectData: Object,
  ontologyProgress: Object,
  buildProgress: Object,
  graphData: Object,
  systemLogs: { type: Array, default: () => [] }
})

defineEmits(['next-step'])

const selectedOntologyItem = ref(null)
const logContent = ref(null)
const creatingSimulation = ref(false)
const calibrationRegions = ref([])
const calibrationProfile = ref(null)
const selectedRegionCode = ref('')
const calibrationLoading = ref(false)

const loadCalibrationRegions = async () => {
  calibrationLoading.value = true
  try {
    const res = await getCalibrationRegions()
    if (res.success && res.data?.regions) {
      calibrationRegions.value = res.data.regions
      if (!selectedRegionCode.value && calibrationRegions.value.length > 0) {
        selectedRegionCode.value = calibrationRegions.value[0].nuts2_code
      }
    }
  } catch (err) {
    console.error('Impossibile caricare le regioni di calibrazione:', err)
  } finally {
    calibrationLoading.value = false
  }
}

const loadCalibrationRegion = async (nuts2Code) => {
  if (!nuts2Code) return
  calibrationLoading.value = true
  try {
    const res = await getCalibrationRegion(nuts2Code)
    if (res.success && res.data) {
      calibrationProfile.value = res.data
    }
  } catch (err) {
    console.error(`Impossibile caricare la regione ${nuts2Code}:`, err)
  } finally {
    calibrationLoading.value = false
  }
}

const reloadCalibrationData = async () => {
  await loadCalibrationRegions()
  if (selectedRegionCode.value) {
    await loadCalibrationRegion(selectedRegionCode.value)
  }
}

const ensureCalibrationLoaded = async () => {
  if (!calibrationRegions.value.length) {
    await loadCalibrationRegions()
  }
  if (selectedRegionCode.value) {
    await loadCalibrationRegion(selectedRegionCode.value)
  }
}

// Entra nella costruzione dell'ambiente: crea simulazione e salta
const handleEnterEnvSetup = async () => {
  if (!props.projectData?.project_id || !props.projectData?.graph_id) {
    console.error('Informazioni mancanti sul progetto o sulla mappa')
    return
  }

  await ensureCalibrationLoaded()
  if (!selectedRegionCode.value) {
    alert('Seleziona una regione NUTS-2 prima di inizializzare la simulazione.')
    return
  }
  
  creatingSimulation.value = true
  
  try {
    const res = await createSimulation({
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      enable_twitter: true,
      enable_reddit: true,
      nuts2_region: selectedRegionCode.value
    })
    
    if (res.success && res.data?.simulation_id) {
      // Vai alla pagina della simulazione
      router.push({
        name: 'Simulation',
        params: { simulationId: res.data.simulation_id }
      })
    } else {
      console.error('Impossibile creare la simulazione:', res.error)
      alert('Impossibile creare la simulazione: ' + (res.error || 'errore sconosciuto'))
    }
  } catch (err) {
    console.error("Crea un'eccezione fittizia:", err)
    alert("Crea un'eccezione fittizia: " + err.message)
  } finally {
    creatingSimulation.value = false
  }
}

const selectOntologyItem = (item, type) => {
  selectedOntologyItem.value = { ...item, itemType: type }
}

const graphStats = computed(() => {
  const nodes = props.graphData?.node_count || props.graphData?.nodes?.length || 0
  const edges = props.graphData?.edge_count || props.graphData?.edges?.length || 0
  const types = props.projectData?.ontology?.entity_types?.length || 0
  return { nodes, edges, types }
})

const formatDate = (dateStr) => {
  if (!dateStr) return '--:--:--'
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour12: false }) + '.' + d.getMilliseconds()
}

// Auto-scroll logs
watch(() => props.systemLogs.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

watch(selectedRegionCode, async (newValue) => {
  if (newValue) {
    await loadCalibrationRegion(newValue)
  }
})

onMounted(() => {
  loadCalibrationRegions().then(() => {
    if (selectedRegionCode.value) {
      loadCalibrationRegion(selectedRegionCode.value)
    }
  })
})
</script>

<style scoped>
.workbench-panel {
  height: 100%;
  background-color: #FAFAFA;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-card {
  background: #FFF;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #EAEAEA;
  transition: all 0.3s ease;
  position: relative; /* For absolute overlay */
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #E0E0E0;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #000;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.success { background: #E8F5E9; color: #2E7D32; }
.badge.processing { background: #FF5722; color: #FFF; }
.badge.accent { background: #FF5722; color: #FFF; }
.badge.pending { background: #F5F5F5; color: #999; }

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
}

.description {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  margin-bottom: 16px;
}

.calibration-panel {
  margin: 12px 0 16px;
  padding: 14px;
  border: 1px solid #ECECEC;
  border-radius: 8px;
  background: linear-gradient(180deg, #FFFFFF 0%, #FAFAFA 100%);
}

.calibration-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.calibration-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #666;
  line-height: 1.45;
}

.refresh-btn {
  border: 1px solid #DDD;
  background: #FFF;
  color: #222;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: progress;
}

.calibration-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  gap: 10px;
}

.calibration-select-card,
.calibration-summary-card,
.layer-card {
  border: 1px solid #ECECEC;
  border-radius: 8px;
  background: #FFF;
  padding: 12px;
}

.select-label,
.layer-title {
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: #444;
  margin-bottom: 8px;
}

.region-select {
  width: 100%;
  border: 1px solid #D8D8D8;
  border-radius: 6px;
  padding: 9px 10px;
  font-size: 12px;
  background: #fff;
}

.select-hint,
.layer-source,
.calibration-note {
  margin-top: 8px;
  font-size: 11px;
  color: #666;
  line-height: 1.45;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 0;
  border-bottom: 1px dashed #EEE;
}

.summary-row:last-child {
  border-bottom: none;
}

.summary-label {
  font-size: 11px;
  color: #666;
}

.summary-value,
.layer-item {
  font-size: 11px;
  font-weight: 600;
  color: #111;
}

.calibration-layers {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.layer-item {
  padding: 2px 0;
  font-weight: 500;
}

.mono {
  font-family: 'JetBrains Mono', monospace;
}

@media (max-width: 1100px) {
  .calibration-grid,
  .calibration-layers {
    grid-template-columns: 1fr;
  }
}

/* Step 01 Tags */
.tags-container {
  margin-top: 12px;
  transition: opacity 0.3s;
}

.tags-container.dimmed {
    opacity: 0.3;
    pointer-events: none;
}

.tag-label {
  display: block;
  font-size: 10px;
  color: #AAA;
  margin-bottom: 8px;
  font-weight: 600;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  background: #F5F5F5;
  border: 1px solid #EEE;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.2s;
}

.entity-tag.clickable {
    cursor: pointer;
}

.entity-tag.clickable:hover {
    background: #E0E0E0;
    border-color: #CCC;
}

/* Ontology Detail Overlay */
.ontology-detail-overlay {
    position: absolute;
    top: 60px; /* Below header roughly */
    left: 20px;
    right: 20px;
    bottom: 20px;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(4px);
    z-index: 10;
    border: 1px solid #EAEAEA;
    box-shadow: 0 4px 20px rgba(0,0,0,0.05);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

.detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #EAEAEA;
    background: #FAFAFA;
}

.detail-title-group {
    display: flex;
    align-items: center;
    gap: 8px;
}

.detail-type-badge {
    font-size: 9px;
    font-weight: 700;
    color: #FFF;
    background: #000;
    padding: 2px 6px;
    border-radius: 2px;
    text-transform: uppercase;
}

.detail-name {
    font-size: 14px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

.close-btn {
    background: none;
    border: none;
    font-size: 18px;
    color: #999;
    cursor: pointer;
    line-height: 1;
}

.close-btn:hover {
    color: #333;
}

.detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
}

.detail-desc {
    font-size: 12px;
    color: #444;
    line-height: 1.5;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px dashed #EAEAEA;
}

.detail-section {
    margin-bottom: 16px;
}

.section-label {
    display: block;
    font-size: 10px;
    font-weight: 600;
    color: #AAA;
    margin-bottom: 8px;
}

.attr-list, .conn-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.attr-item {
    font-size: 11px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: baseline;
    padding: 4px;
    background: #F9F9F9;
    border-radius: 4px;
}

.attr-name {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    color: #000;
}

.attr-type {
    color: #999;
    font-size: 10px;
}

.attr-desc {
    color: #555;
    flex: 1;
    min-width: 150px;
}

.example-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.example-tag {
    font-size: 11px;
    background: #FFF;
    border: 1px solid #E0E0E0;
    padding: 3px 8px;
    border-radius: 12px;
    color: #555;
}

.conn-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    padding: 6px;
    background: #F5F5F5;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
}

.conn-node {
    font-weight: 600;
    color: #333;
}

.conn-arrow {
    color: #BBB;
}

/* Step 02 Stats */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

/* Step 03 Button */
.action-btn {
  width: 100%;
  background: #000;
  color: #FFF;
  border: none;
  padding: 14px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.action-btn:hover:not(:disabled) {
  opacity: 0.8;
}

.action-btn:disabled {
  background: #CCC;
  cursor: not-allowed;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #FF5722;
  margin-bottom: 12px;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid #FFCCBC;
  border-top-color: #FF5722;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* System Logs */
.system-logs {
  background: #000;
  color: #DDD;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid #222;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #333;
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: #888;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 80px; /* Approx 4 lines visible */
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar {
  width: 4px;
}

.log-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time {
  color: #666;
  min-width: 75px;
}

.log-msg {
  color: #CCC;
  word-break: break-all;
}
</style>
