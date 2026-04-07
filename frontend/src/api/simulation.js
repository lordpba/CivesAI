import service, { requestWithRetry } from './index'

/**
 * Crea simulazione
 * @param {Object} data - { project_id, graph_id?, enable_twitter?, enable_reddit? }
 */
export const createSimulation = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/create', data), 3, 1000)
}

/**
 * Preparare l'ambiente di simulazione (attività asincrona）
 * @param {Object} data - { simulation_id, entity_types?, use_llm_for_profiles?, parallel_profile_count?, force_regenerate? }
 */
export const prepareSimulation = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/prepare', data), 3, 1000)
}

/**
 * Interrogare lo stato di avanzamento delle attività di preparazione
 * @param {Object} data - { task_id?, simulation_id? }
 */
export const getPrepareStatus = (data) => {
  return service.post('/api/simulation/prepare/status', data)
}

/**
 * Elenca le regioni NUTS-2 disponibili per la calibrazione
 */
export const getCalibrationRegions = () => {
  return service.get('/api/simulation/calibration/regions')
}

/**
 * Ottieni il profilo di calibrazione per una regione NUTS-2
 * @param {string} nuts2Code
 */
export const getCalibrationRegion = (nuts2Code) => {
  return service.get(`/api/simulation/calibration/${nuts2Code}`)
}

/**
 * Ottieni lo stato della simulazione
 * @param {string} simulationId
 */
export const getSimulation = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}`)
}

/**
 * ottenere simulato Agent Profiles
 * @param {string} simulationId
 * @param {string} platform - 'reddit' | 'twitter'
 */
export const getSimulationProfiles = (simulationId, platform = 'reddit') => {
  return service.get(`/api/simulation/${simulationId}/profiles`, { params: { platform } })
}

/**
 * Get generated in real time Agent Profiles
 * @param {string} simulationId
 * @param {string} platform - 'reddit' | 'twitter'
 */
export const getSimulationProfilesRealtime = (simulationId, platform = 'reddit') => {
  return service.get(`/api/simulation/${simulationId}/profiles/realtime`, { params: { platform } })
}

/**
 * Ottieni la configurazione della simulazione
 * @param {string} simulationId
 */
export const getSimulationConfig = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/config`)
}

/**
 * Ottieni la configurazione della simulazione in tempo reale durante la creazione
 * @param {string} simulationId
 * @returns {Promise} Restituisce informazioni di configurazione, inclusi metadati e contenuto di configurazione
 */
export const getSimulationConfigRealtime = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/config/realtime`)
}

/**
 * Elenca tutte le simulazioni
 * @param {string} projectId - Facoltativo, filtra per ID progetto
 */
export const listSimulations = (projectId) => {
  const params = projectId ? { project_id: projectId } : {}
  return service.get('/api/simulation/list', { params })
}

/**
 * Avvia la simulazione
 * @param {Object} data - { simulation_id, platform?, max_rounds?, enable_graph_memory_update? }
 */
export const startSimulation = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/start', data), 3, 1000)
}

/**
 * Interrompi la simulazione
 * @param {Object} data - { simulation_id }
 */
export const stopSimulation = (data) => {
  return service.post('/api/simulation/stop', data)
}

/**
 * Ottieni lo stato in tempo reale dell'esecuzione della simulazione
 * @param {string} simulationId
 */
export const getRunStatus = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/run-status`)
}

/**
 * Ottieni lo stato dettagliato dell'esecuzione della simulazione (comprese le azioni recenti）
 * @param {string} simulationId
 */
export const getRunStatusDetail = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/run-status/detail`)
}

/**
 * Ottieni post in simulazione
 * @param {string} simulationId
 * @param {string} platform - 'reddit' | 'twitter'
 * @param {number} limit - Quantità restituita
 * @param {number} offset - compensare
 */
export const getSimulationPosts = (simulationId, platform = 'reddit', limit = 50, offset = 0) => {
  return service.get(`/api/simulation/${simulationId}/posts`, {
    params: { platform, limit, offset }
  })
}

/**
 * Ottieni la sequenza temporale della simulazione (riepilogata per round）
 * @param {string} simulationId
 * @param {number} startRound - giro iniziale
 * @param {number} endRound - fine giro
 */
export const getSimulationTimeline = (simulationId, startRound = 0, endRound = null) => {
  const params = { start_round: startRound }
  if (endRound !== null) {
    params.end_round = endRound
  }
  return service.get(`/api/simulation/${simulationId}/timeline`, { params })
}

/**
 * Ottieni le statistiche dell'agente
 * @param {string} simulationId
 */
export const getAgentStats = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/agent-stats`)
}

/**
 * Ottieni la cronologia delle azioni di simulazione
 * @param {string} simulationId
 * @param {Object} params - { limit, offset, platform, agent_id, round_num }
 */
export const getSimulationActions = (simulationId, params = {}) => {
  return service.get(`/api/simulation/${simulationId}/actions`, { params })
}

/**
 * Chiudi l'ambiente di simulazione (esci con garbo）
 * @param {Object} data - { simulation_id, timeout? }
 */
export const closeSimulationEnv = (data) => {
  return service.post('/api/simulation/close-env', data)
}

/**
 * Ottieni lo stato dell'ambiente di simulazione
 * @param {Object} data - { simulation_id }
 */
export const getEnvStatus = (data) => {
  return service.post('/api/simulation/env-status', data)
}

/**
 * interviste batch Agent
 * @param {Object} data - { simulation_id, interviews: [{ agent_id, prompt }] }
 */
export const interviewAgents = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/interview/batch', data), 3, 1000)
}

/**
 * Ottieni un elenco di simulazioni storiche (con i dettagli del progetto)
 * Utilizzato per visualizzare elementi storici sulla home page
 * @param {number} limit - Limite quantità reso
 */
export const getSimulationHistory = (limit = 20) => {
  return service.get('/api/simulation/history', { params: { limit } })
}

/**
 * Elimina una simulazione storica
 * @param {string} simulationId
 */
export const deleteSimulation = (simulationId) => {
  return service.delete(`/api/simulation/${simulationId}`)
}

