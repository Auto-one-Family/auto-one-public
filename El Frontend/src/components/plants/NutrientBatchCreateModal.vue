<script setup lang="ts">
/**
 * NutrientBatchCreateModal — Bilanz-Ledger-Eintrag erfassen (AUT-1215)
 *
 * Ein Formular für alle entry_types inkl. system_incident (Anlagen-Vorfall).
 * Bedingte Felder je Typ; EC/pH „nicht gemessen“ explizit wählbar.
 * Pattern: PlantCreateModal.
 *
 * AUT-1358: EC Anzeige/Eingabe in µS/cm (FE-SSOT). Write via
 * `usCmToLedgerMsCm` (÷1000) — Ledger API/DB bleibt mS (U1-Adapter-Spiegel).
 */

import { computed, ref, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { useTankStore } from '@/shared/stores/tank.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'
import type {
  NutrientBatchAcquisitionMethod,
  NutrientBatchComponent,
  NutrientBatchEntryType,
  NutrientBatchQualifier,
} from '@/types'
import {
  NUTRIENT_BATCH_ACQUISITION_METHOD_LABELS,
  NUTRIENT_BATCH_ACQUISITION_METHODS,
  NUTRIENT_BATCH_ENTRY_TYPE_LABELS,
  NUTRIENT_BATCH_ENTRY_TYPES,
  NUTRIENT_BATCH_QUALIFIER_LABELS,
  NUTRIENT_BATCH_QUALIFIERS,
  showsComponents,
  showsMeasurements,
  showsRecipeLabel,
} from '@/components/plants/tankLabels'
import { usCmToLedgerMsCm } from '@/utils/ledgerEcUnits'

interface Props {
  open: boolean
  /** Pre-select entry type (e.g. system_incident for Vorfall-Kurzweg). */
  defaultEntryType?: NutrientBatchEntryType
  /** Pre-select tank after create. */
  initialTankId?: string
}

const props = withDefaults(defineProps<Props>(), {
  defaultEntryType: 'full_reset',
  initialTankId: '',
})

const emit = defineEmits<{
  close: []
  created: [batchId: string]
}>()

const tankStore = useTankStore()
const zoneStore = useZoneStore()
const toast = useToast()

type DoseUnit = 'ml_per_l' | 'g_per_l'
/** number-input v-model may be string or number at runtime. */
type NumberField = string | number

type ComponentDraft =
  | {
      kind: 'product'
      name: string
      dose: NumberField
      doseUnit: DoseUnit
      /** UI µS/cm — converted to ledger mS on submit. */
      ec_contribution_us_cm: NumberField
    }
  | {
      kind: 'salt'
      name: string
      conc_g_per_l: NumberField
      /** UI µS/cm — converted to ledger mS on submit. */
      ec_contribution_us_cm: NumberField
    }

interface FormState {
  zone_id: string
  tank_id: string
  entry_type: NutrientBatchEntryType
  volume_l: NumberField
  recipe_label: string
  occurred_at_local: string
  acquisition_method: NutrientBatchAcquisitionMethod
  qualifier: NutrientBatchQualifier
  ec_was_measured: boolean
  /** UI µS/cm — converted to ledger mS on submit. */
  ec_measured_after_us_cm: NumberField
  ph_was_measured: boolean
  ph_measured_after: NumberField
  components: ComponentDraft[]
}

function isBlankNumberField(raw: NumberField): boolean {
  return raw === ''
}

function parseRequiredNonNegative(
  raw: NumberField,
  label: string,
): number {
  const n = typeof raw === 'number' ? raw : parseLocaleNumber(String(raw))
  if (!Number.isFinite(n) || n < 0) {
    throw new Error(label)
  }
  return n
}

function parseOptionalNonNegative(
  raw: NumberField,
  label: string,
): number | undefined {
  if (isBlankNumberField(raw)) return undefined
  return parseRequiredNonNegative(raw, label)
}

function nowLocalInputValue(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function emptyProduct(): ComponentDraft {
  return {
    kind: 'product',
    name: '',
    dose: '',
    doseUnit: 'ml_per_l',
    ec_contribution_us_cm: '',
  }
}

function emptyForm(entryType: NutrientBatchEntryType, tankId = ''): FormState {
  return {
    zone_id: '',
    tank_id: tankId,
    entry_type: entryType,
    volume_l: entryType === 'remeasurement_only' ? '0' : '',
    recipe_label: '',
    occurred_at_local: nowLocalInputValue(),
    acquisition_method: 'manual_entry',
    qualifier: 'approximate',
    ec_was_measured: false,
    ec_measured_after_us_cm: '',
    ph_was_measured: false,
    ph_measured_after: '',
    components: showsComponents(entryType) ? [emptyProduct(), emptyProduct()] : [],
  }
}

const form = ref<FormState>(emptyForm(props.defaultEntryType))
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

const modalTitle = computed(() =>
  form.value.entry_type === 'system_incident'
    ? 'Anlagen-Vorfall protokollieren'
    : 'Bilanz-Eintrag erfassen',
)

const availableZones = computed(() => zoneStore.activeZones)

const tanksInZone = computed(() => {
  if (!form.value.zone_id) return tankStore.tanks
  return tankStore.tanksForZone(form.value.zone_id)
})

const showComponentEditor = computed(() => showsComponents(form.value.entry_type))
const showRecipe = computed(() => showsRecipeLabel(form.value.entry_type))
const showMeasureFields = computed(() => showsMeasurements(form.value.entry_type))

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    errorMessage.value = null
    form.value = emptyForm(props.defaultEntryType, props.initialTankId || '')
    if (props.initialTankId) {
      const known = tankStore.tanks.find((t) => t.id === props.initialTankId)
      if (known) form.value.zone_id = known.zone_id
    }
    if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
      void zoneStore.fetchZoneEntities()
    }
  },
)

watch(
  () => form.value.entry_type,
  (type, prev) => {
    if (type === prev) return
    if (type === 'remeasurement_only' && form.value.volume_l === '') {
      form.value.volume_l = '0'
    }
    if (showsComponents(type) && form.value.components.length === 0) {
      form.value.components = [emptyProduct()]
    }
    if (!showsComponents(type)) {
      form.value.components = []
    }
  },
)

watch(
  () => form.value.zone_id,
  () => {
    if (
      form.value.tank_id &&
      !tanksInZone.value.some((t) => t.id === form.value.tank_id)
    ) {
      form.value.tank_id = ''
    }
  },
)

function emptySalt(): ComponentDraft {
  return {
    kind: 'salt',
    name: '',
    conc_g_per_l: '',
    ec_contribution_us_cm: '',
  }
}

function addComponent(kind: 'product' | 'salt'): void {
  form.value.components.push(kind === 'product' ? emptyProduct() : emptySalt())
}

function setComponentKind(index: number, kind: 'product' | 'salt'): void {
  const prev = form.value.components[index]
  const name = prev?.name ?? ''
  form.value.components[index] =
    kind === 'product'
      ? { ...emptyProduct(), name }
      : { ...emptySalt(), name }
}

function removeComponent(index: number): void {
  form.value.components.splice(index, 1)
}

function buildComponents(): NutrientBatchComponent[] {
  const out: NutrientBatchComponent[] = []
  for (const c of form.value.components) {
    const name = c.name.trim()
    if (!name) continue
    if (c.kind === 'product') {
      const dose = parseRequiredNonNegative(
        c.dose,
        `Komponente „${name}": Dosis muss eine Zahl ≥ 0 sein.`,
      )
      const item: NutrientBatchComponent = {
        kind: 'product',
        name,
        ...(c.doseUnit === 'ml_per_l'
          ? { dose_ml_per_l: dose }
          : { dose_g_per_l: dose }),
      }
      const ecUs = parseOptionalNonNegative(
        c.ec_contribution_us_cm,
        `Komponente „${name}": EC-Beitrag ungültig.`,
      )
      if (ecUs !== undefined) item.ec_contribution_ms_cm = usCmToLedgerMsCm(ecUs)
      out.push(item)
    } else {
      const conc = parseRequiredNonNegative(
        c.conc_g_per_l,
        `Komponente „${name}": Konzentration muss ≥ 0 sein.`,
      )
      const item: NutrientBatchComponent = {
        kind: 'salt',
        name,
        conc_g_per_l: conc,
      }
      const ecUs = parseOptionalNonNegative(
        c.ec_contribution_us_cm,
        `Komponente „${name}": EC-Beitrag ungültig.`,
      )
      if (ecUs !== undefined) item.ec_contribution_ms_cm = usCmToLedgerMsCm(ecUs)
      out.push(item)
    }
  }
  return out
}

async function handleSubmit(): Promise<void> {
  if (isSubmitting.value) return
  errorMessage.value = null

  if (!form.value.tank_id) {
    errorMessage.value = 'Bitte einen Tank wählen (ggf. zuerst anlegen).'
    return
  }

  let volume: number
  try {
    volume = parseRequiredNonNegative(
      form.value.volume_l,
      'Volumen muss eine Zahl ≥ 0 sein.',
    )
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : 'Volumen ungültig'
    return
  }

  if (form.value.ec_was_measured) {
    const ec =
      typeof form.value.ec_measured_after_us_cm === 'number'
        ? form.value.ec_measured_after_us_cm
        : parseLocaleNumber(String(form.value.ec_measured_after_us_cm))
    if (!Number.isFinite(ec)) {
      errorMessage.value = 'EC-Messwert fehlt oder ist ungültig.'
      return
    }
  }
  if (form.value.ph_was_measured) {
    const ph =
      typeof form.value.ph_measured_after === 'number'
        ? form.value.ph_measured_after
        : parseLocaleNumber(String(form.value.ph_measured_after))
    if (!Number.isFinite(ph)) {
      errorMessage.value = 'pH-Messwert fehlt oder ist ungültig.'
      return
    }
  }

  let components: NutrientBatchComponent[] = []
  try {
    if (showComponentEditor.value) {
      components = buildComponents()
    }
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : 'Komponenten ungültig'
    return
  }

  const occurredAt = form.value.occurred_at_local
    ? new Date(form.value.occurred_at_local).toISOString()
    : undefined

  isSubmitting.value = true
  try {
    const batch = await tankStore.createBatch(form.value.tank_id, {
      entry_type: form.value.entry_type,
      volume_l: volume,
      components,
      acquisition_method: form.value.acquisition_method,
      qualifier: form.value.qualifier,
      occurred_at: occurredAt,
      recipe_label: form.value.recipe_label.trim() || null,
      ec_was_measured: form.value.ec_was_measured,
      // Ledger API expects mS/cm — convert from UI µS/cm (AUT-1358 / U1 adapter).
      ec_measured_after: form.value.ec_was_measured
        ? usCmToLedgerMsCm(
            typeof form.value.ec_measured_after_us_cm === 'number'
              ? form.value.ec_measured_after_us_cm
              : parseLocaleNumber(String(form.value.ec_measured_after_us_cm)),
          )
        : null,
      ph_was_measured: form.value.ph_was_measured,
      ph_measured_after: form.value.ph_was_measured
        ? typeof form.value.ph_measured_after === 'number'
          ? form.value.ph_measured_after
          : parseLocaleNumber(String(form.value.ph_measured_after))
        : null,
    })

    const warnings = batch.warnings?.filter(Boolean) ?? []
    if (warnings.length > 0) {
      toast.success(
        `${NUTRIENT_BATCH_ENTRY_TYPE_LABELS[batch.entry_type]} gespeichert (Hinweis: ${warnings[0]})`,
      )
    } else {
      toast.success(`${NUTRIENT_BATCH_ENTRY_TYPE_LABELS[batch.entry_type]} gespeichert`)
    }
    emit('created', batch.id)
    emit('close')
  } catch (e) {
    errorMessage.value =
      e instanceof Error ? e.message : 'Eintrag konnte nicht gespeichert werden'
  } finally {
    isSubmitting.value = false
  }
}

function handleClose(): void {
  if (!isSubmitting.value) emit('close')
}
</script>

<template>
  <BaseModal
    :open="props.open"
    :title="modalTitle"
    max-width="max-w-2xl"
    @close="handleClose"
  >
    <form class="batch-form" @submit.prevent="handleSubmit">
      <div class="batch-form__row">
        <label class="batch-form__field">
          <span class="batch-form__label">Zone (Filter)</span>
          <select v-model="form.zone_id" class="batch-form__input" aria-label="Zone filtern">
            <option value="">Alle bekannten Tanks</option>
            <option
              v-for="zone in availableZones"
              :key="zone.zone_id"
              :value="zone.zone_id"
            >
              {{ zone.name }}
            </option>
          </select>
        </label>

        <label class="batch-form__field">
          <span class="batch-form__label">Tank *</span>
          <select
            v-model="form.tank_id"
            class="batch-form__input"
            required
            aria-label="Tank"
          >
            <option value="" disabled>
              {{ tanksInZone.length === 0 ? 'Kein Tank bekannt — zuerst anlegen' : 'Tank wählen' }}
            </option>
            <option v-for="tank in tanksInZone" :key="tank.id" :value="tank.id">
              {{ tank.name }} ({{ tank.operation_mode }})
            </option>
          </select>
        </label>
      </div>

      <p v-if="tankStore.tanks.length === 0" class="batch-form__hint">
        Hinweis: Es gibt noch keinen Listen-Endpunkt für Tanks. Bekannte Tanks stammen aus
        dieser Browser-Sitzung (nach „Tank anlegen").
      </p>

      <label class="batch-form__field">
        <span class="batch-form__label">Eintragstyp *</span>
        <select
          v-model="form.entry_type"
          class="batch-form__input"
          required
          aria-label="Eintragstyp"
        >
          <option
            v-for="type in NUTRIENT_BATCH_ENTRY_TYPES"
            :key="type"
            :value="type"
          >
            {{ NUTRIENT_BATCH_ENTRY_TYPE_LABELS[type] }}
          </option>
        </select>
      </label>

      <div class="batch-form__row">
        <label class="batch-form__field">
          <span class="batch-form__label">Volumen (L) *</span>
          <input
            v-model="form.volume_l"
            type="number"
            min="0"
            step="any"
            class="batch-form__input"
            required
            aria-label="Volumen in Litern"
          />
        </label>

        <label class="batch-form__field">
          <span class="batch-form__label">Zeitpunkt</span>
          <input
            v-model="form.occurred_at_local"
            type="datetime-local"
            class="batch-form__input"
            aria-label="Zeitpunkt"
          />
        </label>
      </div>

      <label v-if="showRecipe" class="batch-form__field">
        <span class="batch-form__label">Rezeptur / Label</span>
        <input
          v-model="form.recipe_label"
          type="text"
          class="batch-form__input"
          maxlength="200"
          placeholder="z.B. Grow Woche 3"
          aria-label="Rezeptur-Label"
        />
      </label>

      <div class="batch-form__row">
        <label class="batch-form__field">
          <span class="batch-form__label">Erfassungsmethode *</span>
          <select
            v-model="form.acquisition_method"
            class="batch-form__input"
            required
            aria-label="Erfassungsmethode"
          >
            <option
              v-for="m in NUTRIENT_BATCH_ACQUISITION_METHODS"
              :key="m"
              :value="m"
            >
              {{ NUTRIENT_BATCH_ACQUISITION_METHOD_LABELS[m] }}
            </option>
          </select>
        </label>

        <label class="batch-form__field">
          <span class="batch-form__label">Genauigkeit *</span>
          <select
            v-model="form.qualifier"
            class="batch-form__input"
            required
            aria-label="Genauigkeits-Kennzeichnung"
          >
            <option
              v-for="q in NUTRIENT_BATCH_QUALIFIERS"
              :key="q"
              :value="q"
            >
              {{ NUTRIENT_BATCH_QUALIFIER_LABELS[q] }}
            </option>
          </select>
        </label>
      </div>

      <!-- Components: Fertigprodukt / Salz -->
      <fieldset v-if="showComponentEditor" class="batch-form__fieldset">
        <legend class="batch-form__label">Komponenten</legend>
        <div
          v-for="(comp, index) in form.components"
          :key="index"
          class="batch-form__component"
        >
          <div class="batch-form__row">
            <label class="batch-form__field">
              <span class="batch-form__label">Art</span>
              <select
                class="batch-form__input"
                :value="comp.kind"
                :aria-label="`Komponente ${index + 1} Art`"
                @change="
                  setComponentKind(
                    index,
                    ($event.target as HTMLSelectElement).value as 'product' | 'salt',
                  )
                "
              >
                <option value="product">Fertigprodukt</option>
                <option value="salt">Salz-Rezeptur</option>
              </select>
            </label>
            <label class="batch-form__field">
              <span class="batch-form__label">Name *</span>
              <input
                v-model="comp.name"
                type="text"
                class="batch-form__input"
                :aria-label="`Komponente ${index + 1} Name`"
              />
            </label>
          </div>

          <div v-if="comp.kind === 'product'" class="batch-form__row">
            <label class="batch-form__field">
              <span class="batch-form__label">Dosis *</span>
              <input
                v-model="comp.dose"
                type="number"
                min="0"
                step="any"
                class="batch-form__input"
                :aria-label="`Komponente ${index + 1} Dosis`"
              />
            </label>
            <label class="batch-form__field">
              <span class="batch-form__label">Einheit</span>
              <select
                v-model="comp.doseUnit"
                class="batch-form__input"
                :aria-label="`Komponente ${index + 1} Einheit`"
              >
                <option value="ml_per_l">ml/L</option>
                <option value="g_per_l">g/L</option>
              </select>
            </label>
          </div>

          <div v-else class="batch-form__row">
            <label class="batch-form__field">
              <span class="batch-form__label">Konzentration g/L *</span>
              <input
                v-model="comp.conc_g_per_l"
                type="number"
                min="0"
                step="any"
                class="batch-form__input"
                :aria-label="`Komponente ${index + 1} Konzentration`"
              />
            </label>
          </div>

          <div class="batch-form__row batch-form__row--end">
            <label class="batch-form__field">
              <span class="batch-form__label">EC-Beitrag (optional, µS/cm)</span>
              <input
                v-model="comp.ec_contribution_us_cm"
                type="text"
                inputmode="decimal"
                class="batch-form__input"
                placeholder="µS/cm"
                :aria-label="`Komponente ${index + 1} EC-Beitrag in µS/cm`"
              />
            </label>
            <button
              type="button"
              class="plant-btn plant-btn--ghost"
              :aria-label="`Komponente ${index + 1} entfernen`"
              @click="removeComponent(index)"
            >
              Entfernen
            </button>
          </div>
        </div>

        <div class="batch-form__comp-actions">
          <button
            type="button"
            class="plant-btn plant-btn--ghost"
            aria-label="Fertigprodukt hinzufügen"
            @click="addComponent('product')"
          >
            + Fertigprodukt
          </button>
          <button
            type="button"
            class="plant-btn plant-btn--ghost"
            aria-label="Salz hinzufügen"
            @click="addComponent('salt')"
          >
            + Salz
          </button>
        </div>
      </fieldset>

      <!-- EC / pH with explicit never-measured -->
      <fieldset v-if="showMeasureFields" class="batch-form__fieldset">
        <legend class="batch-form__label">Messwerte nach Eintrag</legend>

        <div class="batch-form__measure">
          <span class="batch-form__label">EC (µS/cm)</span>
          <div class="batch-form__radios" role="radiogroup" aria-label="EC gemessen?">
            <label class="batch-form__radio">
              <input v-model="form.ec_was_measured" type="radio" :value="false" />
              <span>nicht gemessen</span>
            </label>
            <label class="batch-form__radio">
              <input v-model="form.ec_was_measured" type="radio" :value="true" />
              <span>gemessen</span>
            </label>
          </div>
          <input
            v-if="form.ec_was_measured"
            v-model="form.ec_measured_after_us_cm"
            type="text"
            inputmode="decimal"
            class="batch-form__input"
            placeholder="µS/cm (0 erlaubt)"
            aria-label="EC-Messwert in µS/cm"
          />
        </div>

        <div class="batch-form__measure">
          <span class="batch-form__label">pH</span>
          <div class="batch-form__radios" role="radiogroup" aria-label="pH gemessen?">
            <label class="batch-form__radio">
              <input v-model="form.ph_was_measured" type="radio" :value="false" />
              <span>nicht gemessen</span>
            </label>
            <label class="batch-form__radio">
              <input v-model="form.ph_was_measured" type="radio" :value="true" />
              <span>gemessen</span>
            </label>
          </div>
          <input
            v-if="form.ph_was_measured"
            v-model="form.ph_measured_after"
            type="text"
            inputmode="decimal"
            class="batch-form__input"
            placeholder="z. B. 5,9"
            aria-label="pH-Messwert"
          />
        </div>
      </fieldset>

      <div v-if="errorMessage" class="batch-form__error" role="alert">
        {{ errorMessage }}
      </div>
    </form>

    <template #footer>
      <div class="batch-form__actions">
        <button
          type="button"
          class="plant-btn plant-btn--ghost"
          :disabled="isSubmitting"
          @click="handleClose"
        >
          Abbrechen
        </button>
        <button
          type="button"
          class="plant-btn plant-btn--primary"
          :disabled="isSubmitting || tanksInZone.length === 0"
          @click="handleSubmit"
        >
          {{ isSubmitting ? 'Wird gespeichert…' : 'Speichern' }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.batch-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-height: min(70vh, 720px);
  overflow: auto;
}

.batch-form__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.batch-form__row--end {
  align-items: end;
}

.batch-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.batch-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.batch-form__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  min-height: 38px;
}

.batch-form__input:focus {
  border-color: var(--color-accent);
}

.batch-form__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
}

.batch-form__fieldset {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
}

.batch-form__component {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-bottom: var(--space-3);
  border-bottom: 1px dashed var(--glass-border);
}

.batch-form__component:last-of-type {
  border-bottom: none;
  padding-bottom: 0;
}

.batch-form__comp-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.batch-form__measure {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.batch-form__radios {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.batch-form__radio {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  cursor: pointer;
}

.batch-form__error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  padding: var(--space-2) var(--space-3);
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  border-radius: var(--radius-sm);
}

.batch-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.plant-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
  min-height: 38px;
}

.plant-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.plant-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--color-text-primary);
}

.plant-btn--primary {
  background: var(--color-accent);
  color: var(--color-text-on-accent, #fff);
}

@media (max-width: 640px) {
  .batch-form__row {
    grid-template-columns: 1fr;
  }
}
</style>
