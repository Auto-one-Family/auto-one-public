<script setup lang="ts">
/**
 * RuntimeMaintenanceSection — Runtime Statistics & Maintenance Tracking (Phase 4A.8)
 *
 * Displays:
 * - Uptime (computed from last_restart)
 * - Expected lifetime hours
 * - Maintenance status + overdue indicator
 * - Maintenance log (append-only)
 *
 * Used inside SensorConfigPanel and ActuatorConfigPanel AccordionSections.
 */
import { ref, computed, onMounted } from 'vue'
import { Clock, Wrench, AlertTriangle, Plus } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { formatRelativeTime } from '@/utils/formatters'
import type { RuntimeStatsResponse, RuntimeStatsUpdate } from '@/api/sensors'

interface Props {
  entityId: string
  entityType: 'sensor' | 'actuator'
  fetchFn: (id: string) => Promise<RuntimeStatsResponse>
  updateFn: (id: string, stats: RuntimeStatsUpdate) => Promise<RuntimeStatsResponse>
}

const props = defineProps<Props>()
const { success, error } = useToast()

const isLoading = ref(false)
const stats = ref<Record<string, unknown>>({})
const computedUptime = ref<number | null>(null)
const maintenanceOverdue = ref(false)

// New maintenance entry form
const showAddEntry = ref(false)
const newAction = ref('')
const newNotes = ref('')

const maintenanceLog = computed(() => {
  const log = stats.value.maintenance_log as Array<Record<string, string>> | undefined
  return log || []
})

const uptimeDisplay = computed(() => {
  if (computedUptime.value == null) return '—'
  const hours = computedUptime.value
  if (hours < 1) return `${Math.round(hours * 60)} Min.`
  if (hours < 24) return `${hours.toFixed(1)} Std.`
  const days = Math.floor(hours / 24)
  const remaining = hours % 24
  return `${days}d ${remaining.toFixed(0)}h`
})

const lifetimeDisplay = computed(() => {
  const lifetime = stats.value.expected_lifetime_hours as number | undefined
  if (!lifetime) return '—'
  if (lifetime < 24) return `${lifetime} Std.`
  return `${Math.round(lifetime / 24)} Tage`
})

const lastRestart = computed(() => {
  const ts = stats.value.last_restart as string | undefined
  if (!ts) return null
  return new Date(ts)
})

const lastMaintenance = computed(() => {
  const ts = stats.value.last_maintenance as string | undefined
  if (!ts) return null
  return new Date(ts)
})

onMounted(async () => {
  await loadStats()
})

async function loadStats() {
  isLoading.value = true
  try {
    const response = await props.fetchFn(props.entityId)
    stats.value = response.runtime_stats || {}
    computedUptime.value = response.computed_uptime_hours ?? null
    maintenanceOverdue.value = response.maintenance_overdue ?? false
  } catch {
    stats.value = {}
  } finally {
    isLoading.value = false
  }
}

async function addMaintenanceEntry() {
  if (!newAction.value.trim()) return

  try {
    const entry = {
      date: new Date().toISOString(),
      action: newAction.value.trim(),
      notes: newNotes.value.trim() || undefined,
    }

    await props.updateFn(props.entityId, {
      last_maintenance: new Date().toISOString().split('T')[0],
      maintenance_log: [entry],
    })

    await loadStats()
    success('Wartungseintrag hinzugefügt')
    newAction.value = ''
    newNotes.value = ''
    showAddEntry.value = false
  } catch (e) {
    error(e instanceof Error ? e.message : 'Fehler beim Speichern')
  }
}
</script>

<template>
  <div class="runtime-section">
    <!-- Loading state -->
    <div v-if="isLoading" class="runtime-section__loading">
      Lade Laufzeitdaten...
    </div>

    <template v-else>
      <!-- Stats Grid -->
      <div class="runtime-section__grid">
        <div class="runtime-section__stat">
          <Clock class="w-4 h-4 text-iridescent-2" />
          <div class="runtime-section__stat-content">
            <span class="runtime-section__stat-label">Uptime</span>
            <span class="runtime-section__stat-value">{{ uptimeDisplay }}</span>
          </div>
        </div>

        <div class="runtime-section__stat">
          <Clock class="w-4 h-4 text-iridescent-3" />
          <div class="runtime-section__stat-content">
            <span class="runtime-section__stat-label">Erwartete Lebensdauer</span>
            <span class="runtime-section__stat-value">{{ lifetimeDisplay }}</span>
          </div>
        </div>

        <div v-if="lastRestart" class="runtime-section__stat">
          <Clock class="w-4 h-4 text-text-secondary" />
          <div class="runtime-section__stat-content">
            <span class="runtime-section__stat-label">Letzter Neustart</span>
            <span class="runtime-section__stat-value">
              {{ formatRelativeTime(lastRestart) }}
            </span>
          </div>
        </div>

        <div class="runtime-section__stat" :class="{ 'runtime-section__stat--overdue': maintenanceOverdue }">
          <component
            :is="maintenanceOverdue ? AlertTriangle : Wrench"
            class="w-4 h-4"
            :class="maintenanceOverdue ? 'text-warning' : 'text-success'"
          />
          <div class="runtime-section__stat-content">
            <span class="runtime-section__stat-label">Letzte Wartung</span>
            <span class="runtime-section__stat-value">
              {{ lastMaintenance ? formatRelativeTime(lastMaintenance) : '—' }}
              <span v-if="maintenanceOverdue" class="runtime-section__overdue-badge">
                Überfällig
              </span>
            </span>
          </div>
        </div>
      </div>

      <!-- Maintenance Log -->
      <div class="runtime-section__log">
        <div class="runtime-section__log-header">
          <h4 class="runtime-section__log-title">Wartungsprotokoll</h4>
          <button
            class="runtime-section__add-btn"
            @click="showAddEntry = !showAddEntry"
          >
            <Plus class="w-3.5 h-3.5" />
            Eintrag
          </button>
        </div>

        <!-- Add Entry Form -->
        <div v-if="showAddEntry" class="runtime-section__add-form">
          <input
            v-model="newAction"
            class="runtime-section__input"
            placeholder="Aktion (z.B. Sensor gereinigt)"
          />
          <input
            v-model="newNotes"
            class="runtime-section__input"
            placeholder="Notizen (optional)"
          />
          <button
            class="runtime-section__save-btn"
            :disabled="!newAction.trim()"
            @click="addMaintenanceEntry"
          >
            Speichern
          </button>
        </div>

        <!-- Log Entries -->
        <div v-if="maintenanceLog.length > 0" class="runtime-section__entries">
          <div
            v-for="(entry, idx) in maintenanceLog.slice().reverse()"
            :key="idx"
            class="runtime-section__entry"
          >
            <div class="runtime-section__entry-header">
              <Wrench class="w-3 h-3 text-text-muted" />
              <span class="runtime-section__entry-action">{{ entry.action }}</span>
              <span class="runtime-section__entry-date">
                {{ entry.date ? formatRelativeTime(new Date(entry.date)) : '' }}
              </span>
            </div>
            <p v-if="entry.notes" class="runtime-section__entry-notes">
              {{ entry.notes }}
            </p>
          </div>
        </div>
        <div v-else class="runtime-section__empty">
          Noch keine Wartungseinträge
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.runtime-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.runtime-section__loading {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: var(--space-4) 0;
  text-align: center;
}

/* Stats Grid */
.runtime-section__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.runtime-section__stat {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.runtime-section__stat--overdue {
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.runtime-section__stat-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.runtime-section__stat-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.runtime-section__stat-value {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.runtime-section__overdue-badge {
  font-size: var(--text-xs);
  color: var(--color-warning);
  font-weight: 600;
}

/* Maintenance Log */
.runtime-section__log {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.runtime-section__log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.runtime-section__log-title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

.runtime-section__add-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.runtime-section__add-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

/* Add Form */
.runtime-section__add-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.runtime-section__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-body);
}

.runtime-section__input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.runtime-section__save-btn {
  align-self: flex-end;
  padding: var(--space-1) var(--space-3);
  background: var(--color-accent);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
}

.runtime-section__save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Log Entries */
.runtime-section__entries {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 200px;
  overflow-y: auto;
}

.runtime-section__entry {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.runtime-section__entry-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.runtime-section__entry-action {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  font-weight: 500;
  flex: 1;
}

.runtime-section__entry-date {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.runtime-section__entry-notes {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin: var(--space-1) 0 0 calc(12px + var(--space-2));
}

.runtime-section__empty {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-3);
}
</style>
