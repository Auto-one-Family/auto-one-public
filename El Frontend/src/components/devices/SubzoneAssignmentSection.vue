<script setup lang="ts">
/**
 * SubzoneAssignmentSection — Heimat-Subzone (GPIO) + optionale n:m-Abdeckung
 *
 * Used in AddSensorModal, SensorConfigPanel and ActuatorConfigPanel.
 *
 * ## Doppelpfad-Vorrangregel (verbindlich)
 * 1. **Abdeckung (Ist/Soll):** ausschließlich Junction-API
 *    (`getSensorAssignments`/`assignSensor` bzw. `getActuatorAssignments`/`assignActuator`).
 *    Quelle der Wahrheit für „welche Subzonen deckt Komponente X ab“.
 * 2. **Heimat-Subzone (GPIO):** Select + Create → `assigned_gpios` /
 *    GPIO-first-match (Einzelfall, ESP-Config-Push). Unverändert kanonisch
 *    für eine Subzone pro GPIO; darf die Abdeckungs-Liste nicht speisen.
 *    Options: current-ESP API + zone siblings from espStore when `zoneId` set
 *    (fresh ESP in populated zone must still see Topf 1/2 etc.).
 * 3. `assigned_subzones` JSON bleibt tot — weder lesen noch schreiben.
 * 4. n:m aktiv mit `sensorConfigId` oder `actuatorConfigId`; sonst nur GPIO.
 */

import { ref, computed, onMounted, watch } from 'vue'
import { Check, X, Plus } from 'lucide-vue-next'
import { subzonesApi } from '@/api/subzones'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'
import { MESSAGE_LABELS, SUBZONE_ASSIGNMENT_LABELS } from '@/utils/labels'

interface SubzoneOption {
  id: string
  name: string
  /** AUT-1241: optional spatial Klarname (not used for sort). */
  positionLabel?: string | null
}

interface CoverageEntry {
  subzoneId: string
  name: string
}

interface Props {
  espId: string
  gpio: number
  modelValue: string | null
  /** When set, enables n:m coverage UI for sensors. */
  sensorConfigId?: string | null
  /** When set, enables n:m coverage UI for actuators (Verortung). */
  actuatorConfigId?: string | null
  zoneId?: string | null
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  sensorConfigId: null,
  actuatorConfigId: null,
  zoneId: null,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const labels = SUBZONE_ASSIGNMENT_LABELS
const toast = useToast()
const espStore = useEspStore()

const availableSubzones = ref<SubzoneOption[]>([])
const isLoading = ref(true)
const newSubzoneName = ref('')
/** AUT-1241: optional free-text spatial position on create */
const newSubzonePosition = ref('')
const createLoading = ref(false)

const CREATE_OPTION = '__create_new__'
/** Sentinel for "Keine Subzone" — avoids HTML select coercing null to string "null" */
const NONE_OPTION = '__none__'
const isCreating = ref(false)

/** Ist: loaded from junction API only */
const coverageIst = ref<CoverageEntry[]>([])
/** Soll: editable draft while in coverage edit mode */
const coverageSoll = ref<string[]>([])
const coverageLoading = ref(false)
const coverageSaving = ref(false)
const isEditingCoverage = ref(false)

const coverageKind = computed<'sensor' | 'actuator' | null>(() => {
  if (props.sensorConfigId && props.sensorConfigId.length > 0) return 'sensor'
  if (props.actuatorConfigId && props.actuatorConfigId.length > 0) return 'actuator'
  return null
})

const coverageConfigId = computed(() => {
  if (coverageKind.value === 'sensor') return props.sensorConfigId
  if (coverageKind.value === 'actuator') return props.actuatorConfigId
  return null
})

const coverageEnabled = computed(() => coverageKind.value != null)

const coverageHintText = computed(() => {
  if (coverageKind.value === 'actuator') return labels.coverageHintActuator
  if (coverageKind.value === 'sensor') return labels.coverageHintSensor
  return labels.coverageHint
})

const emptyCoverageText = computed(() => {
  if (coverageKind.value === 'actuator') return labels.emptyCoverageActuator
  if (coverageKind.value === 'sensor') return labels.emptyCoverageSensor
  return labels.emptyCoverage
})

function displayName(raw: string | null | undefined): string {
  const trimmed = raw?.trim()
  return trimmed ? trimmed : labels.unnamedPlace
}

/** Klarname: Name · Position (AUT-1241) — position never required. */
function klarname(sz: SubzoneOption): string {
  const pos = sz.positionLabel?.trim()
  return pos ? `${sz.name} · ${pos}` : sz.name
}

const selectedValue = computed({
  get: () => {
    if (isCreating.value) return CREATE_OPTION
    const v = props.modelValue
    return v == null || v === '' ? NONE_OPTION : v
  },
  set: (v) => {
    if (v === CREATE_OPTION) {
      isCreating.value = true
    } else {
      const emitted = v === NONE_OPTION || v == null || v === '' ? null : String(v)
      emit('update:modelValue', emitted)
      isCreating.value = false
    }
  },
})

const showCreateInput = computed(() => isCreating.value)

const selectOptions = computed(() => [
  { value: NONE_OPTION, label: labels.noneOption },
  ...availableSubzones.value.map((sz) => ({ value: sz.id, label: klarname(sz) })),
  { value: CREATE_OPTION, label: labels.createOption },
])

/** BUG-09 server fallback — prefer intentional Klarnamen from zone siblings. */
function isAutoSubzoneName(name: string | null | undefined): boolean {
  const trimmed = name?.trim() ?? ''
  return trimmed.length === 0 || /^Subzone \d+$/.test(trimmed)
}

/**
 * Load Heimat-Subzone options for the select.
 *
 * Root cause of empty dropdown on initial sensor config: subzones are
 * per-ESP in the API (`GET …/devices/{esp_id}/subzones`). A fresh ESP in a
 * populated zone therefore returned []. `zoneId` was already passed from
 * AddSensorModal but unused — merge zone siblings from espStore (same
 * pattern as PlantCreateModal.availableSubzones / AUT-1178).
 *
 * Merge rules:
 * - Zone siblings fill gaps (fresh ESP).
 * - Current-ESP API adds position_label.
 * - Prefer intentional Klarnamen over auto 'Subzone N' (sensor-create bug).
 */
async function loadSubzones() {
  isLoading.value = true
  try {
    const byId = new Map<string, SubzoneOption>()

    const zoneId = props.zoneId
    if (zoneId) {
      for (const device of espStore.devices) {
        if (device.zone_id !== zoneId) continue
        for (const sz of device.subzones ?? []) {
          const id = sz.subzone_id ?? ''
          if (!id) continue
          const next: SubzoneOption = {
            id,
            name: displayName(sz.subzone_name),
            positionLabel: null,
          }
          const prev = byId.get(id)
          if (!prev || (isAutoSubzoneName(prev.name) && !isAutoSubzoneName(next.name))) {
            byId.set(id, next)
          }
        }
      }
    }

    const result = await subzonesApi.getSubzones(props.espId)
    for (const sz of result.subzones ?? []) {
      const id = sz.subzone_id ?? ''
      if (!id) continue
      const apiName = displayName(sz.subzone_name)
      const prev = byId.get(id)
      const preferSiblingName =
        prev != null && isAutoSubzoneName(apiName) && !isAutoSubzoneName(prev.name)
      byId.set(id, {
        id,
        name: preferSiblingName ? prev.name : apiName,
        positionLabel: sz.position_label ?? null,
      })
    }

    availableSubzones.value = Array.from(byId.values()).sort((a, b) =>
      a.name.localeCompare(b.name, 'de'),
    )
  } catch {
    availableSubzones.value = []
  } finally {
    isLoading.value = false
  }
}

/**
 * Load coverage Ist exclusively from the n:m junction GET per subzone.
 * GPIO membership is intentionally ignored here (Vorrangregel §1).
 */
async function loadCoverage() {
  const configId = coverageConfigId.value
  const kind = coverageKind.value
  if (!coverageEnabled.value || !configId || !kind) {
    coverageIst.value = []
    return
  }
  coverageLoading.value = true
  try {
    const entries = await Promise.all(
      availableSubzones.value.map(async (sz) => {
        try {
          if (kind === 'sensor') {
            const res = await subzonesApi.getSensorAssignments(props.espId, sz.id)
            const hit = res.assignments.some((a) => a.sensor_config_id === configId)
            return hit
              ? ({ subzoneId: sz.id, name: klarname(sz) } satisfies CoverageEntry)
              : null
          }
          const res = await subzonesApi.getActuatorAssignments(props.espId, sz.id)
          const hit = res.assignments.some((a) => a.actuator_config_id === configId)
          return hit
            ? ({ subzoneId: sz.id, name: klarname(sz) } satisfies CoverageEntry)
            : null
        } catch {
          return null
        }
      }),
    )
    coverageIst.value = entries.filter((e): e is CoverageEntry => e != null)
  } catch {
    coverageIst.value = []
    toast.error(labels.coverageLoadError)
  } finally {
    coverageLoading.value = false
  }
}

async function refreshAll() {
  await loadSubzones()
  if (coverageEnabled.value) {
    await loadCoverage()
  }
}

function startEditCoverage() {
  coverageSoll.value = coverageIst.value.map((e) => e.subzoneId)
  isEditingCoverage.value = true
}

function cancelEditCoverage() {
  isEditingCoverage.value = false
  coverageSoll.value = []
}

function toggleSoll(subzoneId: string) {
  const set = new Set(coverageSoll.value)
  if (set.has(subzoneId)) {
    set.delete(subzoneId)
  } else {
    set.add(subzoneId)
  }
  coverageSoll.value = Array.from(set)
}

/**
 * Diff Soll vs Ist and call junction POST/DELETE. No GPIO side effects.
 */
async function applyCoverage() {
  const configId = coverageConfigId.value
  const kind = coverageKind.value
  if (!configId || !kind) return
  coverageSaving.value = true
  try {
    const ist = new Set(coverageIst.value.map((e) => e.subzoneId))
    const soll = new Set(coverageSoll.value)
    const toAdd = [...soll].filter((id) => !ist.has(id))
    const toRemove = [...ist].filter((id) => !soll.has(id))

    const assign =
      kind === 'sensor'
        ? (subzoneId: string) => subzonesApi.assignSensor(props.espId, subzoneId, configId)
        : (subzoneId: string) => subzonesApi.assignActuator(props.espId, subzoneId, configId)
    const remove =
      kind === 'sensor'
        ? (subzoneId: string) => subzonesApi.removeSensor(props.espId, subzoneId, configId)
        : (subzoneId: string) => subzonesApi.removeActuator(props.espId, subzoneId, configId)

    await Promise.all([
      ...toAdd.map((subzoneId) => assign(subzoneId)),
      ...toRemove.map((subzoneId) => remove(subzoneId)),
    ])

    await loadCoverage()
    isEditingCoverage.value = false
    coverageSoll.value = []
    toast.success(labels.coverageSaveSuccess)
  } catch {
    toast.error(labels.coverageSaveError)
  } finally {
    coverageSaving.value = false
  }
}

async function removeCoverageEntry(subzoneId: string) {
  const configId = coverageConfigId.value
  const kind = coverageKind.value
  if (!configId || !kind || props.disabled) return
  coverageSaving.value = true
  try {
    if (kind === 'sensor') {
      await subzonesApi.removeSensor(props.espId, subzoneId, configId)
    } else {
      await subzonesApi.removeActuator(props.espId, subzoneId, configId)
    }
    await loadCoverage()
    toast.success(labels.coverageRemoveSuccess)
  } catch {
    toast.error(labels.coverageSaveError)
  } finally {
    coverageSaving.value = false
  }
}

async function confirmCreateSubzone() {
  const name = newSubzoneName.value.trim()
  if (!name) return
  createLoading.value = true
  try {
    const device = espStore.devices.find((d) => espStore.getDeviceId(d) === props.espId)
    const zoneId = props.zoneId ?? device?.zone_id ?? null
    // Server accepts only letters, numbers, underscores (schemas/subzone.py)
    const subzoneId = name
      .toLowerCase()
      .replace(/\s+/g, '_')
      .replace(/-/g, '_')
      .replace(/[^a-z0-9_]/g, '_')
    const position = newSubzonePosition.value.trim()
    await subzonesApi.assignSubzone(props.espId, {
      subzone_id: subzoneId,
      subzone_name: name,
      parent_zone_id: zoneId ?? undefined,
      assigned_gpios: [props.gpio],
      ...(position ? { position_label: position } : {}),
    })
    await espStore.fetchAll()
    await refreshAll()
    emit('update:modelValue', subzoneId)
    isCreating.value = false
    newSubzoneName.value = ''
    newSubzonePosition.value = ''
    toast.success(`Subzone "${name}" erstellt und zugewiesen`)
  } catch {
    toast.error('Subzone konnte nicht erstellt werden')
  } finally {
    createLoading.value = false
  }
}

function cancelCreateSubzone() {
  isCreating.value = false
  newSubzoneName.value = ''
  newSubzonePosition.value = ''
}

watch(showCreateInput, (show) => {
  if (show) {
    isCreating.value = true
    newSubzoneName.value = ''
    newSubzonePosition.value = ''
  }
})

watch(
  () => [props.espId, props.zoneId] as const,
  () => {
    void refreshAll()
  },
)

watch(
  () => [props.sensorConfigId, props.actuatorConfigId] as const,
  () => {
    if (coverageEnabled.value) {
      void loadCoverage()
    } else {
      coverageIst.value = []
      isEditingCoverage.value = false
    }
  },
)

onMounted(() => {
  void refreshAll()
})
</script>

<template>
  <div class="subzone-assignment" data-testid="subzone-assignment-section">
    <!-- Path A: GPIO / Heimat (Einzelfall) -->
    <div class="subzone-assignment__gpio">
      <label class="subzone-assignment__label">{{ labels.gpioSection }}</label>
      <p class="subzone-assignment__hint">{{ labels.gpioHint }}</p>
      <div class="subzone-assignment__controls">
        <select
          v-model="selectedValue"
          class="subzone-assignment__select"
          :disabled="disabled || isLoading"
          :aria-label="labels.gpioSection"
          data-testid="subzone-gpio-select"
        >
          <option v-for="opt in selectOptions" :key="String(opt.value)" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <template v-if="showCreateInput">
          <div class="subzone-assignment__create-block">
            <div class="subzone-assignment__create-row">
              <input
                v-model="newSubzoneName"
                class="subzone-assignment__input"
                type="text"
                :placeholder="labels.createPlaceholder"
                :disabled="createLoading"
                :aria-label="labels.createPlaceholder"
                @keyup.enter="confirmCreateSubzone"
                @keyup.escape="cancelCreateSubzone"
              />
              <button
                type="button"
                class="subzone-assignment__btn subzone-assignment__btn--confirm"
                :disabled="!newSubzoneName.trim() || createLoading"
                :aria-label="labels.createOption"
                @click="confirmCreateSubzone"
              >
                <Check class="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                class="subzone-assignment__btn"
                :disabled="createLoading"
                :aria-label="labels.cancelEditAction"
                @click="cancelCreateSubzone"
              >
                <X class="w-3.5 h-3.5" />
              </button>
            </div>
            <label class="subzone-assignment__position">
              <span class="subzone-assignment__position-label">{{ labels.positionLabel }}</span>
              <input
                v-model="newSubzonePosition"
                class="subzone-assignment__input"
                type="text"
                :placeholder="labels.positionPlaceholder"
                :disabled="createLoading"
                :aria-label="labels.positionLabel"
                data-testid="subzone-position-input"
                @keyup.enter="confirmCreateSubzone"
                @keyup.escape="cancelCreateSubzone"
              />
            </label>
          </div>
        </template>
      </div>
    </div>

    <!-- Path B: n:m Abdeckung (sensorConfigId oder actuatorConfigId) -->
    <div
      v-if="coverageEnabled"
      class="subzone-assignment__coverage"
      data-testid="subzone-coverage"
    >
      <label class="subzone-assignment__label">{{ labels.coverageSection }}</label>
      <p class="subzone-assignment__hint">{{ coverageHintText }}</p>

      <div v-if="coverageLoading" class="subzone-assignment__muted">
        {{ MESSAGE_LABELS.loading }}
      </div>

      <!-- Ist (read-only list) — getrennt vom Soll-Editor -->
      <template v-else-if="!isEditingCoverage">
        <div class="subzone-assignment__ist-block" data-testid="subzone-coverage-ist">
          <span class="subzone-assignment__badge">{{ labels.coverageIst }}</span>
          <ul v-if="coverageIst.length > 0" class="subzone-assignment__chip-list">
            <li
              v-for="entry in coverageIst"
              :key="entry.subzoneId"
              class="subzone-assignment__chip"
            >
              <span>{{ entry.name }}</span>
              <button
                type="button"
                class="subzone-assignment__chip-remove"
                :disabled="disabled || coverageSaving"
                :aria-label="`${labels.removeCoverageAria}: ${entry.name}`"
                data-testid="subzone-coverage-remove"
                @click="removeCoverageEntry(entry.subzoneId)"
              >
                <X class="w-3 h-3" />
              </button>
            </li>
          </ul>
          <p v-else class="subzone-assignment__empty" data-testid="subzone-coverage-empty">
            {{ emptyCoverageText }}
            <button
              type="button"
              class="subzone-assignment__link-btn"
              :disabled="disabled"
              data-testid="subzone-coverage-assign"
              @click="startEditCoverage"
            >
              {{ labels.assignSubzoneAction }}
            </button>
          </p>
        </div>

        <button
          v-if="coverageIst.length > 0"
          type="button"
          class="subzone-assignment__primary"
          :disabled="disabled || coverageSaving"
          data-testid="subzone-coverage-edit"
          @click="startEditCoverage"
        >
          <Plus class="w-3.5 h-3.5" aria-hidden="true" />
          {{ labels.addCoverageAction }}
        </button>
      </template>

      <!-- Soll-Editor (editierbar in derselben Ansicht) -->
      <div v-else class="subzone-assignment__soll-block" data-testid="subzone-coverage-soll">
        <span class="subzone-assignment__badge">{{ labels.coverageSoll }}</span>
        <ul class="subzone-assignment__check-list">
          <li v-for="sz in availableSubzones" :key="sz.id">
            <label class="subzone-assignment__check">
              <input
                type="checkbox"
                :checked="coverageSoll.includes(sz.id)"
                :disabled="coverageSaving"
                @change="toggleSoll(sz.id)"
              />
              <span>{{ sz.name }}</span>
            </label>
          </li>
        </ul>
        <div class="subzone-assignment__soll-actions">
          <button
            type="button"
            class="subzone-assignment__primary"
            :disabled="coverageSaving"
            data-testid="subzone-coverage-apply"
            @click="applyCoverage"
          >
            {{ labels.applyCoverageAction }}
          </button>
          <button
            type="button"
            class="subzone-assignment__btn subzone-assignment__btn--text"
            :disabled="coverageSaving"
            @click="cancelEditCoverage"
          >
            {{ labels.cancelEditAction }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.subzone-assignment {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.subzone-assignment__gpio,
.subzone-assignment__coverage {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.subzone-assignment__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.subzone-assignment__hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.subzone-assignment__controls {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.subzone-assignment__select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
}

.subzone-assignment__select:focus {
  border-color: var(--color-accent);
}

.subzone-assignment__create-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
}

.subzone-assignment__create-row {
  display: flex;
  gap: var(--space-1);
  align-items: center;
}

.subzone-assignment__position {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 100%;
}

.subzone-assignment__position-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.subzone-assignment__input {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
}

.subzone-assignment__input:focus {
  border-color: var(--color-accent);
}

.subzone-assignment__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.subzone-assignment__btn:hover:not(:disabled) {
  border-color: var(--color-text-muted);
  color: var(--color-text-primary);
}

.subzone-assignment__btn--confirm:hover:not(:disabled) {
  border-color: var(--color-success);
  color: var(--color-success);
}

.subzone-assignment__btn--text {
  border: none;
  background: transparent;
  padding: var(--space-2) var(--space-3);
}

.subzone-assignment__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.subzone-assignment__ist-block,
.subzone-assignment__soll-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.subzone-assignment__badge {
  align-self: flex-start;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.subzone-assignment__chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  list-style: none;
  margin: 0;
  padding: 0;
}

.subzone-assignment__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.subzone-assignment__chip-remove {
  display: inline-flex;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}

.subzone-assignment__chip-remove:hover:not(:disabled) {
  color: var(--color-danger);
}

.subzone-assignment__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.subzone-assignment__link-btn {
  display: inline;
  padding: 0;
  border: none;
  background: none;
  color: var(--color-accent);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  text-decoration: underline;
}

.subzone-assignment__link-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.subzone-assignment__primary {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  align-self: flex-start;
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-inverse, #fff);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
}

.subzone-assignment__primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.subzone-assignment__check-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.subzone-assignment__check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  cursor: pointer;
}

.subzone-assignment__soll-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.subzone-assignment__muted {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}
</style>
