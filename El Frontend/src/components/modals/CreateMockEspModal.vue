<script setup lang="ts">
/**
 * CreateMockEspModal
 *
 * Reusable modal for creating Mock ESP devices.
 * Can be used from Dashboard, MockEspView, or any other view.
 *
 * Uses useEspStore().createDevice() for consistency with DevicesView.
 */

import { ref, watch } from 'vue'
import { useEspStore } from '@/stores/esp'
import type { MockESPCreate } from '@/types'
import { X, RefreshCw, Info } from 'lucide-vue-next'

interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: [espId: string]
}>()

const espStore = useEspStore()

const isCreating = ref(false)
const createError = ref<string | null>(null)
const newEsp = ref<MockESPCreate>({
  esp_id: '',
  zone_name: '',
  auto_heartbeat: true,
  heartbeat_interval_seconds: 15,
  sensors: [],
  actuators: [],
})

// Generate ESP ID - same format as DevicesView (MOCK_XXXXXXXX)
function generateEspId(): string {
  const chars = 'ABCDEF0123456789'
  let id = 'MOCK_'
  for (let i = 0; i < 8; i++) {
    id += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return id
}

function resetForm() {
  newEsp.value = {
    esp_id: generateEspId(),
    zone_name: '',
    auto_heartbeat: true,
    heartbeat_interval_seconds: 15,
    sensors: [],
    actuators: [],
  }
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      resetForm()
    }
  }
)

function close() {
  emit('update:modelValue', false)
}

async function createEsp() {
  if (isCreating.value) return

  isCreating.value = true
  createError.value = null

  try {
    // Build config - same structure as DevicesView
    const config: MockESPCreate = {
      esp_id: newEsp.value.esp_id,
      zone_name: newEsp.value.zone_name?.trim() || '',
      auto_heartbeat: newEsp.value.auto_heartbeat,
      heartbeat_interval_seconds: newEsp.value.heartbeat_interval_seconds,
      sensors: [],
      actuators: [],
    }

    // Use espStore.createDevice() - same as DevicesView
    await espStore.createDevice(config)
    emit('created', newEsp.value.esp_id)
    close()
  } catch (err: unknown) {
    // Display error to user
    const error = err as { message?: string }
    createError.value = error.message || 'Fehler beim Erstellen des Mock ESP'
  } finally {
    isCreating.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="modal-overlay"
      @click.self="close"
    >
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">Mock ESP erstellen</h3>
          <button class="modal-close" @click="close">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="modal-body space-y-4">
          <!-- Error Alert -->
          <div v-if="createError" class="error-alert">
            <span>{{ createError }}</span>
            <button @click="createError = null" class="error-close">&times;</button>
          </div>

          <!-- ESP ID -->
          <div>
            <label class="label">ESP ID</label>
            <div class="flex gap-2">
              <input
                v-model="newEsp.esp_id"
                class="input flex-1 font-mono"
                placeholder="MOCK_XXXXXXXX"
              />
              <button
                class="btn-secondary"
                @click="newEsp.esp_id = generateEspId()"
                title="Neue ID generieren"
              >
                <RefreshCw class="w-4 h-4" />
              </button>
            </div>
            <p class="text-xs mt-1" style="color: var(--color-text-muted)">
              Format: MOCK_XXXXXXXX
            </p>
          </div>

          <!-- Zone Name -->
          <div>
            <div class="mock-label-row">
              <label class="label">Zone-Name (optional)</label>
              <span class="mock-info-icon" title="Die Zone wird automatisch erstellt wenn sie noch nicht existiert">
                <Info class="mock-info-icon__svg" />
              </span>
            </div>
            <input
              v-model="newEsp.zone_name"
              class="input"
              placeholder="z.B. Zelt 1, Gewächshaus Nord"
            />
          </div>

          <!-- Auto-Heartbeat -->
          <div class="flex items-center gap-3">
            <input
              id="autoHeartbeat"
              v-model="newEsp.auto_heartbeat"
              type="checkbox"
              class="checkbox"
            />
            <label for="autoHeartbeat" style="color: var(--color-text-secondary)">
              Automatisch Lebenszeichen senden <span class="mock-recommended">(empfohlen)</span>
            </label>
          </div>

          <!-- Heartbeat Interval -->
          <div v-if="newEsp.auto_heartbeat">
            <label class="label">Heartbeat-Intervall (Sekunden)</label>
            <input
              v-model.number="newEsp.heartbeat_interval_seconds"
              type="number"
              min="5"
              max="300"
              class="input"
            />
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-secondary flex-1" @click="close" :disabled="isCreating">
            Abbrechen
          </button>
          <button
            class="mock-create-btn flex-1"
            @click="createEsp"
            :disabled="isCreating || !newEsp.esp_id"
          >
            <RefreshCw v-if="isCreating" class="w-4 h-4 animate-spin mr-2" />
            {{ isCreating ? 'Erstelle...' : 'Erstellen' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Error alert */
.error-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background-color: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 0.875rem;
}

.error-close {
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
  font-size: 1.25rem;
  line-height: 1;
  padding: 0;
  margin-left: 0.5rem;
}

.error-close:hover {
  opacity: 0.7;
}

/* Checkbox */
.checkbox {
  width: 1rem;
  height: 1rem;
  border-radius: var(--radius-xs);
  border: 1px solid var(--glass-border);
  background-color: var(--color-bg-tertiary);
  cursor: pointer;
}

.checkbox:checked {
  background-color: var(--color-iridescent-1);
  border-color: var(--color-iridescent-1);
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background-color: rgba(10, 10, 15, 0.8);
  backdrop-filter: blur(4px);
}

.modal-content {
  width: 100%;
  max-width: 28rem;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--glass-shadow);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.modal-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.modal-close {
  padding: 0.5rem;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  transition: all 0.2s;
  background: none;
  border: none;
  cursor: pointer;
}

.modal-close:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
}

.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}

/* ── Iridescent Create Button ── */
.mock-create-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-inverse);
  background: var(--gradient-iridescent);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  box-shadow: 0 0 24px rgba(167, 139, 250, 0.35);
  transition: filter var(--transition-fast), box-shadow var(--transition-fast);
}

.mock-create-btn:hover:not(:disabled) {
  filter: brightness(1.15);
  box-shadow: 0 0 32px rgba(167, 139, 250, 0.5);
}

.mock-create-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  filter: saturate(0.5);
}

/* ── Zone Label Row with Info Icon ── */
.mock-label-row {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.mock-info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: help;
  color: var(--color-text-muted);
  transition: color var(--transition-fast);
}

.mock-info-icon:hover {
  color: var(--color-accent-bright);
}

.mock-info-icon__svg {
  width: 14px;
  height: 14px;
}

/* ── Recommended tag ── */
.mock-recommended {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 400;
}
</style>
