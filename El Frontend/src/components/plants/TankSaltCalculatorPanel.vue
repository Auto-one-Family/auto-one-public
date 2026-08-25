<script setup lang="ts">
/**
 * Salt calculator panel (Salzrechner) (AUT-1344 PKG-02 / P7).
 *
 * Shows feedforward expectation (A/B ml + expected EC) from the server Assist
 * API only (AUT-1368: no second FE ratio formula). After AUT-1367 the Assist
 * derives ratio_share from volume_share×concentration so preview ml match
 * LogicEngine dosing. System-EC is the operating truth. Target write goes
 * through TankEcPhPlanEditor.applySystemEcAsTarget (P6 path).
 *
 * AUT-1375 A1.1: concentration A/B display reads pump SSOT
 * (actuator_configs.concentration × dose_role part_a/part_b), not only Assist.
 */

import { computed, onMounted, ref, watch } from 'vue'
import { Beaker, Info, RefreshCw, Target } from 'lucide-vue-next'
import { actuatorsApi } from '@/api/actuators'
import { tanksApi } from '@/api/tanks'
import { useEspStore } from '@/stores/esp'
import { useUiStore } from '@/shared/stores/ui.store'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import BaseToggle from '@/shared/design/primitives/BaseToggle.vue'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'
import {
  findIstSensorValue,
  formatIstSollValue,
} from '@/components/plants/tankIstSollFormat'
import {
  formatAssistVolumeRatioLabel,
  buildSaltAssistOperatorHints,
  suggestionKindLabel,
} from '@/components/plants/saltCalculatorPreviewLabels'
import { formatStockConcentrationStatus } from '@/components/plants/stockConcentrationStatus'
import { stockMixRecipesApi } from '@/api/stockMixRecipes'
import type { TankTargetsResponse, SaltCalculatorAssistResponse } from '@/types'
import type { VolumeZugabeSource } from '@/types/measureBinding'
import {
  formatMeasuredFreshWaterOrigin,
  volumeZugabeSourceLabel,
} from '@/utils/volumeZugabeSourceDisplay'
import { createLogger } from '@/utils/logger'

const logger = createLogger('TankSaltCalculatorPanel')

interface Props {
  tankId: string
  tankName?: string
  /**
   * @deprecated AUT-1404 — not used; volume comes from V_real / ledger only.
   * Kept so parent bindings stay valid.
   */
  nominalVolumeL?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  tankName: '',
  nominalVolumeL: null,
})

const emit = defineEmits<{
  /**
   * Ask parent to write System-EC via P6 editor path.
   * Parent must call TankEcPhPlanEditor.applySystemEcAsTarget.
   */
  'apply-system-ec': [ecUsCm: number]
  /** After assist/targets change — parent may refresh Ist/Soll. */
  changed: []
}>()

const espStore = useEspStore()
const uiStore = useUiStore()
const toast = useToast()

const targets = ref<TankTargetsResponse | null>(null)
const expectation = ref<SaltCalculatorAssistResponse | null>(null)
const isLoadingTargets = ref(false)
const isComputing = ref(false)
const error = ref<string | null>(null)

/** AUT-1397/1404: measured zugabe from server only (read-only display). */
const volumeZugabeL = ref(0)
const volumeZugabeSource = ref<VolumeZugabeSource>('none')
const volumeZugabeOccurredAt = ref<string | null>(null)
const volumeZugabeLabel = ref<string | null>(null)
/** AUT-1404: explicit Frischbatch — start from Frischwasser-EC. */
const freshBatch = ref(false)
/**
 * AUT-1375 / AUT-1355: pump SSOT concentration (read-only).
 * Loaded via actuatorsApi — same source as tank_service._resolve_pump_concentrations.
 */
const pumpConcA = ref<number | null>(null)
const pumpConcB = ref<number | null>(null)
/** AUT-1413: soft identity for status mirror (same helper as Kalibrier-Tab). */
const pumpStatusA = ref<{ recipeLabel: string | null; preparedAt: string | null }>({
  recipeLabel: null,
  preparedAt: null,
})
const pumpStatusB = ref<{ recipeLabel: string | null; preparedAt: string | null }>({
  recipeLabel: null,
  preparedAt: null,
})
const isLoadingPumpConc = ref(false)

const volumeZugabeOriginText = computed(() => {
  if (volumeZugabeSource.value === 'measured') {
    return formatMeasuredFreshWaterOrigin({
      ruleName: volumeZugabeLabel.value,
      occurredAt: volumeZugabeOccurredAt.value,
      volumeL: volumeZugabeL.value,
    })
  }
  return 'keine gemessene Nachfüllung'
})

const suggestionKind = computed(
  () => expectation.value?.suggestion_kind ?? null,
)

const directionLabel = computed(() => suggestionKindLabel(suggestionKind.value))

const assignedDeviceIds = computed(() => {
  const fromTargets = targets.value?.assigned_device_ids ?? []
  if (fromTargets.length > 0) return fromTargets
  // Fallback: esp_devices.tank_id membership (AUT-1223 / AUT-1221)
  return espStore.devices
    .filter((d) => (d as { tank_id?: string | null }).tank_id === props.tankId)
    .map((d) => espStore.getDeviceId(d))
    .filter((id): id is string => !!id)
})

const systemEc = computed((): number | null =>
  findIstSensorValue(espStore.devices, assignedDeviceIds.value, 'ec'),
)

const targetEc = computed((): number | null => {
  const row = targets.value?.targets.find((t) => t.measure === 'target_ec')
  if (row?.value == null || Number.isNaN(Number(row.value))) return null
  return Number(row.value)
})

const systemEcDisplay = computed(() => formatIstSollValue(systemEc.value, 0))
const targetEcDisplay = computed(() => formatIstSollValue(targetEc.value, 0))

const canCompute = computed(
  () => systemEc.value != null && targetEc.value != null && !isComputing.value,
)

/** AUT-1404 D5: only pump SSOT — never Assist/Platzhalter 100 as truth. */
const concentrationADisplay = computed(() => {
  if (isLoadingPumpConc.value) return '…'
  if (pumpConcA.value != null && pumpConcA.value > 0) {
    return formatIstSollValue(pumpConcA.value, 1)
  }
  return 'nicht kalibriert'
})
const concentrationBDisplay = computed(() => {
  if (isLoadingPumpConc.value) return '…'
  if (pumpConcB.value != null && pumpConcB.value > 0) {
    return formatIstSollValue(pumpConcB.value, 1)
  }
  return 'nicht kalibriert'
})
const concentrationsCalibrated = computed(
  () =>
    pumpConcA.value != null &&
    pumpConcA.value > 0 &&
    pumpConcB.value != null &&
    pumpConcB.value > 0,
)

/** AUT-1413: mirrored stock status (short) — no second state logic. */
const stockStatusAShort = computed(() =>
  formatStockConcentrationStatus({
    concentration: pumpConcA.value,
    recipeLabel: pumpStatusA.value.recipeLabel,
    stockPreparedAt: pumpStatusA.value.preparedAt,
  }).shortLabel,
)
const stockStatusBShort = computed(() =>
  formatStockConcentrationStatus({
    concentration: pumpConcB.value,
    recipeLabel: pumpStatusB.value.recipeLabel,
    stockPreparedAt: pumpStatusB.value.preparedAt,
  }).shortLabel,
)

async function resolveRecipeLabel(recipeId: string | null | undefined): Promise<string | null> {
  if (!recipeId) return null
  try {
    const recipe = await stockMixRecipesApi.get(recipeId)
    return recipe.label || null
  } catch {
    return null
  }
}

/** AUT-1368: label from server ml only — not a local EC-share assumption. */
const volumeRatioLabel = computed(() => {
  const e = expectation.value
  if (!e) return ''
  return formatAssistVolumeRatioLabel(e.dose_a_ml, e.dose_b_ml)
})

const canApplySystemEc = computed(
  () => systemEc.value != null && Number.isFinite(systemEc.value),
)

/** Operator-Hinweise aus Assist-Feldern — keine Roh-Notes (GPIO/dose_role). */
const operatorHints = computed(() => {
  const e = expectation.value
  if (!e) return []
  return buildSaltAssistOperatorHints({
    volume_alt_l: e.volume_alt_l,
    volume_alt_source: e.volume_alt_source,
    volume_zugabe_l: e.volume_zugabe_l,
    ec_wasser_us_cm: e.ec_wasser_us_cm,
    ec_wasser_source: e.ec_wasser_source,
    ec_after_dilution_us_cm: e.ec_after_dilution_us_cm,
  })
})

/**
 * AUT-1375 A1.1: Read concentration from pump SSOT (dose_role part_a/part_b).
 * Pattern mirrors ActuatorConfigPanel.scalePartnerConcentration (actuatorsApi.get).
 */
async function loadPumpConcentrations(): Promise<void> {
  pumpConcA.value = null
  pumpConcB.value = null
  pumpStatusA.value = { recipeLabel: null, preparedAt: null }
  pumpStatusB.value = { recipeLabel: null, preparedAt: null }
  const deviceIds = assignedDeviceIds.value
  if (deviceIds.length === 0) return

  isLoadingPumpConc.value = true
  let seenA = false
  let seenB = false
  try {
    for (const espId of deviceIds) {
      const device = espStore.devices.find((d) => espStore.getDeviceId(d) === espId)
      const actuators = (device?.actuators as { gpio: number }[] | undefined) ?? []
      for (const act of actuators) {
        if (typeof act.gpio !== 'number') continue
        try {
          const cfg = await actuatorsApi.get(espId, act.gpio)
          const role = (cfg.dose_role ?? '').trim().toLowerCase()
          if (role !== 'part_a' && role !== 'part_b') continue
          if (role === 'part_a' && seenA) continue
          if (role === 'part_b' && seenB) continue

          const value = cfg.concentration
          const preparedAt = cfg.stock_prepared_at ?? null
          const recipeLabel = await resolveRecipeLabel(cfg.stock_recipe_ref)
          const conc =
            value != null && Number.isFinite(value) && value > 0 ? value : null

          if (role === 'part_a') {
            seenA = true
            pumpConcA.value = conc
            pumpStatusA.value = { recipeLabel, preparedAt }
          } else {
            seenB = true
            pumpConcB.value = conc
            pumpStatusB.value = { recipeLabel, preparedAt }
          }
        } catch {
          // try next actuator — same fail-soft as partner-scale path
        }
      }
      if (seenA && seenB) break
    }
  } finally {
    isLoadingPumpConc.value = false
  }
}

function applyZugabeFromAssist(result: SaltCalculatorAssistResponse): void {
  const source = result.volume_zugabe_source
  if (source === 'manual' || source === 'measured' || source === 'none') {
    volumeZugabeSource.value = source
  } else {
    volumeZugabeSource.value = 'none'
  }
  volumeZugabeOccurredAt.value = result.volume_zugabe_occurred_at ?? null
  volumeZugabeLabel.value = result.volume_zugabe_label ?? null
  volumeZugabeL.value =
    source === 'measured' && result.volume_zugabe_l > 0
      ? result.volume_zugabe_l
      : 0
}

async function loadTargets(): Promise<void> {
  if (!props.tankId) return
  isLoadingTargets.value = true
  error.value = null
  try {
    targets.value = await tanksApi.getTargets(props.tankId)
    if (espStore.devices.length === 0) {
      await espStore.fetchAll()
    }
    await loadPumpConcentrations()
    // AUT-1375: auto-preview so Ratio-Verify (AUT-1372 Schritt 2) needs no extra click
    if (systemEc.value != null && targetEc.value != null) {
      void computeExpectation()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Ziele konnten nicht geladen werden'
    logger.error(`Failed to load targets for tank ${props.tankId}`, e)
  } finally {
    isLoadingTargets.value = false
  }
}

async function computeExpectation(): Promise<void> {
  error.value = null
  expectation.value = null
  if (systemEc.value == null) {
    error.value = 'Kein gemessener EC — Sensorwert am Tank wird benötigt.'
    return
  }
  if (targetEc.value == null) {
    error.value = 'Kein EC-Ziel — bitte zuerst unter „EC- & pH-Ziele“ anlegen.'
    return
  }

  isComputing.value = true
  try {
    // AUT-1355: concentration from pump SSOT — omit request field.
    // AUT-1404: V_real / ledger only — no nominal default, no manual Liter.
    // volume_zugabe_l=0 → server resolves measured ledger prefill.
    // Frischwasser-EC: tank.fresh_water_ec_us_cm on server — never invent 488.
    const baseReq = {
      current_ec_us_cm: systemEc.value,
      target_ec_us_cm: targetEc.value,
      volume_zugabe_l: 0,
      fresh_batch: freshBatch.value,
    }
    let result: SaltCalculatorAssistResponse
    try {
      result = await tanksApi.computeDoseExpectation(props.tankId, baseReq)
    } catch (firstErr) {
      // Explicit V_real if server assist could not resolve volume from ledger.
      const volume = await tanksApi.getVolume(props.tankId)
      if (volume.volume_l != null && volume.volume_l > 0) {
        result = await tanksApi.computeDoseExpectation(props.tankId, {
          ...baseReq,
          volume_alt_l: volume.volume_l,
        })
      } else {
        throw firstErr
      }
    }
    expectation.value = result
    applyZugabeFromAssist(result)
  } catch (e) {
    const raw = e instanceof Error ? e.message : 'Erwartung konnte nicht berechnet werden'
    // AUT-1404 D4: honest volume failure — no nominal invent.
    if (/V_alt unresolved|volume|nicht gemessen|volume_alt/i.test(raw)) {
      error.value = 'Tankvolumen nicht gemessen — Erwartung ohne Volumen nicht möglich.'
    } else {
      error.value = raw
    }
    logger.error(`Assist failed for tank ${props.tankId}`, e)
  } finally {
    isComputing.value = false
  }
}

async function onApplySystemEc(): Promise<void> {
  const ec = systemEc.value
  if (ec == null || !Number.isFinite(ec)) {
    toast.error('Kein gemessener EC')
    return
  }
  const ok = await uiStore.confirm({
    title: 'Gemessenen EC als Ziel übernehmen?',
    message:
      `Der gemessene EC ${formatIstSollValue(ec, 0)} µS/cm wird als neues EC-Ziel` +
      ` für ${props.tankName || 'diesen Tank'} gesetzt` +
      ` (wie unter „EC- & pH-Ziele“).`,
    variant: 'warning',
    confirmText: 'Übernehmen',
  })
  if (!ok) return
  emit('apply-system-ec', ec)
}

defineExpose({
  reload: loadTargets,
})

onMounted(() => {
  if (props.tankId) void loadTargets()
})

watch(
  () => props.tankId,
  (id, prev) => {
    if (id && id !== prev) {
      expectation.value = null
      volumeZugabeL.value = 0
      volumeZugabeSource.value = 'none'
      volumeZugabeOccurredAt.value = null
      volumeZugabeLabel.value = null
      freshBatch.value = false
      void loadTargets()
    }
  },
)

watch(freshBatch, () => {
  if (systemEc.value != null && targetEc.value != null) {
    void computeExpectation()
  }
})
</script>

<template>
  <section class="salt-calculator" aria-labelledby="salt-calculator-heading">
    <div class="salt-calculator__head">
      <h2 id="salt-calculator-heading" class="salt-calculator__title">
        <Beaker class="w-4 h-4 shrink-0" aria-hidden="true" />
        <span>Salzrechner</span>
      </h2>
      <BaseButton
        type="button"
        variant="ghost"
        size="sm"
        aria-label="Erwartung neu berechnen"
        :disabled="!canCompute"
        :loading="isComputing"
        @click="computeExpectation"
      >
        <RefreshCw class="w-4 h-4" aria-hidden="true" />
        <span>Erwartung</span>
      </BaseButton>
    </div>

    <p class="salt-calculator__hint">
      Nur Vorschlag — dosiert nichts. Der gemessene EC zählt.
    </p>

    <div v-if="isLoadingTargets" class="salt-calculator__state">
      <BaseSpinner size="sm" aria-label="Lade Ziele" />
      <span>Lade Ist und Ziel…</span>
    </div>

    <template v-else>
      <div class="salt-calculator__metrics" role="group" aria-label="Ist und Ziel EC">
        <div class="salt-calculator__metric">
          <span class="salt-calculator__metric-label">Gemessener EC</span>
          <span class="salt-calculator__metric-value">
            {{ systemEcDisplay }}
            <span class="salt-calculator__unit">µS/cm</span>
          </span>
        </div>
        <div class="salt-calculator__metric">
          <span class="salt-calculator__metric-label">Ziel-EC</span>
          <span class="salt-calculator__metric-value">
            {{ targetEcDisplay }}
            <span class="salt-calculator__unit">µS/cm</span>
          </span>
        </div>
      </div>

      <div class="salt-calculator__params">
        <div class="salt-calculator__metric" role="group" aria-label="Wirkstärke der Stammlösungen">
          <span class="salt-calculator__metric-label">Wirkstärke Stock A / B</span>
          <span class="salt-calculator__metric-value" data-testid="salt-concentration-display">
            {{ concentrationADisplay }} / {{ concentrationBDisplay }}
            <span
              v-if="concentrationsCalibrated"
              class="salt-calculator__unit"
            >µS/cm je ml/L</span>
          </span>
          <span
            class="salt-calculator__hint"
            data-testid="salt-stock-status"
            role="status"
            aria-label="Konzentrations-Zustand Stock A und B"
          >
            A: {{ stockStatusAShort }} · B: {{ stockStatusBShort }}
          </span>
          <span class="salt-calculator__hint">
            Live von den Dosierpumpen, nur Anzeige.
            Nicht kalibriert → kein präziser ml-Vorschlag.
          </span>
        </div>
        <div class="salt-calculator__zugabe" data-testid="fresh-water-zugabe">
          <span class="salt-calculator__metric-label">Frischwasser-Nachfüllung</span>
          <span
            class="salt-calculator__metric-value"
            data-testid="fresh-water-zugabe-readonly"
          >
            <template v-if="volumeZugabeSource === 'measured' && volumeZugabeL > 0">
              {{ formatIstSollValue(volumeZugabeL, 1) }}
              <span class="salt-calculator__unit">L (gemessen)</span>
            </template>
            <template v-else>—</template>
          </span>
          <p
            class="salt-calculator__source"
            data-testid="fresh-water-source"
            role="status"
          >
            <span
              class="salt-calculator__source-badge"
              :data-source="volumeZugabeSource"
            >
              {{ volumeZugabeSourceLabel(volumeZugabeSource) }}
            </span>
            <span class="salt-calculator__source-origin">{{ volumeZugabeOriginText }}</span>
          </p>
        </div>
        <div data-testid="fresh-batch-toggle">
          <BaseToggle
            v-model="freshBatch"
            size="sm"
            label="Frischbatch"
            description="Neuer Ansatz: Rechnung startet am Frischwasser-EC (nicht am gemessenen Tank-EC)."
          />
        </div>
        <p class="salt-calculator__hint" data-testid="fresh-water-ec-hint">
          Frischwasser-EC und Tankvolumen kommen vom Tank bzw. Sensor —
          nicht von Hand eintragen.
        </p>
      </div>

      <ErrorState
        v-if="error && !expectation"
        :message="error"
        @retry="computeExpectation"
      />

      <div
        class="salt-calculator__expect"
        :class="{ 'salt-calculator__expect--empty': !expectation }"
        role="status"
        aria-live="polite"
      >
        <span
          class="salt-calculator__expect-badge"
          data-testid="salt-assist-direction-label"
        >
          {{ directionLabel }}
        </span>
        <template v-if="expectation">
          <p
            class="salt-calculator__operator-msg"
            data-testid="salt-assist-operator-message"
          >
            {{ expectation.operator_message }}
          </p>

          <template v-if="suggestionKind === 'dose_up'">
            <p class="salt-calculator__expect-doses">
              <span>Stock A {{ formatIstSollValue(expectation.dose_a_ml, 0) }} ml</span>
              <span aria-hidden="true">·</span>
              <span>Stock B {{ formatIstSollValue(expectation.dose_b_ml, 0) }} ml</span>
              <span class="salt-calculator__expect-ratio">({{ volumeRatioLabel }})</span>
            </p>
            <p class="salt-calculator__expect-ec">
              Erwarteter EC danach:
              {{ formatIstSollValue(expectation.expected_ec_us_cm, 0) }}
              µS/cm
            </p>
          </template>

          <template v-else-if="suggestionKind === 'dilute'">
            <p
              class="salt-calculator__expect-doses"
              data-testid="salt-assist-dilute-liters"
            >
              Frischwasser ca.
              {{ formatIstSollValue(expectation.fresh_water_suggest_l ?? 0, 1) }}
              L
            </p>
            <p class="salt-calculator__expect-ec">
              Kein Salz — Ausführung über die Frischwasser-/Level-Regel,
              nicht über diesen Rechner.
            </p>
          </template>

          <template v-else-if="suggestionKind === 'within_tolerance'">
            <p class="salt-calculator__expect-ec">
              Kein Vorschlag — Ist und Ziel liegen im Zielband.
            </p>
          </template>

          <template v-else-if="suggestionKind === 'unavailable'">
            <p class="salt-calculator__expect-ec">
              Kein präziser ml- oder Liter-Vorschlag möglich.
            </p>
          </template>

          <ul v-if="operatorHints.length" class="salt-calculator__notes">
            <li v-for="(hint, idx) in operatorHints" :key="idx">{{ hint }}</li>
          </ul>
        </template>
        <p v-else class="salt-calculator__expect-empty-text">
          „Erwartung“ tippen — zeigt Aufdosieren, Verdünnen oder „passt“
          (ohne zu dosieren).
        </p>
      </div>

      <p v-if="error && expectation" class="salt-calculator__inline-error" role="alert">
        {{ error }}
      </p>

      <BaseButton
        type="button"
        variant="primary"
        size="sm"
        class="salt-calculator__apply"
        :disabled="!canApplySystemEc"
        aria-label="Gemessenen EC als Ziel übernehmen"
        @click="onApplySystemEc"
      >
        <Target class="w-4 h-4" aria-hidden="true" />
        <span>Gemessenen EC als Ziel übernehmen</span>
      </BaseButton>

      <aside class="salt-calculator__seq" aria-label="Misch-Hinweis">
        <Info class="w-4 h-4 shrink-0 salt-calculator__seq-icon" aria-hidden="true" />
        <p>
          Zuerst Stock A, umrühren, dann Stock B, kurz warten, EC prüfen.
          pH danach in kleinen Schritten — hier nur Hinweis, keine Ausführung.
        </p>
      </aside>
    </template>
  </section>
</template>

<style scoped>
.salt-calculator {
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

.salt-calculator__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  flex-wrap: wrap;
  min-width: 0;
}

.salt-calculator__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.salt-calculator__hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.salt-calculator__state {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.salt-calculator__metrics {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-2);
}

@media (min-width: 480px) {
  .salt-calculator__metrics {
    grid-template-columns: 1fr 1fr;
  }
}

.salt-calculator__metric {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
}

.salt-calculator__metric-label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.salt-calculator__metric-value {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  word-break: break-word;
}

.salt-calculator__unit {
  font-size: var(--text-sm);
  font-weight: 400;
  color: var(--color-text-secondary);
}

.salt-calculator__params {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-2);
  min-width: 0;
}

@media (min-width: 480px) {
  .salt-calculator__params {
    grid-template-columns: 1fr 1fr;
  }
}

.salt-calculator__expect {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px dashed var(--color-accent, var(--glass-border));
  background: color-mix(in srgb, var(--color-accent, #6b8cae) 8%, transparent);
}

.salt-calculator__expect--empty {
  border-style: solid;
  border-color: var(--glass-border);
  background: var(--color-bg-tertiary);
}

.salt-calculator__expect-badge {
  align-self: flex-start;
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-accent, var(--color-text-secondary));
}

.salt-calculator__expect-doses {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.salt-calculator__expect-ratio {
  font-size: var(--text-sm);
  font-weight: 400;
  color: var(--color-text-secondary);
}

.salt-calculator__expect-ec,
.salt-calculator__expect-meta,
.salt-calculator__expect-empty-text {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.salt-calculator__expect-ec {
  color: var(--color-text-primary);
  font-weight: 500;
}

.salt-calculator__operator-msg {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  line-height: 1.45;
}

.salt-calculator__notes {
  margin: 0;
  padding-left: var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.salt-calculator__inline-error {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-danger);
}

.salt-calculator__apply {
  width: 100%;
  justify-content: center;
}

.salt-calculator__seq {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.45;
}

.salt-calculator__seq p {
  margin: 0;
  min-width: 0;
}

.salt-calculator__seq-icon {
  color: var(--color-info, var(--color-text-secondary));
  margin-top: 1px;
}

.salt-calculator__zugabe {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.salt-calculator__source {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.35;
}

.salt-calculator__source-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-dark-600);
  background: var(--color-dark-800);
  color: var(--color-dark-100);
  font-weight: 600;
  text-transform: lowercase;
}

.salt-calculator__source-badge[data-source='measured'] {
  border-color: color-mix(in srgb, var(--color-success) 45%, transparent);
  color: var(--color-success);
}

.salt-calculator__source-badge[data-source='manual'] {
  border-color: color-mix(in srgb, var(--color-warning) 45%, transparent);
  color: var(--color-warning);
}

.salt-calculator__source-origin {
  min-width: 0;
  flex: 1 1 12rem;
}
</style>
