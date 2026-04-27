<template>
  <div class="export-panel">
    <div class="export-header">
      <svg class="export-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
      <span class="export-title">Esporta Progetto Completo</span>
    </div>

    <!-- Status Check -->
    <div class="export-status" v-if="showStatus">
      <div class="status-item" :class="{ available: statusData.project_available }">
        <span class="status-icon" :class="statusData.project_available ? '✓' : '✗'"></span>
        <span class="status-label">Progetto</span>
      </div>
      <div class="status-item" :class="{ available: statusData.ontology_available }">
        <span class="status-icon" :class="statusData.ontology_available ? '✓' : '✗'"></span>
        <span class="status-label">Ontologia</span>
      </div>
      <div class="status-item" :class="{ available: statusData.simulation_available }">
        <span class="status-icon" :class="statusData.simulation_available ? '✓' : '✗'"></span>
        <span class="status-label">Simulazione</span>
      </div>
      <div class="status-item" :class="{ available: statusData.report_available }">
        <span class="status-icon" :class="statusData.report_available ? '✓' : '✗'"></span>
        <span class="status-label">Report</span>
      </div>
    </div>

    <!-- Export Buttons -->
    <div class="export-actions">
      <button 
        @click="exportProject" 
        :disabled="isExporting || !hasData"
        class="btn btn-export-primary"
        :class="{ loading: isExporting }"
      >
        <span v-if="!isExporting" class="btn-content">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          <span>Scarica ZIP Completo</span>
        </span>
        <span v-else class="btn-loading">
          <span class="spinner"></span>
          {{ exportProgress }}%
        </span>
      </button>

      <div class="info-note">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        <span>ZIP offline completo: progetto, ontologia, simulazione, report, prompts, reality seed</span>
      </div>
    </div>

    <!-- Success Message -->
    <div v-if="exportSuccess" class="export-success">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
      <span>Export completato! Il file è stato scaricato.</span>
    </div>

    <!-- Error Message -->
    <div v-if="exportError" class="export-error">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
      <span>{{ exportError }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({
  projectId: {
    type: String,
    required: true
  },
  simulationId: {
    type: String,
    default: null
  },
  reportId: {
    type: String,
    default: null
  }
})

const showStatus = ref(false)
const statusData = ref({
  project_available: false,
  ontology_available: false,
  simulation_available: false,
  report_available: false
})

const isExporting = ref(false)
const exportProgress = ref(0)
const exportSuccess = ref(false)
const exportError = ref('')

const API_BASE_URL = 'http://localhost:5000/api'

const hasData = computed(() => {
  return statusData.value.project_available || statusData.value.ontology_available
})

onMounted(async () => {
  await checkExportStatus()
})

const checkExportStatus = async () => {
  try {
    const response = await axios.post(`${API_BASE_URL}/export/status`, {
      project_id: props.projectId,
      simulation_id: props.simulationId,
      report_id: props.reportId
    })

    if (response.data.success) {
      statusData.value = response.data.data
      showStatus.value = true
    }
  } catch (error) {
    console.warn('Errore nel controllo dello stato di export:', error)
  }
}

const exportProject = async () => {
  if (isExporting.value) return

  isExporting.value = true
  exportSuccess.value = false
  exportError.value = ''
  exportProgress.value = 0

  try {
    const response = await axios.post(
      `${API_BASE_URL}/export/package`,
      {
        project_id: props.projectId,
        simulation_id: props.simulationId,
        report_id: props.reportId
      },
      {
        responseType: 'blob',
        onDownloadProgress: (progressEvent) => {
          if (progressEvent.total) {
            exportProgress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          }
        }
      }
    )

    // Crea un blob e scarica il file
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `CivesAI_Export_${props.projectId}.zip`)
    document.body.appendChild(link)
    link.click()
    link.parentNode.removeChild(link)
    window.URL.revokeObjectURL(url)

    exportSuccess.value = true
    setTimeout(() => {
      exportSuccess.value = false
    }, 5000)
  } catch (error) {
    console.error('Errore durante l\'export:', error)
    exportError.value = error.response?.data?.error || 'Errore durante l\'esportazione'
    setTimeout(() => {
      exportError.value = ''
    }, 5000)
  } finally {
    isExporting.value = false
    exportProgress.value = 0
  }
}
</script>

<style scoped>
.export-panel {
  background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  margin: 16px 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.export-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.export-icon {
  color: #4f46e5;
  flex-shrink: 0;
}

.export-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: 0.3px;
}

.export-status {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: #f3f4f6;
  border-radius: 6px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
  transition: all 0.2s ease;
}

.status-item.available {
  color: #10b981;
}

.status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: bold;
  background: currentColor;
  color: white;
}

.status-item.available .status-icon {
  background: #10b981;
}

.status-item:not(.available) .status-icon {
  background: #d1d5db;
  color: #9ca3af;
}

.export-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  letter-spacing: 0.3px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-export-primary {
  background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
}

.btn-export-primary:hover:not(:disabled) {
  box-shadow: 0 6px 16px rgba(79, 70, 229, 0.35);
  transform: translateY(-1px);
}

.btn-export-primary.loading {
  opacity: 0.8;
}

.btn-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-loading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.info-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 5px;
  font-size: 12px;
  color: #1e40af;
  line-height: 1.4;
}

.info-note svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.export-success {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 5px;
  font-size: 12px;
  color: #166534;
  font-weight: 500;
  animation: slideIn 0.3s ease;
}

.export-success svg {
  color: #10b981;
  flex-shrink: 0;
}

.export-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 5px;
  font-size: 12px;
  color: #7f1d1d;
  font-weight: 500;
  animation: slideIn 0.3s ease;
}

.export-error svg {
  color: #ef4444;
  flex-shrink: 0;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
