<script setup lang="ts">
/**
 * ZoneContextEditor — Form for zone-level business context.
 *
 * Manages plant info, growth phase, substrate, responsible person,
 * cycle archival, and custom fields per zone.
 */

import { ref, computed, onMounted, watch } from 'vue'
import {
  Save, Leaf, Calendar, Archive, ChevronDown, ChevronRight,
  Clock, Sprout,
} from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { useUiStore } from '@/shared/stores/ui.store'
import { inventoryApi } from '@/api/inventory'
import type { ZoneContextData, ZoneContextUpdate, CycleEntry } from '@/api/inventory'
import { AccordionSection } from '@/shared/design/primitives'

const props = defineProps<{
  zoneId: string
  zoneName?: string
}>()

const { success, error: showError } = useToast()
const uiStore = useUiStore()

// ── State ──
const isLoading = ref(true)
const isSaving = ref(false)
const isDirty = ref(false)
const contextExists = ref(false)

const form = ref<ZoneContextUpdate>({
  zone_name: undefined,
  plant_count: undefined,
  variety: undefined,
  substrate: undefined,
  growth_phase: undefined,
  planted_date: undefined,
  expected_harvest: undefined,
  responsible_person: undefined,
  work_hours_weekly: undefined,
  notes: undefined,
  custom_data: undefined,
})

const cycleHistory = ref<CycleEntry[]>([])
const plantAgeDays = ref<number | null>(null)
const daysToHarvest = ref<number | null>(null)
const showHistory = ref(false)

// ── Growth Phase Options ──
const GROWTH_PHASES = [
  { value: 'seedling', label: 'Sämling' },
  { value: 'clone', label: 'Steckling' },
  { value: 'vegetative', label: 'Vegetativ' },
  { value: 'pre_flower', label: 'Vorblüte' },
  { value: 'flower_week_1', label: 'Blüte Woche 1' },
  { value: 'flower_week_2', label: 'Blüte Woche 2' },
  { value: 'flower_week_3', label: 'Blüte Woche 3' },
  { value: 'flower_week_4', label: 'Blüte Woche 4' },
  { value: 'flower_week_5', label: 'Blüte Woche 5' },
  { value: 'flower_week_6', label: 'Blüte Woche 6' },
  { value: 'flower_week_7', label: 'Blüte Woche 7' },
  { value: 'flower_week_8', label: 'Blüte Woche 8' },
  { value: 'flower_week_9', label: 'Blüte Woche 9' },
  { value: 'flower_week_10', label: 'Blüte Woche 10' },
  { value: 'flush', label: 'Spülung' },
  { value: 'harvest', label: 'Ernte' },
  { value: 'drying', label: 'Trocknung' },
  { value: 'curing', label: 'Aushärtung' },
]

const phaseLabel = computed(() => {
  const phase = GROWTH_PHASES.find(p => p.value === form.value.growth_phase)
  return phase?.label ?? form.value.growth_phase ?? '—'
})

// ── Load Data ──
async function loadContext() {
  isLoading.value = true
  try {
    const data = await inventoryApi.getZoneContext(props.zoneId)
    applyData(data)
    contextExists.value = true
  } catch (e) {
    // 404 = no context yet, not an error
    contextExists.value = false
    form.value.zone_name = props.zoneName ?? undefined
  } finally {
    isLoading.value = false
    isDirty.value = false
  }
}

function applyData(data: ZoneContextData) {
  form.value = {
    zone_name: data.zone_name ?? undefined,
    plant_count: data.plant_count ?? undefined,
    variety: data.variety ?? undefined,
    substrate: data.substrate ?? undefined,
    growth_phase: data.growth_phase ?? undefined,
    planted_date: data.planted_date ?? undefined,
    expected_harvest: data.expected_harvest ?? undefined,
    responsible_person: data.responsible_person ?? undefined,
    work_hours_weekly: data.work_hours_weekly ?? undefined,
    notes: data.notes ?? undefined,
    custom_data: data.custom_data && Object.keys(data.custom_data).length > 0
      ? data.custom_data
      : undefined,
  }
  cycleHistory.value = data.cycle_history ?? []
  plantAgeDays.value = data.plant_age_days
  daysToHarvest.value = data.days_to_harvest
}

// ── Save ──
async function save() {
  isSaving.value = true
  try {
    const data = await inventoryApi.upsertZoneContext(props.zoneId, form.value)
    applyData(data)
    contextExists.value = true
    isDirty.value = false
    success('Zone-Kontext gespeichert')
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Fehler beim Speichern')
  } finally {
    isSaving.value = false
  }
}

// ── Archive Cycle ──
async function archiveCycle() {
  const confirmed = await uiStore.confirm({
    title: 'Zyklus abschließen',
    message: 'Der aktuelle Anbauzyklus wird archiviert und die Felder werden zurückgesetzt. Fortfahren?',
    confirmText: 'Archivieren',
    variant: 'danger',
  })
  if (!confirmed) return

  try {
    const result = await inventoryApi.archiveCycle(props.zoneId)
    success(`Zyklus #${result.cycle_number} archiviert`)
    await loadContext()
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Fehler beim Archivieren')
  }
}

function markDirty() {
  isDirty.value = true
}

// ── Lifecycle ──
onMounted(loadContext)

watch(() => props.zoneId, loadContext)
</script>

<template>
  <div class="zone-context">
    <!-- Loading -->
    <div v-if="isLoading" class="zone-context__loading">
      Lade Zone-Kontext...
    </div>

    <template v-else>
      <!-- KPI Bar -->
      <div v-if="contextExists && (plantAgeDays != null || daysToHarvest != null)" class="zone-context__kpis">
        <div v-if="plantAgeDays != null" class="zone-context__kpi">
          <Sprout class="w-4 h-4" />
          <span class="zone-context__kpi-value">{{ plantAgeDays }}</span>
          <span class="zone-context__kpi-label">Tage alt</span>
        </div>
        <div v-if="daysToHarvest != null" class="zone-context__kpi">
          <Calendar class="w-4 h-4" />
          <span class="zone-context__kpi-value" :class="{ 'zone-context__kpi-value--warn': daysToHarvest < 7 }">
            {{ daysToHarvest }}
          </span>
          <span class="zone-context__kpi-label">Tage bis Ernte</span>
        </div>
        <div v-if="form.growth_phase" class="zone-context__kpi">
          <Leaf class="w-4 h-4" />
          <span class="zone-context__kpi-value">{{ phaseLabel }}</span>
        </div>
      </div>

      <!-- Plant Info Section -->
      <AccordionSection title="Pflanzen & Anbau" storage-key="ao-zctx-plants" :default-open="true">
        <div class="zone-context__grid">
          <div class="zone-context__field">
            <label class="zone-context__label">Sorte / Varietät</label>
            <input
              v-model="form.variety"
              class="zone-context__input"
              type="text"
              placeholder="z.B. Wedding Cake"
              @input="markDirty"
            />
          </div>
          <div class="zone-context__field">
            <label class="zone-context__label">Anzahl Pflanzen</label>
            <input
              v-model.number="form.plant_count"
              class="zone-context__input"
              type="number"
              min="0"
              @input="markDirty"
            />
          </div>
          <div class="zone-context__field">
            <label class="zone-context__label">Substrat</label>
            <input
              v-model="form.substrate"
              class="zone-context__input"
              type="text"
              placeholder="z.B. Coco/Perlite 70/30"
              @input="markDirty"
            />
          </div>
          <div class="zone-context__field">
            <label class="zone-context__label">Wachstumsphase</label>
            <select
              v-model="form.growth_phase"
              class="zone-context__select"
              @change="markDirty"
            >
              <option value="">— Auswählen —</option>
              <option v-for="p in GROWTH_PHASES" :key="p.value" :value="p.value">
                {{ p.label }}
              </option>
            </select>
          </div>
          <div class="zone-context__field">
            <label class="zone-context__label">Pflanzedatum</label>
            <input
              v-model="form.planted_date"
              class="zone-context__input"
              type="date"
              @input="markDirty"
            />
          </div>
          <div class="zone-context__field">
            <label class="zone-context__label">Erwartete Ernte</label>
            <input
              v-model="form.expected_harvest"
              class="zone-context__input"
              type="date"
              @input="markDirty"
            />
          </div>
        </div>
      </AccordionSection>

      <!-- Operations Section -->
      <AccordionSection title="Betrieb" storage-key="ao-zctx-ops">
        <div class="zone-context__grid">
          <div class="zone-context__field">
            <label class="zone-context__label">Verantwortlicher</label>
            <input
              v-model="form.responsible_person"
              class="zone-context__input"
              type="text"
              placeholder="Name"
              @input="markDirty"
            />
          </div>
          <div class="zone-context__field">
            <label class="zone-context__label">Wochenstunden</label>
            <input
              v-model.number="form.work_hours_weekly"
              class="zone-context__input"
              type="number"
              min="0"
              step="0.5"
              @input="markDirty"
            />
          </div>
          <div class="zone-context__field zone-context__field--full">
            <label class="zone-context__label">Notizen</label>
            <textarea
              v-model="form.notes"
              class="zone-context__textarea"
              rows="3"
              placeholder="Freitext-Notizen zur Zone..."
              @input="markDirty"
            />
          </div>
        </div>
      </AccordionSection>

      <!-- Actions -->
      <div class="zone-context__actions">
        <button
          class="zone-context__save-btn"
          :disabled="!isDirty || isSaving"
          @click="save"
        >
          <Save class="w-4 h-4" />
          {{ isSaving ? 'Speichern...' : 'Speichern' }}
        </button>
        <button
          v-if="contextExists"
          class="zone-context__archive-btn"
          @click="archiveCycle"
        >
          <Archive class="w-4 h-4" />
          Zyklus abschließen
        </button>
      </div>

      <!-- Cycle History -->
      <div v-if="cycleHistory.length > 0" class="zone-context__history">
        <button class="zone-context__history-toggle" @click="showHistory = !showHistory">
          <component :is="showHistory ? ChevronDown : ChevronRight" class="w-4 h-4" />
          <Clock class="w-4 h-4" />
          <span>Anbau-Historik ({{ cycleHistory.length }} Zyklen)</span>
        </button>
        <div v-if="showHistory" class="zone-context__history-list">
          <div
            v-for="(cycle, idx) in [...cycleHistory].reverse()"
            :key="idx"
            class="zone-context__cycle"
          >
            <div class="zone-context__cycle-header">
              <span class="zone-context__cycle-number">#{{ cycleHistory.length - idx }}</span>
              <span class="zone-context__cycle-variety">{{ cycle.variety || 'Unbenannt' }}</span>
              <span v-if="cycle.plant_age_days" class="zone-context__cycle-age">
                {{ cycle.plant_age_days }} Tage
              </span>
            </div>
            <div class="zone-context__cycle-details">
              <span v-if="cycle.planted_date">{{ cycle.planted_date }}</span>
              <span v-if="cycle.substrate">{{ cycle.substrate }}</span>
              <span v-if="cycle.growth_phase">{{ cycle.growth_phase }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.zone-context {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.zone-context__loading {
  padding: var(--space-4);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* KPI Bar */
.zone-context__kpis {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
}

.zone-context__kpi {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.zone-context__kpi-value {
  font-weight: 600;
  color: var(--color-text-primary);
}

.zone-context__kpi-value--warn {
  color: var(--color-warning);
}

.zone-context__kpi-label {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

/* Form Grid */
.zone-context__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.zone-context__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.zone-context__field--full {
  grid-column: 1 / -1;
}

.zone-context__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.zone-context__input,
.zone-context__select,
.zone-context__textarea {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}

.zone-context__input:focus,
.zone-context__select:focus,
.zone-context__textarea:focus {
  border-color: var(--color-accent);
}

.zone-context__input::placeholder,
.zone-context__textarea::placeholder {
  color: var(--color-text-muted);
}

.zone-context__select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.zone-context__textarea {
  resize: vertical;
  min-height: 60px;
  font-family: inherit;
}

/* Actions */
.zone-context__actions {
  display: flex;
  gap: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border);
}

.zone-context__save-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.zone-context__save-btn:hover {
  opacity: 0.9;
}

.zone-context__save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.zone-context__archive-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-warning);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.zone-context__archive-btn:hover {
  border-color: var(--color-warning);
  background: rgba(251, 191, 36, 0.06);
}

/* Cycle History */
.zone-context__history {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.zone-context__history-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.zone-context__history-toggle:hover {
  color: var(--color-text-primary);
}

.zone-context__history-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-left: var(--space-4);
  border-left: 2px solid var(--glass-border);
}

.zone-context__cycle {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.zone-context__cycle-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.zone-context__cycle-number {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-iridescent-3);
}

.zone-context__cycle-variety {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.zone-context__cycle-age {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-left: auto;
}

.zone-context__cycle-details {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
