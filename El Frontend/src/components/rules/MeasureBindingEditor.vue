<script setup lang="ts">
/**
 * AUT-1397 [M-5]: Configure rule_metadata.measure_bindings[].
 * Pattern: RuleConfigPanel dose_config — emits update:rule-metadata only.
 * Never writes trigger_conditions.
 */

import { computed, ref, watch } from 'vue'
import { Activity, Plus, Trash2 } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { useSensorOptions } from '@/composables/useSensorOptions'
import {
  MEASURE_BINDING_FORMULA_OPTIONS,
  MEASURE_BINDING_HOOK_OPTIONS,
  UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE,
  type MeasureBinding,
  type MeasureBindingFormulaId,
  type MeasureBindingHook,
} from '@/types/measureBinding'
import {
  createEmptyBinding,
  createFreshWaterFlowBinding,
  getMeasureBindings,
  parseSensorOptionValue,
  sensorRefKey,
  setMeasureBindings,
} from '@/utils/measureBindings'
import { getSensorLabel } from '@/utils/sensorDefaults'

interface Props {
  ruleMetadata?: Record<string, unknown>
  /** Optional: Nachfüllpumpe for preset bracket (GPIO25 pattern). */
  refillPumpHint?: { espId: string; gpio: number; name?: string } | null
  /** AUT-1399: genau eine Bindung am Knoten — kein Listen-Add/Remove. */
  singleBinding?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  ruleMetadata: () => ({}),
  refillPumpHint: null,
  singleBinding: false,
})

const emit = defineEmits<{
  'update:rule-metadata': [metadata: Record<string, unknown>]
}>()

const espStore = useEspStore()
const { groupedSensorOptions } = useSensorOptions()

const bindings = computed(() => {
  const list = getMeasureBindings(props.ruleMetadata)
  if (props.singleBinding && list.length === 0) {
    return [createEmptyBinding()]
  }
  if (props.singleBinding) {
    return list.slice(0, 1)
  }
  return list
})

function commit(next: MeasureBinding[]): void {
  const payload = props.singleBinding ? next.slice(0, 1) : next
  emit('update:rule-metadata', setMeasureBindings(props.ruleMetadata, payload))
}

function addBinding(): void {
  commit([...bindings.value, createEmptyBinding()])
}

function removeBinding(idx: number): void {
  commit(bindings.value.filter((_, i) => i !== idx))
}

function updateBinding(idx: number, patch: Partial<MeasureBinding>): void {
  const next = bindings.value.map((b, i) => (i === idx ? { ...b, ...patch } : b))
  commit(next)
}

function setSensor(idx: number, optionValue: string): void {
  const current = bindings.value[idx]
  const second = current?.sensor_refs[1]
  const ref = parseSensorOptionValue(optionValue)
  if (!ref) {
    updateBinding(idx, { sensor_refs: second ? [second] : [] })
    return
  }
  updateBinding(idx, { sensor_refs: second ? [ref, second] : [ref] })
}

/** Optional second sensor → Canvas shows B−A Klarname (AUT-1399). */
function setSensorB(idx: number, optionValue: string): void {
  const current = bindings.value[idx]
  const first = current?.sensor_refs[0]
  const ref = parseSensorOptionValue(optionValue)
  if (!ref) {
    updateBinding(idx, { sensor_refs: first ? [first] : [] })
    return
  }
  if (!first) {
    updateBinding(idx, { sensor_refs: [ref] })
    return
  }
  updateBinding(idx, { sensor_refs: [first, ref] })
}

function toggleHook(idx: number, hook: MeasureBindingHook): void {
  const current = bindings.value[idx]
  if (!current) return
  const has = current.hooks.includes(hook)
  const hooks = has
    ? current.hooks.filter((h) => h !== hook)
    : [...current.hooks, hook]
  if (hooks.length === 0) return
  updateBinding(idx, { hooks })
}

function setFormula(idx: number, formulaId: string): void {
  if (formulaId !== 'difference' && formulaId !== 'delta_over_event') return
  updateBinding(idx, { formula_id: formulaId as MeasureBindingFormulaId })
}

function setOutputTarget(idx: number, target: string): void {
  if (target !== 'execution_metadata' && target !== 'ledger') return
  const current = bindings.value[idx]
  if (!current) return
  const formula_params = { ...current.formula_params }
  if (target === 'ledger') {
    formula_params.ui_target = UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE
  } else if (formula_params.ui_target === UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE) {
    delete formula_params.ui_target
  }
  updateBinding(idx, {
    output_target: target,
    formula_params,
  })
}

function applyFreshWaterPreset(idx: number): void {
  const current = bindings.value[idx]
  const sensor = current?.sensor_refs[0]
  if (!sensor) return
  const bracket = props.refillPumpHint
    ? { esp_id: props.refillPumpHint.espId, gpio: props.refillPumpHint.gpio }
    : undefined
  const preset = createFreshWaterFlowBinding(sensor, bracket)
  updateBinding(idx, preset)
}

function sensorSelectValue(binding: MeasureBinding, slot: 0 | 1 = 0): string {
  const ref = binding.sensor_refs[slot]
  return ref ? sensorRefKey(ref) : ''
}

function sensorDisplayName(binding: MeasureBinding, slot: 0 | 1 = 0): string {
  const ref = binding.sensor_refs[slot]
  if (!ref) return 'Kein Sensor'
  for (const device of espStore.devices) {
    const deviceId = espStore.getDeviceId(device)
    if (deviceId !== ref.esp_id) continue
    const sensors = (device.sensors as { gpio: number; sensor_type: string; name?: string | null }[]) || []
    const match = sensors.find(
      (s) => s.gpio === ref.gpio && s.sensor_type === ref.sensor_type,
    )
    if (match?.name?.trim()) return match.name.trim()
    const deviceName = device.name?.trim()
    if (deviceName) {
      return `${deviceName} · ${getSensorLabel(ref.sensor_type) || ref.sensor_type}`
    }
  }
  return getSensorLabel(ref.sensor_type) || ref.sensor_type
}

function isFreshWaterTarget(binding: MeasureBinding): boolean {
  return (
    binding.output_target === 'ledger' &&
    binding.formula_params?.ui_target === UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE
  )
}

/** Erweiterter Zwei-Sensor-Vergleich — standardmäßig zu (Ziegenbauer-Pfad = ein Sensor). */
const showTwoSensors = ref(false)

watch(
  bindings,
  (list) => {
    if (list.some((b) => b.sensor_refs.length >= 2)) {
      showTwoSensors.value = true
    }
  },
  { immediate: true, deep: true },
)

function onToggleTwoSensors(enabled: boolean): void {
  showTwoSensors.value = enabled
  if (!enabled) {
    bindings.value.forEach((b, idx) => {
      if (b.sensor_refs.length >= 2) {
        updateBinding(idx, { sensor_refs: b.sensor_refs.slice(0, 1) })
      }
    })
  }
}
</script>

<template>
  <section
    class="measure-binding-editor"
    aria-labelledby="measure-binding-heading"
    data-testid="measure-binding-editor"
  >
    <div class="measure-binding-editor__head">
      <h3 id="measure-binding-heading" class="measure-binding-editor__title">
        <Activity class="w-4 h-4 shrink-0" aria-hidden="true" />
        {{ singleBinding ? 'Mess-Bindung' : 'Mess-Bindung (optional)' }}
      </h3>
      <button
        v-if="!singleBinding"
        type="button"
        class="measure-binding-editor__add"
        aria-label="Mess-Bindung hinzufügen"
        data-testid="measure-binding-add"
        @click="addBinding"
      >
        <Plus class="w-3.5 h-3.5" aria-hidden="true" />
        Hinzufügen
      </button>
    </div>

    <p class="measure-binding-editor__hint">
      Misst zusätzlich mit, während die Regel läuft — entscheidet
      <strong>nicht</strong>, wann die Regel startet.
      Linien zu anderen Knoten brauchst du dafür
      <strong>nicht</strong>.
    </p>

    <div
      v-if="!singleBinding && bindings.length === 0"
      class="measure-binding-editor__empty"
      data-testid="measure-binding-empty"
    >
      Keine Mess-Bindung — Regel verhält sich wie bisher.
    </div>

    <article
      v-for="(binding, idx) in bindings"
      :key="idx"
      class="measure-binding-editor__card"
      :data-testid="`measure-binding-card-${idx}`"
    >
      <div class="measure-binding-editor__card-head">
        <span class="measure-binding-editor__card-label">
          {{ singleBinding ? 'Diese Messung' : `Messung ${idx + 1}` }}
          <span v-if="isFreshWaterTarget(binding)" class="measure-binding-editor__badge">
            → Frischwasser (L)
          </span>
        </span>
        <button
          v-if="!singleBinding"
          type="button"
          class="measure-binding-editor__remove"
          :aria-label="`Mess-Bindung ${idx + 1} entfernen`"
          @click="removeBinding(idx)"
        >
          <Trash2 class="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>

      <label class="measure-binding-editor__field">
        <span class="measure-binding-editor__label">Welcher Sensor?</span>
        <select
          class="measure-binding-editor__select"
          :value="sensorSelectValue(binding, 0)"
          :aria-label="`Sensor für Mess-Bindung ${idx + 1}`"
          data-testid="measure-binding-sensor"
          @change="setSensor(idx, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Sensor wählen…</option>
          <optgroup
            v-for="group in groupedSensorOptions"
            :key="group.zoneId ?? 'none'"
            :label="group.label"
          >
            <template v-for="sub in group.subgroups" :key="sub.subzoneId ?? 'root'">
              <option
                v-for="opt in sub.options"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </option>
            </template>
          </optgroup>
        </select>
        <span v-if="binding.sensor_refs[0]" class="measure-binding-editor__meta">
          Gewählt: {{ sensorDisplayName(binding, 0) }}
          <template v-if="!showTwoSensors">
            — derselbe Sensor wird am Anfang und am Ende gelesen
          </template>
        </span>
      </label>

      <fieldset class="measure-binding-editor__hooks">
        <legend class="measure-binding-editor__label">
          Wann wird gemessen?
        </legend>
        <p class="measure-binding-editor__meta measure-binding-editor__meta--block">
          Typisch für Nachfüllung: <strong>Erste Messung</strong> +
          <strong>Letzte Messung</strong> angehakt.
          Daraus kommt der Unterschied (z.&nbsp;B. wie viel Wasser geflossen ist).
        </p>
        <label
          v-for="hook in MEASURE_BINDING_HOOK_OPTIONS"
          :key="hook.id"
          class="measure-binding-editor__hook"
        >
          <input
            type="checkbox"
            :checked="binding.hooks.includes(hook.id)"
            :aria-label="hook.label"
            @change="toggleHook(idx, hook.id)"
          />
          <span>
            <strong>{{ hook.label }}</strong>
            <small>{{ hook.hint }}</small>
          </span>
        </label>
      </fieldset>

      <label class="measure-binding-editor__field">
        <span class="measure-binding-editor__label">Was wird berechnet?</span>
        <select
          class="measure-binding-editor__select"
          :value="binding.formula_id"
          :aria-label="`Formel für Mess-Bindung ${idx + 1}`"
          data-testid="measure-binding-formula"
          @change="setFormula(idx, ($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="opt in MEASURE_BINDING_FORMULA_OPTIONS"
            :key="opt.id"
            :value="opt.id"
          >
            {{ opt.label }}
          </option>
        </select>
      </label>

      <label class="measure-binding-editor__field">
        <span class="measure-binding-editor__label">Wohin mit dem Ergebnis?</span>
        <select
          class="measure-binding-editor__select"
          :value="binding.output_target"
          :aria-label="`Ziel für Mess-Bindung ${idx + 1}`"
          data-testid="measure-binding-output"
          @change="setOutputTarget(idx, ($event.target as HTMLSelectElement).value)"
        >
          <option value="execution_metadata">Nur im Protokoll merken</option>
          <option value="ledger">Als Frischwasser (L) im Salzrechner</option>
        </select>
      </label>

      <button
        v-if="binding.sensor_refs[0]"
        type="button"
        class="measure-binding-editor__preset"
        data-testid="measure-binding-freshwater-preset"
        aria-label="Preset Nachfüllung zu Frischwasser anwenden"
        @click="applyFreshWaterPreset(idx)"
      >
        Vorschlag: Nachfüllung → Frischwasser (L)
      </button>

      <!-- Zwei-Sensor-Vergleich bewusst versteckt — Normalfall ist ein Sensor -->
      <div v-if="singleBinding" class="measure-binding-editor__advanced">
        <label class="measure-binding-editor__hook">
          <input
            type="checkbox"
            :checked="showTwoSensors"
            data-testid="measure-binding-two-sensors"
            aria-label="Zwei verschiedene Sensoren vergleichen"
            @change="onToggleTwoSensors(($event.target as HTMLInputElement).checked)"
          />
          <span>
            <strong>Zwei verschiedene Sensoren vergleichen</strong>
            <small>
              Selten nötig. Normalfall: ein Sensor, zweimal gelesen (Anfang und Ende).
            </small>
          </span>
        </label>
        <label v-if="showTwoSensors" class="measure-binding-editor__field">
          <span class="measure-binding-editor__label">Zweiter Sensor (wird abgezogen)</span>
          <select
            class="measure-binding-editor__select"
            :value="sensorSelectValue(binding, 1)"
            :aria-label="`Zweiter Sensor für Mess-Bindung ${idx + 1}`"
            data-testid="measure-binding-sensor-b"
            @change="setSensorB(idx, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">Zweiten Sensor wählen…</option>
            <optgroup
              v-for="group in groupedSensorOptions"
              :key="`b-${group.zoneId ?? 'none'}`"
              :label="group.label"
            >
              <template v-for="sub in group.subgroups" :key="`b-${sub.subzoneId ?? 'root'}`">
                <option
                  v-for="opt in sub.options"
                  :key="`b-${opt.value}`"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </option>
              </template>
            </optgroup>
          </select>
          <span v-if="binding.sensor_refs[1]" class="measure-binding-editor__meta">
            Ergebnis: {{ sensorDisplayName(binding, 1) }} minus
            {{ sensorDisplayName(binding, 0) }}
          </span>
        </label>
      </div>
    </article>
  </section>
</template>

<style scoped>
.measure-binding-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-dark-700);
}

.measure-binding-editor__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.measure-binding-editor__title {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-dark-100);
}

.measure-binding-editor__hint,
.measure-binding-editor__meta,
.measure-binding-editor__empty {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-dark-400);
  line-height: 1.4;
}

.measure-binding-editor__meta--block {
  margin-bottom: var(--space-2);
}

.measure-binding-editor__advanced {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px dashed var(--color-dark-700);
}

.measure-binding-editor__add,
.measure-binding-editor__preset,
.measure-binding-editor__remove {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-dark-600);
  background: var(--color-dark-800);
  color: var(--color-dark-100);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-2);
  min-height: 36px;
}

.measure-binding-editor__preset {
  width: 100%;
  justify-content: center;
  color: var(--color-accent);
  border-color: color-mix(in srgb, var(--color-accent) 40%, transparent);
}

.measure-binding-editor__remove {
  min-width: 36px;
  justify-content: center;
  color: var(--color-danger);
}

.measure-binding-editor__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-dark-700);
  background: var(--color-dark-900);
}

.measure-binding-editor__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.measure-binding-editor__card-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-dark-200);
}

.measure-binding-editor__badge {
  margin-left: var(--space-2);
  color: var(--color-success);
  font-weight: 500;
}

.measure-binding-editor__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.measure-binding-editor__label {
  font-size: var(--text-xs);
  color: var(--color-dark-300);
}

.measure-binding-editor__select {
  width: 100%;
  min-height: 40px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-dark-600);
  background: var(--color-dark-800);
  color: var(--color-dark-50);
  font-size: var(--text-sm);
  padding: var(--space-2);
}

.measure-binding-editor__hooks {
  margin: 0;
  padding: 0;
  border: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.measure-binding-editor__hook {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-dark-200);
}

.measure-binding-editor__hook small {
  display: block;
  color: var(--color-dark-400);
}

.measure-binding-editor__hook input {
  margin-top: 2px;
}
</style>
