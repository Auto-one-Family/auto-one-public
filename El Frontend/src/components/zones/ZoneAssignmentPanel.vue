<template>
  <div :class="['zone-panel', { 'zone-panel--compact': compact }]">
    <!-- Card wrapper for non-compact mode -->
    <Card v-if="!compact">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <MapPin class="w-5 h-5 text-dark-300" />
            <span class="font-medium">Zone</span>
          </div>
          <!-- Status Badge - show zone_name (human-readable) with zone_id as tooltip -->
          <Badge v-if="assignmentState === 'sending'" variant="warning" size="sm" pulse>
            <Loader2 class="w-3 h-3 animate-spin mr-1" />
            Sende...
          </Badge>
          <Badge v-else-if="assignmentState === 'pending_ack'" variant="info" size="sm" pulse>
            <Radio class="w-3 h-3 animate-pulse mr-1" />
            Warte auf ESP...
          </Badge>
          <Badge v-else-if="assignmentState === 'success'" variant="success" size="sm">
            <CheckCircle class="w-3 h-3 mr-1" />
            Erfolgreich
          </Badge>
          <Badge v-else-if="assignmentState === 'timeout'" variant="warning" size="sm">
            <AlertCircle class="w-3 h-3 mr-1" />
            Timeout
          </Badge>
          <Badge v-else-if="currentZoneName || currentZoneId" variant="success" size="sm" :title="currentZoneId ? `Zone-ID: ${currentZoneId}` : undefined">
            {{ currentZoneName || currentZoneId }}
          </Badge>
          <Badge v-else variant="gray" size="sm">
            Nicht zugewiesen
          </Badge>
        </div>
      </template>

      <!-- Error Message -->
      <div v-if="errorMessage" class="error-banner">
        <AlertCircle class="w-4 h-4 flex-shrink-0" />
        <span>{{ errorMessage }}</span>
        <button class="ml-auto" @click="errorMessage = ''">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Success Message -->
      <div v-if="successMessage" class="success-banner">
        <CheckCircle class="w-4 h-4 flex-shrink-0" />
        <span>{{ successMessage }}</span>
        <button class="ml-auto" @click="successMessage = ''">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Simple Zone Input -->
      <div class="space-y-3">
        <Input
          v-model="zoneInput"
          label="Zonenname"
          placeholder="z.B. Zelt 1, Gewächshaus, Outdoor"
          helper="Menschenfreundlicher Name. Die technische Zone-ID wird automatisch generiert."
          :disabled="saving"
        />

        <!-- Show generated zone_id preview -->
        <div v-if="zoneInput && generatedZoneId" class="text-xs" style="color: var(--color-text-muted)">
          Technische Zone-ID: <code class="font-mono bg-dark-800 px-1 rounded">{{ generatedZoneId }}</code>
        </div>

        <div class="flex gap-2">
          <Button
            v-if="(currentZoneName || currentZoneId) && zoneInput !== (currentZoneName || currentZoneId)"
            variant="secondary"
            size="sm"
            :disabled="saving"
            @click="zoneInput = currentZoneName || currentZoneId || ''"
          >
            Zurücksetzen
          </Button>

          <Button
            v-if="currentZoneId"
            variant="danger"
            size="sm"
            :loading="saving && isRemoving"
            :disabled="saving"
            @click="removeZone"
          >
            <X class="w-4 h-4 mr-1" />
            Entfernen
          </Button>

          <div class="flex-1"></div>

          <Button
            variant="primary"
            size="sm"
            :loading="saving && !isRemoving"
            :disabled="!zoneInput || !generatedZoneId || generatedZoneId === currentZoneId || saving"
            @click="saveZone"
          >
            <Check class="w-4 h-4 mr-1" />
            {{ currentZoneId ? 'Ändern' : 'Zuweisen' }}
          </Button>
        </div>
      </div>
    </Card>

    <!-- Compact mode content (no Card wrapper) -->
    <template v-else>
      <!-- Status Badge Row -->
      <div class="compact-status">
        <Badge v-if="assignmentState === 'sending'" variant="warning" size="sm" pulse>
          <Loader2 class="w-3 h-3 animate-spin mr-1" />
          Sende...
        </Badge>
        <Badge v-else-if="assignmentState === 'pending_ack'" variant="info" size="sm" pulse>
          <Radio class="w-3 h-3 animate-pulse mr-1" />
          Warte auf ESP...
        </Badge>
        <Badge v-else-if="assignmentState === 'success'" variant="success" size="sm">
          <CheckCircle class="w-3 h-3 mr-1" />
          Bestätigt
        </Badge>
        <Badge v-else-if="assignmentState === 'timeout'" variant="warning" size="sm">
          <AlertCircle class="w-3 h-3 mr-1" />
          Timeout
        </Badge>
      </div>

      <!-- Error Message -->
      <div v-if="errorMessage" class="error-banner error-banner--compact">
        <AlertCircle class="w-4 h-4 flex-shrink-0" />
        <span>{{ errorMessage }}</span>
        <button class="ml-auto" @click="errorMessage = ''">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Success Message -->
      <div v-if="successMessage" class="success-banner success-banner--compact">
        <CheckCircle class="w-4 h-4 flex-shrink-0" />
        <span>{{ successMessage }}</span>
        <button class="ml-auto" @click="successMessage = ''">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Zone Input -->
      <div class="compact-content">
        <Input
          v-model="zoneInput"
          label="Zonenname"
          placeholder="z.B. Zelt 1, Gewächshaus"
          :helper="zoneInput && generatedZoneId ? undefined : 'Name eingeben, Zone-ID wird automatisch generiert.'"
          :disabled="saving"
          size="sm"
        />

        <!-- Show generated zone_id preview -->
        <div v-if="zoneInput && generatedZoneId" class="zone-id-preview">
          Zone-ID: <code>{{ generatedZoneId }}</code>
        </div>

        <div class="compact-actions">
          <Button
            v-if="currentZoneId"
            variant="danger"
            size="sm"
            :loading="saving && isRemoving"
            :disabled="saving"
            @click="removeZone"
          >
            <X class="w-4 h-4" />
            Entfernen
          </Button>

          <Button
            variant="primary"
            size="sm"
            :loading="saving && !isRemoving"
            :disabled="!zoneInput || !generatedZoneId || generatedZoneId === currentZoneId || saving"
            @click="saveZone"
          >
            <Check class="w-4 h-4" />
            {{ currentZoneId ? 'Ändern' : 'Zuweisen' }}
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { MapPin, Check, X, AlertCircle, CheckCircle, Radio, Loader2 } from 'lucide-vue-next'
import { Card, Input, Button, Badge } from '@/shared/design'
import { zonesApi } from '@/api/zones'
import { useEspStore } from '@/stores/esp'
import { createLogger } from '@/utils/logger'

const log = createLogger('ZoneAssignment')

const espStore = useEspStore()

// Props
interface Props {
  espId: string
  currentZoneId?: string
  currentZoneName?: string
  currentMasterZoneId?: string
  isMock?: boolean  // Whether this is a Mock ESP (no server API call needed)
  compact?: boolean // Compact mode without Card wrapper (for embedding in popovers)
  subzoneStrategy?: 'transfer' | 'copy' | 'reset' // Strategy for subzone handling on zone switch
}

const props = withDefaults(defineProps<Props>(), {
  compact: false,
})

// Emits
const emit = defineEmits<{
  (e: 'zone-updated', zoneData: { zone_id: string; zone_name?: string; master_zone_id?: string }): void
  (e: 'zone-error', error: string): void
  (e: 'zone-before-save', zoneData: { zone_id: string; zone_name: string }): void
}>()

// =============================================================================
// State Machine for Zone Assignment
// =============================================================================

type ZoneAssignmentState = 'idle' | 'sending' | 'pending_ack' | 'success' | 'timeout' | 'error'

// State - use zone_name for display (human-readable), zone_id is technical
const zoneInput = ref(props.currentZoneName || props.currentZoneId || '')
const assignmentState = ref<ZoneAssignmentState>('idle')
const isRemoving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const ackTimeoutId = ref<ReturnType<typeof setTimeout> | null>(null)

// Computed states for compatibility with existing template
const saving = computed(() => assignmentState.value === 'sending' || assignmentState.value === 'pending_ack')

// Cleanup timeout on unmount
onUnmounted(() => {
  if (ackTimeoutId.value) {
    clearTimeout(ackTimeoutId.value)
  }
})

/**
 * Generate technical zone_id from human-readable zone_name
 * Mirrors server-side logic in debug.py and mock_esp_manager.py
 * "Zelt 1" -> "zelt_1", "Gewächshaus Nord" -> "gewaechshaus_nord"
 */
function generateZoneId(zoneName: string): string {
  if (!zoneName) return ''
  let zoneId = zoneName.toLowerCase()
  // Replace German umlauts
  zoneId = zoneId.replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
  // Replace spaces and special chars with underscores
  zoneId = zoneId.replace(/[^a-z0-9]+/g, '_')
  // Remove leading/trailing underscores
  zoneId = zoneId.replace(/^_+|_+$/g, '')
  return zoneId
}

// Computed zone_id from user input
const generatedZoneId = computed(() => generateZoneId(zoneInput.value))

// Watch for prop changes - prefer zone_name for input
watch([() => props.currentZoneName, () => props.currentZoneId], ([newName, newId]) => {
  if (!saving.value) {
    zoneInput.value = newName || newId || ''
  }
})

// Watch for zone confirmation via WebSocket (prop update during pending_ack)
// When the server broadcasts zone_assignment event, ESP Store updates device.zone_id
// which flows down as currentZoneId prop - detect this and transition to success
watch(() => props.currentZoneId, (newZoneId) => {
  if (assignmentState.value === 'pending_ack' && newZoneId === generatedZoneId.value) {
    // ESP confirmed zone assignment via WebSocket!
    log.debug('Zone confirmed via WebSocket', newZoneId)

    // Clear the timeout
    if (ackTimeoutId.value) {
      clearTimeout(ackTimeoutId.value)
      ackTimeoutId.value = null
    }

    // Transition to success
    assignmentState.value = 'success'
    successMessage.value = `Zone "${zoneInput.value}" vom ESP bestätigt`

    // Reset to idle after showing success
    setTimeout(() => {
      if (assignmentState.value === 'success') {
        assignmentState.value = 'idle'
        successMessage.value = ''
      }
    }, 3000)
  }
})

// Track whether we need to wait for strategy confirmation
const pendingSave = ref(false)

// Watch for subzoneStrategy changes — resume save when strategy is provided
watch(() => props.subzoneStrategy, (strategy) => {
  if (strategy && pendingSave.value) {
    pendingSave.value = false
    executeSaveZone()
  }
})

async function saveZone() {
  if (!zoneInput.value) return

  const zoneName = zoneInput.value
  const zoneId = generatedZoneId.value

  if (!zoneId) {
    errorMessage.value = 'Ungültiger Zonenname - bitte alphanumerische Zeichen verwenden'
    assignmentState.value = 'error'
    return
  }

  // If device already has a different zone and no strategy is set, ask parent for strategy
  const isZoneChange = props.currentZoneId && zoneId !== props.currentZoneId
  if (isZoneChange && !props.subzoneStrategy) {
    pendingSave.value = true
    emit('zone-before-save', { zone_id: zoneId, zone_name: zoneName })
    return
  }

  await executeSaveZone()
}

async function executeSaveZone() {
  const zoneName = zoneInput.value
  const zoneId = generatedZoneId.value

  if (!zoneId) return

  // Clear any existing timeout
  if (ackTimeoutId.value) {
    clearTimeout(ackTimeoutId.value)
  }

  assignmentState.value = 'sending'
  isRemoving.value = false
  errorMessage.value = ''
  successMessage.value = ''

  try {
    // Build request with generated zone_id and user-provided zone_name
    const request: { zone_id: string; zone_name?: string; master_zone_id?: string; subzone_strategy?: 'transfer' | 'copy' | 'reset' } = {
      zone_id: zoneId,        // Technical ID (lowercase, no spaces)
      zone_name: zoneName,     // Human-readable name
    }
    // Only add master_zone_id if it exists
    if (props.currentMasterZoneId) {
      request.master_zone_id = props.currentMasterZoneId
    }
    // Add subzone strategy if provided (zone switch scenario)
    if (props.subzoneStrategy) {
      request.subzone_strategy = props.subzoneStrategy
    }

    log.debug('Sending request', request)
    const response = await zonesApi.assignZone(props.espId, request)

    log.debug('API response', response)

    if (response.success) {
      // OPTIMISTIC UPDATE: Update ESP Store immediately for instant UI feedback
      // This ensures the Dashboard updates without waiting for WebSocket event
      espStore.updateDeviceZone(props.espId, {
        zone_id: zoneId,
        zone_name: zoneName,
        master_zone_id: props.currentMasterZoneId,
      })

      // For real ESPs with MQTT, show pending_ack briefly
      // Mock ESPs don't need ACK wait since server handles it immediately
      if (response.mqtt_sent && !props.isMock) {
        assignmentState.value = 'pending_ack'

        // Set timeout for ACK - show timeout after 30 seconds if no ESP confirmation
        ackTimeoutId.value = setTimeout(() => {
          if (assignmentState.value === 'pending_ack') {
            assignmentState.value = 'timeout'
            errorMessage.value = `ESP hat nicht innerhalb von 30 Sekunden bestätigt. Zone wurde in der Datenbank gespeichert, aber ESP-Bestätigung fehlt.`

            // Reset to idle after showing timeout
            setTimeout(() => {
              if (assignmentState.value === 'timeout') {
                assignmentState.value = 'idle'
                errorMessage.value = ''
              }
            }, 5000)
          }
        }, 30000)
      } else {
        // Immediate success for mocks or non-MQTT updates
        assignmentState.value = 'success'
        successMessage.value = response.mqtt_sent
          ? `Zone "${zoneName}" zugewiesen (MQTT gesendet)`
          : `Zone "${zoneName}" in Datenbank gespeichert`

        // Reset to idle after showing success
        setTimeout(() => {
          if (assignmentState.value === 'success') {
            assignmentState.value = 'idle'
            successMessage.value = ''
          }
        }, 3000)
      }

      emit('zone-updated', {
        zone_id: zoneId,
        zone_name: zoneName,
        master_zone_id: props.currentMasterZoneId
      })
    } else {
      assignmentState.value = 'error'
      errorMessage.value = response.message || 'Zone-Zuweisung fehlgeschlagen'
      emit('zone-error', errorMessage.value)

      // Reset to idle after showing error
      setTimeout(() => {
        if (assignmentState.value === 'error') {
          assignmentState.value = 'idle'
        }
      }, 5000)
    }
  } catch (error: unknown) {
    log.error('API error', error)
    const axiosError = error as { response?: { data?: { detail?: string } } }
    const message = axiosError.response?.data?.detail
      || (error instanceof Error ? error.message : 'Unbekannter Fehler')
    assignmentState.value = 'error'
    errorMessage.value = `Fehler: ${message}`
    emit('zone-error', errorMessage.value)

    // Reset to idle after showing error
    setTimeout(() => {
      if (assignmentState.value === 'error') {
        assignmentState.value = 'idle'
      }
    }, 5000)
  }
}

async function removeZone() {
  assignmentState.value = 'sending'
  isRemoving.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    // Call the Zone API to remove assignment
    const response = await zonesApi.removeZone(props.espId)

    log.debug('Remove response', response)

    if (response.success) {
      // OPTIMISTIC UPDATE: Update ESP Store immediately for instant UI feedback
      espStore.updateDeviceZone(props.espId, {
        zone_id: undefined,
        zone_name: undefined,
        master_zone_id: undefined,
      })

      // Server has removed the zone
      assignmentState.value = 'success'
      successMessage.value = 'Zone-Zuweisung entfernt'
      zoneInput.value = ''

      emit('zone-updated', {
        zone_id: '',
        zone_name: undefined,
        master_zone_id: undefined
      })

      // Reset to idle after showing success
      setTimeout(() => {
        if (assignmentState.value === 'success') {
          assignmentState.value = 'idle'
          successMessage.value = ''
        }
      }, 3000)
    } else {
      assignmentState.value = 'error'
      errorMessage.value = response.message || 'Zone-Entfernung fehlgeschlagen'
      emit('zone-error', errorMessage.value)

      // Reset to idle after showing error
      setTimeout(() => {
        if (assignmentState.value === 'error') {
          assignmentState.value = 'idle'
        }
      }, 5000)
    }
  } catch (error: unknown) {
    log.error('Remove error', error)
    const axiosError = error as { response?: { data?: { detail?: string } } }
    const message = axiosError.response?.data?.detail
      || (error instanceof Error ? error.message : 'Unbekannter Fehler')
    assignmentState.value = 'error'
    errorMessage.value = `Fehler: ${message}`
    emit('zone-error', errorMessage.value)

    // Reset to idle after showing error
    setTimeout(() => {
      if (assignmentState.value === 'error') {
        assignmentState.value = 'idle'
      }
    }, 5000)
  } finally {
    isRemoving.value = false
  }
}
</script>

<style scoped>
.zone-panel {
  margin-bottom: 16px;
}

.zone-panel--compact {
  margin-bottom: 0;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 0.875rem;
}

.error-banner--compact {
  padding: 0.5rem 0.625rem;
  font-size: 0.75rem;
}

.success-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
  background-color: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: var(--radius-md);
  color: var(--color-success);
  font-size: 0.875rem;
}

.success-banner--compact {
  padding: 0.5rem 0.625rem;
  font-size: 0.75rem;
}

/* Compact mode styles */
.compact-status {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0.75rem;
  min-height: 24px;
}

.compact-content {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.zone-id-preview {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.zone-id-preview code {
  font-family: 'JetBrains Mono', monospace;
  background-color: var(--color-bg-tertiary);
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-xs);
  font-size: 0.6875rem;
}

.compact-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
  margin-top: 0.25rem;
}
</style>














