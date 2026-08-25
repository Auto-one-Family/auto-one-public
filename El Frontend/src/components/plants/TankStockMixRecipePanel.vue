<script setup lang="ts">
/**
 * TankStockMixRecipePanel — Rezept-getriebener Ansetz-Rechner im Nährlösung-Tab
 * (AUT-1387 P-B, vorher AUT-1361 P9 in ActuatorConfigPanel).
 *
 * User tippt KEINE g/L — nur Wasser-ml + Phase; g/L aus stock_mix_recipes.
 * Schreibt NICHT concentration (Mess-Wizard = Wahrheit). Kein EC-Forecast.
 *
 * Extraction: identische Rechenlogik wie zuvor in ActuatorConfigPanel — nur die
 * Pumpen-Wahl kommt jetzt aus einer Tank-weiten Rollen-Erkennung statt aus dem
 * gerade geöffneten Aktor (Pattern: TankSaltCalculatorPanel.loadPumpConcentrations).
 */

import { computed, onMounted, ref, watch } from 'vue'
import { FlaskConical } from 'lucide-vue-next'
import { actuatorsApi } from '@/api/actuators'
import { stockMixRecipesApi, type StockMixRecipe } from '@/api/stockMixRecipes'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import { useEspStore } from '@/stores/esp'
import { useUiStore } from '@/shared/stores/ui.store'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import {
  buildStockResetConfirmMessage,
  canShowStockResetButton,
} from '@/components/plants/stockResetButton'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import BaseToggle from '@/shared/design/primitives/BaseToggle.vue'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import {
  gramsFromRecipe,
  diluteScaleFactor,
  effectiveGPerL,
  effectiveDoseMlPerL,
  resolveAbSplitWarning,
} from '@/components/esp/recipeMixerCalcs'
import { formatActuatorDoseLabel, formatDoseRoleLabel } from '@/utils/doseRoleDisplay'
import { RECIPE_PHASE_META } from '@/components/plan-timeline/recipeWeekGridDisplay'
import type { DoseRole } from '@/types'
import { createLogger } from '@/utils/logger'

const logger = createLogger('TankStockMixRecipePanel')

interface Props {
  tankId: string
  tankName?: string
}

const props = withDefaults(defineProps<Props>(), {
  tankName: '',
})

const emit = defineEmits<{
  /** After recipe g/L values were saved (server SSOT changed). */
  changed: []
}>()

const espStore = useEspStore()
const uiStore = useUiStore()
const toast = useToast()
const stockResetSaving = ref(false)

/** F3-Buckets → kanonische NUTRIENT_PHASES-Keys (Verify-Plan AUT-1361). */
function phaseOptionLabel(phaseKey: keyof typeof RECIPE_PHASE_META): string {
  const meta = RECIPE_PHASE_META[phaseKey]
  return meta.oxidLabel
    ? `${meta.name} · vorgeschlagenes NPK: ${meta.oxidLabel}`
    : meta.name
}

const STOCK_MIX_PHASE_OPTIONS = [
  { value: 'veg-frueh', label: phaseOptionLabel('veg-frueh') },
  { value: 'uebergang-vorbluete', label: phaseOptionLabel('uebergang-vorbluete') },
  { value: 'bluete-stretch', label: phaseOptionLabel('bluete-stretch') },
] as const

const DOSE_ROLES: DoseRole[] = ['part_a', 'part_b', 'ph_down']

interface DiscoveredPump {
  espId: string
  gpio: number
  name: string
  actuatorType: string
  doseRole: DoseRole
}

const isLoadingPumps = ref(false)
const discoveredPumps = ref<DiscoveredPump[]>([])
const selectedRole = ref<DoseRole | null>(null)

const recipeVesselMl = ref<number | null>(1000)
/** BaseInput requires string|number — bridges the null-able internal ref. */
const recipeVesselMlInput = computed<number | string>({
  get: () => recipeVesselMl.value ?? '',
  set: (v) => {
    const n = Number(v)
    recipeVesselMl.value = v !== '' && Number.isFinite(n) ? n : null
  },
})
const recipeNutrientPhase = ref<string>('uebergang-vorbluete')
const recipeLoaded = ref<StockMixRecipe | null>(null)
const recipeLoadError = ref<string | null>(null)
const recipeLoading = ref(false)
/** AUT-1362: optional milder ansetzen — Gramm/Dosis automatisch, kein Faktor sichtbar. */
const recipeDiluteSafer = ref(false)
const recipeEditOpen = ref(false)
const recipeEditDraft = ref<{ name: string; target_g_per_l: number | string }[]>([])
const recipeEditSaving = ref(false)

const roleOptions = computed(() => {
  const seen = new Set<string>()
  const opts: { value: string; label: string }[] = []
  for (const pump of discoveredPumps.value) {
    if (seen.has(pump.doseRole)) continue
    seen.add(pump.doseRole)
    opts.push({
      value: pump.doseRole,
      label: formatActuatorDoseLabel({
        name: pump.name,
        actuatorType: pump.actuatorType,
        doseRole: pump.doseRole,
        typeFallback: 'Pumpe',
      }),
    })
  }
  return opts
})

const selectedPump = computed(
  () => discoveredPumps.value.find((p) => p.doseRole === selectedRole.value) ?? null,
)

/** AUT-1414: only Stock A/B with pump + loaded recipe — never ph_down. */
const showStockResetButton = computed(() =>
  canShowStockResetButton({
    doseRole: selectedRole.value,
    hasPump: selectedPump.value != null,
    recipeId: recipeLoaded.value?.id,
  }),
)

const actuatorDoseLabel = computed(() => {
  const pump = selectedPump.value
  if (!pump) return '—'
  return formatActuatorDoseLabel({
    name: pump.name,
    actuatorType: pump.actuatorType,
    doseRole: pump.doseRole,
    typeFallback: 'Pumpe',
  })
})

const recipeStockTitle = computed(() => `Stock für ${actuatorDoseLabel.value} ansetzen`)

/** Internal dilute scale from recipe metadata (never shown as 250×/200×). */
const recipeDiluteScale = computed((): number | null => {
  if (!recipeDiluteSafer.value) return null
  const meta = recipeLoaded.value?.metadata
  if (!meta || typeof meta !== 'object') return null
  const watch = meta.solubility_watch
  if (!watch || typeof watch !== 'object') return null
  const watchObj = watch as Record<string, unknown>
  const base = typeof meta.concentration_factor === 'number' ? meta.concentration_factor : null
  const fallback =
    typeof watchObj.fallback_factor === 'number' ? watchObj.fallback_factor : null
  return diluteScaleFactor(base, fallback)
})

const recipeCanDiluteSafer = computed(() => {
  const recipe = recipeLoaded.value
  if (!recipe || recipe.dose_role !== 'part_b') return false
  const watch = recipe.metadata?.solubility_watch
  if (!watch || typeof watch !== 'object') return false
  const watchObj = watch as Record<string, unknown>
  return (
    typeof recipe.metadata.concentration_factor === 'number' &&
    typeof watchObj.fallback_factor === 'number'
  )
})

/**
 * Gramm-Vorschau (blaues Feld). Während g/L-Edit live aus Draft, sonst aus gespeichertem Rezept.
 */
const recipeGrams = computed(() => {
  const recipe = recipeLoaded.value
  const vessel = recipeVesselMl.value
  if (!recipe || vessel == null) return []
  const scale = recipeDiluteScale.value
  const components =
    recipeEditOpen.value && recipeEditDraft.value.length > 0
      ? recipeEditDraft.value
      : recipe.components
  return components.map((row) => {
    const rawGPerL = Number(row.target_g_per_l)
    const gPerL = effectiveGPerL(rawGPerL, scale)
    return {
      name: row.name,
      targetGPerL: Number.isFinite(rawGPerL) ? rawGPerL : row.target_g_per_l,
      grams: gPerL == null ? null : gramsFromRecipe(gPerL, vessel),
    }
  })
})

/** Summe aller berechneten Gramm-Zeilen (nur gültige Werte). */
const recipeGramsTotal = computed(() => {
  const vals = recipeGrams.value
    .map((r) => r.grams)
    .filter((g): g is number => g != null && Number.isFinite(g))
  if (vals.length === 0) return null
  return vals.reduce((a, b) => a + b, 0)
})

/**
 * AUT-1369: display-only recipe volume intent (metadata.dose_ml_per_l).
 * Not the runtime dose — that uses volume_share × concentration (server).
 * Auto-adjusted when dilute toggle on; no factor text.
 */
const recipeDoseMlPerL = computed((): number | null => {
  const recipe = recipeLoaded.value
  const role = selectedRole.value
  if (!recipe || !role) return null
  const doseMap = recipe.metadata?.dose_ml_per_l
  if (!doseMap || typeof doseMap !== 'object') return null
  const raw = (doseMap as Record<string, unknown>)[role]
  const base = typeof raw === 'number' ? raw : null
  return effectiveDoseMlPerL(base, recipeDiluteScale.value)
})

const recipePhaseLabel = computed(() => {
  const hit = STOCK_MIX_PHASE_OPTIONS.find((o) => o.value === recipeNutrientPhase.value)
  return hit?.label ?? recipeNutrientPhase.value
})

const recipeRoleLabel = computed(
  () => formatDoseRoleLabel(selectedRole.value) ?? '— Rolle nicht gesetzt —',
)

/** Deutsche Anzeige: 1,5 g (kein Logik-Change — nur Format). */
function formatGramsDe(grams: number): string {
  return grams.toLocaleString('de-DE', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 2,
  })
}

function formatMlDe(ml: number): string {
  return ml.toLocaleString('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })
}

/**
 * Tank-weite Pumpen-Erkennung nach Rezept-Rolle (part_a | part_b | ph_down).
 * Pattern mirrors ActuatorConfigPanel.scalePartnerConcentration / TankSaltCalculatorPanel
 * .loadPumpConcentrations (actuatorsApi.get pro Aktor am Tank).
 */
async function discoverPumps(): Promise<void> {
  discoveredPumps.value = []
  if (!props.tankId) return
  if (espStore.devices.length === 0) {
    await espStore.fetchAll()
  }
  isLoadingPumps.value = true
  try {
    const devices = espStore.devices.filter(
      (d) => (d as { tank_id?: string | null }).tank_id === props.tankId,
    )
    const found: DiscoveredPump[] = []
    for (const device of devices) {
      const espId = espStore.getDeviceId(device)
      if (!espId) continue
      const actuators = (device.actuators as { gpio: number }[] | undefined) ?? []
      for (const act of actuators) {
        if (typeof act.gpio !== 'number') continue
        try {
          const cfg = await actuatorsApi.get(espId, act.gpio)
          const role = (cfg.dose_role ?? '').trim().toLowerCase()
          if (!DOSE_ROLES.includes(role as DoseRole)) continue
          found.push({
            espId,
            gpio: act.gpio,
            name: cfg.name,
            actuatorType: cfg.actuator_type,
            doseRole: role as DoseRole,
          })
        } catch {
          // try next actuator — same fail-soft as partner-scale path
        }
      }
    }
    discoveredPumps.value = found
  } finally {
    isLoadingPumps.value = false
  }
}

async function loadStockMixRecipe(): Promise<void> {
  recipeLoadError.value = null
  recipeLoaded.value = null
  recipeDiluteSafer.value = false
  recipeEditOpen.value = false
  const role = selectedRole.value
  if (!role) {
    recipeLoadError.value =
      discoveredPumps.value.length === 0
        ? null
        : 'Rezept-Rolle wählen, um ein Stammlösungs-Rezept zu laden.'
    return
  }
  recipeLoading.value = true
  try {
    recipeLoaded.value = await stockMixRecipesApi.lookup({
      dose_role: role,
      nutrient_phase: recipeNutrientPhase.value,
    })
  } catch (err) {
    const uiErr = toUiApiError(err, 'Rezept konnte nicht geladen werden')
    recipeLoadError.value = formatUiApiError(uiErr)
    // 404 = kein Seed/Rolle×Phase — inline reicht. Toast nur bei Server/Netz.
    if (uiErr.status === 0 || uiErr.status >= 500) {
      toast.error('Rezept-Lookup fehlgeschlagen')
    }
  } finally {
    recipeLoading.value = false
  }
}

function openRecipeEdit() {
  const recipe = recipeLoaded.value
  if (!recipe) return
  recipeEditDraft.value = recipe.components.map((c) => ({
    name: c.name,
    target_g_per_l: c.target_g_per_l,
  }))
  recipeEditOpen.value = true
}

/**
 * AUT-1403: soft A/B-split hint while editing (not a save gate).
 * Signal = component name tokens from seed recipes (no Ca-flag in model).
 */
const recipeAbSplitWarning = computed((): string | null => {
  if (!recipeEditOpen.value) return null
  const recipe = recipeLoaded.value
  if (!recipe) return null
  return resolveAbSplitWarning(
    recipe.dose_role,
    recipeEditDraft.value.map((c) => c.name),
  )
})

async function saveRecipeEdit(): Promise<void> {
  const recipe = recipeLoaded.value
  if (!recipe) return
  const comps = recipeEditDraft.value
  const parsed = comps.map((c) => ({
    name: c.name,
    target_g_per_l: Number(c.target_g_per_l),
  }))
  if (parsed.some((c) => !Number.isFinite(c.target_g_per_l) || c.target_g_per_l < 0)) {
    toast.error('g/L-Werte müssen ≥ 0 sein')
    return
  }
  // Warning is display-only — never block save (AUT-1403 / Robin-Scope).
  recipeEditSaving.value = true
  try {
    recipeLoaded.value = await stockMixRecipesApi.update(recipe.id, {
      components: parsed,
    })
    recipeEditOpen.value = false
    toast.success('Rezept-Werte (g/L) gespeichert')
    emit('changed')
  } catch (err) {
    toast.error(formatUiApiError(toUiApiError(err, 'Rezept speichern fehlgeschlagen')))
  } finally {
    recipeEditSaving.value = false
  }
}

/**
 * AUT-1414 SR-3: confirm then atomic reset via AUT-1412 helper.
 * No optimistic UI — toast only after server success/failure.
 */
async function onStockResetPrepared(): Promise<void> {
  const pump = selectedPump.value
  const recipe = recipeLoaded.value
  if (!pump || !recipe || !showStockResetButton.value) return

  const { title, message } = buildStockResetConfirmMessage({
    doseRole: selectedRole.value,
    recipeLabel: recipe.label,
  })
  const ok = await uiStore.confirm({
    title,
    message,
    variant: 'warning',
    confirmText: 'Ja, neu angesetzt',
  })
  if (!ok) return

  stockResetSaving.value = true
  try {
    await actuatorsApi.resetStockPrepared(pump.espId, pump.gpio, recipe.id)
    toast.success(
      'Konzentration zurückgesetzt — wird bei nächster Dosierung neu gemessen.',
    )
    emit('changed')
  } catch (err) {
    toast.error(
      formatUiApiError(toUiApiError(err, 'Stock-Reset fehlgeschlagen')),
    )
  } finally {
    stockResetSaving.value = false
  }
}

async function reload(): Promise<void> {
  try {
    await discoverPumps()
    await loadStockMixRecipe()
  } catch (e) {
    logger.error(`Failed to reload stock-mix panel for tank ${props.tankId}`, e)
  }
}

defineExpose({ reload })

watch(discoveredPumps, (pumps) => {
  if (pumps.length === 0) {
    selectedRole.value = null
    return
  }
  if (!selectedRole.value || !pumps.some((p) => p.doseRole === selectedRole.value)) {
    selectedRole.value = pumps[0].doseRole
  }
})

watch([selectedRole, recipeNutrientPhase], () => {
  void loadStockMixRecipe()
})

onMounted(() => {
  if (props.tankId) void reload()
})

watch(
  () => props.tankId,
  (id, prev) => {
    if (id && id !== prev) void reload()
  },
)
</script>

<template>
  <section class="stock-mix" aria-labelledby="stock-mix-heading">
    <div class="stock-mix__head">
      <h2 id="stock-mix-heading" class="stock-mix__title">
        <FlaskConical class="w-4 h-4 shrink-0" aria-hidden="true" />
        <span>Stock ansetzen</span>
      </h2>
    </div>

    <p class="stock-mix__hint">
      Wasser-Menge und Phase eingeben — Gramm-Werte kommen aus dem
      Stammlösungs-Rezept. Schreibt keine Konzentration; Wahrheit bleibt der
      Mess-Assistent in der Hardware-Ansicht.
    </p>

    <div v-if="isLoadingPumps" class="stock-mix__state">
      <BaseSpinner size="sm" aria-label="Lade Dosierpumpen" />
      <span>Lade Dosierpumpen…</span>
    </div>

    <EmptyState
      v-else-if="discoveredPumps.length === 0"
      :icon="FlaskConical"
      title="Keine Dosierpumpe mit Rezept-Rolle am Tank"
      description="Weise einer Pumpe an diesem Tank unter Grundlagen eine Rezept-Rolle (Stock A/B, pH-Minus) zu, damit hier ein Rezept geladen werden kann."
      :show-action="false"
    />

    <template v-else>
      <div class="stock-mix__params">
        <BaseSelect
          :model-value="selectedRole ?? ''"
          :options="roleOptions"
          label="Dosierpumpe / Rolle"
          @update:model-value="selectedRole = ($event as DoseRole) || null"
        />
        <BaseSelect
          v-model="recipeNutrientPhase"
          :options="STOCK_MIX_PHASE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))"
          label="Phase"
        />
        <BaseInput
          v-model="recipeVesselMlInput"
          type="number"
          label="Wasser-Menge (destilliert)"
          :min="1"
          :step="1"
          helper="ml"
          aria-label="Wasser-Menge in Millilitern"
        />
      </div>

      <h3 class="stock-mix__step-title">{{ recipeStockTitle }}</h3>

      <p v-if="recipeLoading" class="stock-mix__helper" aria-live="polite">
        Rezept wird geladen…
      </p>
      <p
        v-else-if="recipeLoadError"
        class="stock-mix__helper stock-mix__helper--warn"
        role="alert"
      >
        {{ recipeLoadError }}
      </p>

      <template v-else-if="recipeLoaded">
        <div class="stock-mix__grams" role="status" aria-live="polite">
          <p
            v-for="(row, idx) in recipeGrams"
            :key="`${row.name}-${idx}`"
            class="stock-mix__grams-row"
            :class="{ 'stock-mix__grams-row--ready': row.grams != null }"
          >
            {{
              row.grams == null
                ? `Für ${recipeRoleLabel}, Phase ${recipePhaseLabel}: wieg ${row.name} = … g ein`
                : `Für ${recipeRoleLabel}, Phase ${recipePhaseLabel}: wieg ${row.name} = ${formatGramsDe(row.grams)} g ein`
            }}
          </p>
          <p v-if="recipeGramsTotal != null" class="stock-mix__grams-total">
            Gesamt {{ formatGramsDe(recipeGramsTotal) }} g
          </p>
        </div>

        <p v-if="recipeDoseMlPerL != null" class="stock-mix__helper" aria-live="polite">
          Rezept-Absicht (Anzeige): {{ formatMlDe(recipeDoseMlPerL) }}&nbsp;ml Stock je Liter Tank
          — tatsächliche Dosis kommt aus Messung / volume_share × Konzentration
          <span v-if="recipeDiluteSafer"> (automatisch angepasst)</span>.
        </p>

        <div v-if="recipeCanDiluteSafer" class="stock-mix__dilute">
          <BaseToggle
            :model-value="recipeDiluteSafer"
            label="Verdünnter ansetzen"
            description="Falls es trüb bleibt — Gramm und Dosis werden automatisch neu gerechnet."
            @update:model-value="recipeDiluteSafer = $event"
          />
        </div>

        <div class="stock-mix__edit">
          <BaseButton
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Rezept-Werte g pro Liter bearbeiten"
            @click="recipeEditOpen ? (recipeEditOpen = false) : openRecipeEdit()"
          >
            {{ recipeEditOpen ? 'Rezept-Werte schließen' : 'Rezept-Werte (g/L) bearbeiten' }}
          </BaseButton>
          <div v-if="recipeEditOpen" class="stock-mix__edit-form">
            <div
              v-for="(row, eIdx) in recipeEditDraft"
              :key="`edit-${row.name}-${eIdx}`"
              class="stock-mix__field"
            >
              <BaseInput
                v-model="row.target_g_per_l"
                type="number"
                :label="row.name"
                :min="0"
                :step="0.1"
                helper="g/L"
                :aria-label="`${row.name} Ziel g pro Liter`"
              />
            </div>
            <p
              v-if="recipeAbSplitWarning"
              class="stock-mix__helper stock-mix__helper--warn"
              role="status"
              data-testid="stock-mix-ab-split-warning"
            >
              {{ recipeAbSplitWarning }}
            </p>
            <BaseButton
              type="button"
              variant="primary"
              size="sm"
              :loading="recipeEditSaving"
              aria-label="Rezept-Werte speichern"
              @click="saveRecipeEdit"
            >
              g/L speichern
            </BaseButton>
          </div>
        </div>

        <div
          v-if="showStockResetButton"
          class="stock-mix__reset"
          data-testid="stock-reset-button-wrap"
        >
          <BaseButton
            type="button"
            variant="secondary"
            size="sm"
            :loading="stockResetSaving"
            data-testid="stock-reset-button"
            :aria-label="`Stock neu angesetzt für ${recipeRoleLabel}`"
            @click="onStockResetPrepared"
          >
            Stock neu angesetzt
          </BaseButton>
          <p class="stock-mix__helper">
            Setzt die gespeicherte Konzentration der Pumpe zurück — Messung beim
            nächsten Dosierlauf.
          </p>
        </div>
      </template>
    </template>
  </section>
</template>

<style scoped>
.stock-mix {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  max-width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-card, var(--color-bg-secondary));
  box-sizing: border-box;
}

.stock-mix__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  flex-wrap: wrap;
  min-width: 0;
}

.stock-mix__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.stock-mix__hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.stock-mix__state {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.stock-mix__params {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-2);
  min-width: 0;
}

@media (min-width: 480px) {
  .stock-mix__params {
    grid-template-columns: 1fr 1fr;
  }
}

@media (min-width: 768px) {
  .stock-mix__params {
    grid-template-columns: 1fr 1fr 1fr;
  }
}

.stock-mix__step-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.stock-mix__helper {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.stock-mix__helper--warn {
  color: var(--color-warning);
}

.stock-mix__label {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.stock-mix__grams {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px dashed var(--color-accent, var(--glass-border));
  background: color-mix(in srgb, var(--color-accent, #6b8cae) 8%, transparent);
}

.stock-mix__grams-row {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.stock-mix__grams-row--ready {
  color: var(--color-text-primary);
  font-weight: 500;
}

.stock-mix__grams-total {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.stock-mix__dilute {
  min-width: 0;
}

.stock-mix__reset {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border);
}

.stock-mix__edit {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.stock-mix__edit-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
}

.stock-mix__field {
  min-width: 0;
}
</style>
