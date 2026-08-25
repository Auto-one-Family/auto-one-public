<script setup lang="ts">
/**
 * Zone plan staffel editor (AUT-1340 P6, AUT-1536 T/RH).
 *
 * Writes zone-wide plan_segments via usePlanSegmentsStore. Nutrient pair
 * (EC/pH) + climate pair (T/RH) share one component and one modal instance.
 * VPD is derived display only. PlanSegmentEditorModal stays unmounted.
 * phase_ref = NUTRIENT_PHASES for EC/pH only (AUT-1361 / P9).
 */

import { computed, ref, watch } from 'vue'
import { Pencil, Plus, Target, Thermometer, Trash2 } from 'lucide-vue-next'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import { usePlanSegmentsStore } from '@/shared/stores/planSegments.store'
import { useUiStore } from '@/shared/stores/ui.store'
import { useToast } from '@/composables/useToast'
import { NUTRIENT_PHASES } from '@/types'
import { getPlantPhaseLabel } from '@/components/plants/plantLabels'
import {
  clampPlanMeasureValue,
  getPlanMeasureInputSpec,
} from '@/components/plan-timeline/planMeasureInput'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'
import { calculateVpdKpa } from '@/components/plan-timeline/planVpdOverlay'
import {
  CLIMATE_PLAN_DOMAIN,
  CLIMATE_PLAN_MEASURE_RH,
  CLIMATE_PLAN_MEASURE_TEMP,
  TANK_PLAN_DOMAIN,
  TANK_PLAN_MEASURE_EC,
  TANK_PLAN_MEASURE_PH,
  buildClimateStaffeln,
  buildEcPhStaffeln,
  dateInputToIsoStart,
  findActiveClimateStaffel,
  findActiveEcPhStaffel,
  formatMeasureValue,
  formatStaffelRange,
  isoToDateInput,
  type ClimateStaffel,
  type EcPhStaffel,
} from '@/components/plants/tankEcPhPlanStaffel'

type EditorKind = 'nutrient' | 'climate'
type PlanWriteMeasure =
  | typeof TANK_PLAN_MEASURE_EC
  | typeof TANK_PLAN_MEASURE_PH
  | typeof CLIMATE_PLAN_MEASURE_TEMP
  | typeof CLIMATE_PLAN_MEASURE_RH
type PlanWriteDomain = typeof TANK_PLAN_DOMAIN | typeof CLIMATE_PLAN_DOMAIN

interface Props {
  zoneId: string
  zoneName?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  /** Fired after successful create/update/delete so parent can refresh Ist/Soll. */
  changed: []
}>()

const planStore = usePlanSegmentsStore()
const uiStore = useUiStore()
const toast = useToast()

const nowTick = ref(Date.now())
const editorOpen = ref(false)
const editorKind = ref<EditorKind>('nutrient')
const editingKey = ref<string | null>(null)
const formError = ref<string | null>(null)

const fromDate = ref('')
const toDate = ref('')
const ecValue = ref<string | number>('')
const phValue = ref<string | number>('')
const tempValue = ref<string | number>('')
const rhValue = ref<string | number>('')
/** AUT-1361: NUTRIENT_PHASES key → stock_mix_recipes lookup (active phase). */
const phaseRef = ref<string>('')
/** Segment ids when editing an existing staffel window. */
const editEcId = ref<string | null>(null)
const editPhId = ref<string | null>(null)
const editTempId = ref<string | null>(null)
const editRhId = ref<string | null>(null)

const PHASE_SELECT_OPTIONS = [
  { value: '', label: '— Phase nicht gesetzt —' },
  ...NUTRIENT_PHASES.map((p) => ({ value: p, label: getPlantPhaseLabel(p) })),
]

const staffeln = computed(() =>
  buildEcPhStaffeln(planStore.segments, props.zoneId),
)

const activeStaffel = computed(() =>
  findActiveEcPhStaffel(staffeln.value, nowTick.value),
)

const climateStaffeln = computed(() =>
  buildClimateStaffeln(planStore.segments, props.zoneId),
)

const activeClimateStaffel = computed(() =>
  findActiveClimateStaffel(climateStaffeln.value, nowTick.value),
)

const isClimate = computed(() => editorKind.value === 'climate')

const modalTitle = computed(() => {
  if (isClimate.value) {
    return editingKey.value
      ? 'Temperatur/Feuchte bearbeiten'
      : 'Temperatur/Feuchte anlegen'
  }
  return editingKey.value ? 'EC/pH-Ziel bearbeiten' : 'EC/pH-Ziel anlegen'
})

/** EC input bounds/label — same SSOT as PlanSegmentEditorModal (µS/cm). */
const ecInputSpec = computed(
  () => getPlanMeasureInputSpec(TANK_PLAN_MEASURE_EC) ?? {
    measure: TANK_PLAN_MEASURE_EC,
    label: 'EC',
    unit: 'µS/cm',
    min: 0,
    max: 5000,
    step: 0.1,
  },
)

const phInputSpec = computed(
  () => getPlanMeasureInputSpec(TANK_PLAN_MEASURE_PH) ?? {
    measure: TANK_PLAN_MEASURE_PH,
    label: 'pH',
    unit: '',
    min: 0,
    max: 14,
    step: 0.1,
  },
)

const tempInputSpec = computed(
  () => getPlanMeasureInputSpec(CLIMATE_PLAN_MEASURE_TEMP) ?? {
    measure: CLIMATE_PLAN_MEASURE_TEMP,
    label: 'Temperatur-Ziel',
    unit: '°C',
    min: 0,
    max: 45,
    step: 0.5,
  },
)

const rhInputSpec = computed(
  () => getPlanMeasureInputSpec(CLIMATE_PLAN_MEASURE_RH) ?? {
    measure: CLIMATE_PLAN_MEASURE_RH,
    label: 'Feuchte-Ziel',
    unit: '%',
    min: 0,
    max: 100,
    step: 1,
  },
)

const formVpdLabel = computed(() => {
  const temp = parseLocaleNumber(tempValue.value)
  const rh = parseLocaleNumber(rhValue.value)
  const hasTemp = tempValue.value !== '' && !Number.isNaN(temp)
  const hasRh = rhValue.value !== '' && !Number.isNaN(rh)
  if (!hasTemp && !hasRh) {
    return 'VPD nicht berechenbar (Temperatur- und Feuchte-Ziel fehlen)'
  }
  if (!hasTemp) return 'VPD nicht berechenbar (Temperatur-Ziel fehlt)'
  if (!hasRh) return 'VPD nicht berechenbar (Feuchte-Ziel fehlt)'
  const vpd = calculateVpdKpa(temp, rh)
  if (vpd == null) return 'VPD nicht berechenbar (Werte außerhalb Bereich)'
  return `VPD ${vpd.toFixed(2)} kPa (abgeleitet, nicht gespeichert)`
})

async function loadSegments(): Promise<void> {
  if (!props.zoneId) return
  nowTick.value = Date.now()
  await planStore.fetchSegments({
    zone_id: props.zoneId,
  })
}

watch(
  () => props.zoneId,
  () => {
    void loadSegments()
  },
  { immediate: true },
)

function resetForm(): void {
  formError.value = null
  editingKey.value = null
  editEcId.value = null
  editPhId.value = null
  editTempId.value = null
  editRhId.value = null
  fromDate.value = isoToDateInput(new Date().toISOString())
  toDate.value = ''
  ecValue.value = ''
  phValue.value = ''
  tempValue.value = ''
  rhValue.value = ''
  phaseRef.value = ''
}

function openCreate(kind: EditorKind): void {
  resetForm()
  editorKind.value = kind
  editorOpen.value = true
}

function openEdit(row: EcPhStaffel): void {
  formError.value = null
  editorKind.value = 'nutrient'
  editingKey.value = row.key
  editEcId.value = row.ec?.id ?? null
  editPhId.value = row.ph?.id ?? null
  editTempId.value = null
  editRhId.value = null
  fromDate.value = isoToDateInput(row.fromTs)
  toDate.value = isoToDateInput(row.toTs)
  ecValue.value =
    row.ec?.value == null || Number.isNaN(Number(row.ec.value))
      ? ''
      : Number(row.ec.value)
  phValue.value =
    row.ph?.value == null || Number.isNaN(Number(row.ph.value))
      ? ''
      : Number(row.ph.value)
  tempValue.value = ''
  rhValue.value = ''
  phaseRef.value = row.ec?.phase_ref ?? row.ph?.phase_ref ?? ''
  editorOpen.value = true
}

function openEditClimate(row: ClimateStaffel): void {
  formError.value = null
  editorKind.value = 'climate'
  editingKey.value = row.key
  editEcId.value = null
  editPhId.value = null
  editTempId.value = row.temperature?.id ?? null
  editRhId.value = row.humidity?.id ?? null
  fromDate.value = isoToDateInput(row.fromTs)
  toDate.value = isoToDateInput(row.toTs)
  ecValue.value = ''
  phValue.value = ''
  tempValue.value =
    row.temperature?.value == null || Number.isNaN(Number(row.temperature.value))
      ? ''
      : Number(row.temperature.value)
  rhValue.value =
    row.humidity?.value == null || Number.isNaN(Number(row.humidity.value))
      ? ''
      : Number(row.humidity.value)
  phaseRef.value = ''
  editorOpen.value = true
}

function closeEditor(): void {
  editorOpen.value = false
}

function parseRequiredNumber(raw: string | number, label: string): number | null {
  if (raw === '' || raw == null) {
    formError.value = `Bitte ${label} eingeben.`
    return null
  }
  const n = parseLocaleNumber(raw)
  if (Number.isNaN(n)) {
    formError.value = `Bitte ${label} eingeben.`
    return null
  }
  return n
}

async function upsertMeasure(opts: {
  domain: PlanWriteDomain
  measure: PlanWriteMeasure
  value: number
  fromTs: string
  toTs: string | null
  segmentId: string | null
}): Promise<void> {
  const clamped = clampPlanMeasureValue(opts.measure, opts.value)
  const phase =
    opts.domain === TANK_PLAN_DOMAIN ? phaseRef.value.trim() || null : null
  if (opts.segmentId) {
    await planStore.updateSegment(opts.segmentId, {
      value: clamped,
      from_ts: opts.fromTs,
      to_ts: opts.toTs,
      measure: opts.measure,
      phase_ref: phase,
    })
    return
  }
  await planStore.createSegment({
    zone_id: props.zoneId,
    domain: opts.domain,
    measure: opts.measure,
    value: clamped,
    from_ts: opts.fromTs,
    to_ts: opts.toTs,
    interp: 'step',
    status: 'planned',
    phase_ref: phase,
  })
}

async function onSave(): Promise<void> {
  formError.value = null
  if (!props.zoneId) {
    formError.value = 'Keine Zone — Ziel kann nicht gespeichert werden.'
    return
  }
  const fromTs = dateInputToIsoStart(fromDate.value)
  if (!fromTs) {
    formError.value = 'Bitte ein gültiges Von-Datum wählen.'
    return
  }
  let toTs: string | null = null
  if (toDate.value) {
    toTs = dateInputToIsoStart(toDate.value)
    if (!toTs) {
      formError.value = 'Bitte ein gültiges Bis-Datum wählen oder leer lassen.'
      return
    }
    if (Date.parse(toTs) <= Date.parse(fromTs)) {
      formError.value = 'Bis-Datum muss nach dem Von-Datum liegen.'
      return
    }
  }
  try {
    if (isClimate.value) {
      const temp =
        tempValue.value === '' || tempValue.value == null
          ? null
          : parseRequiredNumber(tempValue.value, 'Temperatur-Ziel')
      if (tempValue.value !== '' && tempValue.value != null && temp == null) return
      const rh =
        rhValue.value === '' || rhValue.value == null
          ? null
          : parseRequiredNumber(rhValue.value, 'Feuchte-Ziel')
      if (rhValue.value !== '' && rhValue.value != null && rh == null) return
      if (temp == null && rh == null) {
        formError.value = 'Bitte Temperatur-Ziel oder Feuchte-Ziel eingeben.'
        return
      }
      if (temp != null) {
        await upsertMeasure({
          domain: CLIMATE_PLAN_DOMAIN,
          measure: CLIMATE_PLAN_MEASURE_TEMP,
          value: temp,
          fromTs,
          toTs,
          segmentId: editTempId.value,
        })
      }
      if (rh != null) {
        await upsertMeasure({
          domain: CLIMATE_PLAN_DOMAIN,
          measure: CLIMATE_PLAN_MEASURE_RH,
          value: rh,
          fromTs,
          toTs,
          segmentId: editRhId.value,
        })
      }
    } else {
      const ec = parseRequiredNumber(ecValue.value, 'EC-Ziel')
      if (ec == null) return
      const ph = parseRequiredNumber(phValue.value, 'pH-Ziel')
      if (ph == null) return
      await upsertMeasure({
        domain: TANK_PLAN_DOMAIN,
        measure: TANK_PLAN_MEASURE_EC,
        value: ec,
        fromTs,
        toTs,
        segmentId: editEcId.value,
      })
      await upsertMeasure({
        domain: TANK_PLAN_DOMAIN,
        measure: TANK_PLAN_MEASURE_PH,
        value: ph,
        fromTs,
        toTs,
        segmentId: editPhId.value,
      })
    }
    toast.success(editingKey.value ? 'Ziel aktualisiert' : 'Ziel angelegt')
    editorOpen.value = false
    nowTick.value = Date.now()
    emit('changed')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Speichern fehlgeschlagen')
  }
}

async function onDelete(row: EcPhStaffel): Promise<void> {
  const ok = await uiStore.confirm({
    title: 'Ziel-Staffel löschen?',
    message: `${formatStaffelRange(row.fromTs, row.toTs)} — EC und pH für diesen Zeitraum werden aus dem Plan entfernt.`,
    variant: 'danger',
    confirmText: 'Löschen',
  })
  if (!ok) return
  try {
    if (row.ec) await planStore.deleteSegment(row.ec.id)
    if (row.ph) await planStore.deleteSegment(row.ph.id)
    toast.success('Ziel gelöscht')
    nowTick.value = Date.now()
    emit('changed')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Löschen fehlgeschlagen')
  }
}

async function onDeleteClimate(row: ClimateStaffel): Promise<void> {
  const ok = await uiStore.confirm({
    title: 'Klima-Ziel löschen?',
    message: `${formatStaffelRange(row.fromTs, row.toTs)} — Temperatur und Luftfeuchte für diesen Zeitraum werden aus dem Plan entfernt.`,
    variant: 'danger',
    confirmText: 'Löschen',
  })
  if (!ok) return
  try {
    if (row.temperature) await planStore.deleteSegment(row.temperature.id)
    if (row.humidity) await planStore.deleteSegment(row.humidity.id)
    toast.success('Ziel gelöscht')
    nowTick.value = Date.now()
    emit('changed')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Löschen fehlgeschlagen')
  }
}

/**
 * AUT-1344: write System-EC as plan_segment target_ec via the same store path
 * as the editor form (no second write API). Caller owns ConfirmDialog.
 */
async function applySystemEcAsTarget(ecUsCm: number): Promise<void> {
  if (!props.zoneId) {
    throw new Error('Keine Zone — Ziel kann nicht gespeichert werden.')
  }
  if (!Number.isFinite(ecUsCm)) {
    throw new Error('System-EC fehlt — Ziel kann nicht übernommen werden.')
  }
  const clamped = clampPlanMeasureValue(TANK_PLAN_MEASURE_EC, ecUsCm)
  nowTick.value = Date.now()
  const active = findActiveEcPhStaffel(staffeln.value, nowTick.value)

  if (active?.ec) {
    await planStore.updateSegment(active.ec.id, {
      value: clamped,
      from_ts: active.fromTs,
      to_ts: active.toTs,
      measure: TANK_PLAN_MEASURE_EC,
    })
  } else if (active) {
    await planStore.createSegment({
      zone_id: props.zoneId,
      domain: TANK_PLAN_DOMAIN,
      measure: TANK_PLAN_MEASURE_EC,
      value: clamped,
      from_ts: active.fromTs,
      to_ts: active.toTs,
      interp: 'step',
      status: 'planned',
      phase_ref: null,
    })
  } else {
    const fromTs = dateInputToIsoStart(isoToDateInput(new Date().toISOString()))
    if (!fromTs) {
      throw new Error('Ungültiges Datum — Ziel kann nicht angelegt werden.')
    }
    await planStore.createSegment({
      zone_id: props.zoneId,
      domain: TANK_PLAN_DOMAIN,
      measure: TANK_PLAN_MEASURE_EC,
      value: clamped,
      from_ts: fromTs,
      to_ts: null,
      interp: 'step',
      status: 'planned',
      phase_ref: null,
    })
  }
  nowTick.value = Date.now()
  emit('changed')
}

function climateVpdLabel(row: ClimateStaffel | null): string {
  if (!row) return 'VPD nicht berechenbar (Temperatur- und Feuchte-Ziel fehlen)'
  const t = row.temperature?.value
  const h = row.humidity?.value
  if (t == null && h == null) {
    return 'VPD nicht berechenbar (Temperatur- und Feuchte-Ziel fehlen)'
  }
  if (t == null) return 'VPD nicht berechenbar (Temperatur-Ziel fehlt)'
  if (h == null) return 'VPD nicht berechenbar (Feuchte-Ziel fehlt)'
  const vpd = calculateVpdKpa(t, h)
  if (vpd == null) return 'VPD nicht berechenbar (Werte außerhalb Bereich)'
  return `VPD ${vpd.toFixed(2)} kPa`
}

defineExpose({
  applySystemEcAsTarget,
  reload: loadSegments,
})
</script>

<template>
  <section class="ecph-editor" aria-labelledby="ecph-editor-heading">
    <div class="ecph-editor__head">
      <h2 id="ecph-editor-heading" class="ecph-editor__title">
        <Target class="w-4 h-4 shrink-0" aria-hidden="true" />
        <span>EC- &amp; pH-Ziele</span>
      </h2>
      <BaseButton
        type="button"
        variant="primary"
        size="sm"
        aria-label="EC und pH Ziel anlegen"
        @click="openCreate('nutrient')"
      >
        <Plus class="w-4 h-4" aria-hidden="true" />
        <span>Ziel</span>
      </BaseButton>
    </div>

    <p class="ecph-editor__hint">
      Ab einem Datum gelten EC und pH für
      {{ zoneName || 'diese Zone' }} (Plan, Nährlösung).
      Offen = bis auf Weiteres.
    </p>

    <!-- Anzeige = Wirkung (@now) -->
    <div
      class="ecph-now"
      :class="{ 'ecph-now--empty': !activeStaffel }"
      role="status"
      aria-live="polite"
    >
      <span class="ecph-now__label">Aktuell gültig</span>
      <template v-if="activeStaffel">
        <p class="ecph-now__range">
          {{ formatStaffelRange(activeStaffel.fromTs, activeStaffel.toTs) }}
        </p>
        <p class="ecph-now__values">
          <span>
            EC {{ formatMeasureValue(activeStaffel.ec?.value) }}
            {{ ecInputSpec.unit }}
          </span>
          <span aria-hidden="true">·</span>
          <span>pH {{ formatMeasureValue(activeStaffel.ph?.value) }}</span>
        </p>
      </template>
      <p v-else class="ecph-now__empty-text">
        Kein Plan-Segment für jetzt — Ist/Soll zeigt kein Soll, bis ein Ziel gilt.
      </p>
    </div>

    <div v-if="planStore.isLoading" class="ecph-editor__state">Lade Ziele…</div>
    <div
      v-else-if="planStore.error"
      class="ecph-editor__state ecph-editor__state--error"
      role="alert"
    >
      {{ planStore.error }}
    </div>
    <EmptyState
      v-else-if="staffeln.length === 0"
      :icon="Target"
      title="Noch kein EC/pH-Ziel"
      description="Lege ein Ziel an, z. B. „ab heute EC 1400 µS/cm, pH 6.0“. Die Dosier-Regel und Ist/Soll lesen denselben Plan."
      action-text="Ziel anlegen"
      @action="openCreate('nutrient')"
    />
    <ul v-else class="ecph-list" aria-label="Gestaffelte EC und pH Ziele">
      <li
        v-for="row in staffeln"
        :key="row.key"
        class="ecph-list__item"
        :class="{ 'ecph-list__item--active': activeStaffel?.key === row.key }"
      >
        <div class="ecph-list__main">
          <span class="ecph-list__range">
            {{ formatStaffelRange(row.fromTs, row.toTs) }}
          </span>
          <span class="ecph-list__values">
            EC {{ formatMeasureValue(row.ec?.value) }} {{ ecInputSpec.unit }}
            · pH {{ formatMeasureValue(row.ph?.value) }}
          </span>
          <span
            v-if="activeStaffel?.key === row.key"
            class="ecph-list__badge"
          >jetzt</span>
        </div>
        <div class="ecph-list__actions">
          <button
            type="button"
            class="ecph-icon-btn"
            :aria-label="`Ziel ${formatStaffelRange(row.fromTs, row.toTs)} bearbeiten`"
            @click="openEdit(row)"
          >
            <Pencil class="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="ecph-icon-btn ecph-icon-btn--danger"
            :aria-label="`Ziel ${formatStaffelRange(row.fromTs, row.toTs)} löschen`"
            @click="onDelete(row)"
          >
            <Trash2 class="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </li>
    </ul>

    <div class="ecph-editor__head">
      <h2 id="climate-editor-heading" class="ecph-editor__title">
        <Thermometer class="w-4 h-4 shrink-0" aria-hidden="true" />
        <span>Temperatur- &amp; Feuchte-Ziele</span>
      </h2>
      <BaseButton
        type="button"
        variant="primary"
        size="sm"
        aria-label="Temperatur und Luftfeuchte Ziel anlegen"
        @click="openCreate('climate')"
      >
        <Plus class="w-4 h-4" aria-hidden="true" />
        <span>Ziel</span>
      </BaseButton>
    </div>

    <p class="ecph-editor__hint">
      Ab einem Datum gelten Temperatur und Luftfeuchte für
      {{ zoneName || 'diese Zone' }} (Plan, Klima).
      VPD folgt daraus — nicht als eigene Spalte. Offen = bis auf Weiteres.
    </p>

    <div
      class="ecph-now"
      :class="{ 'ecph-now--empty': !activeClimateStaffel }"
      role="status"
      aria-live="polite"
    >
      <span class="ecph-now__label">Aktuell gültig</span>
      <template v-if="activeClimateStaffel">
        <p class="ecph-now__range">
          {{ formatStaffelRange(activeClimateStaffel.fromTs, activeClimateStaffel.toTs) }}
        </p>
        <p class="ecph-now__values">
          <span>
            T {{ formatMeasureValue(activeClimateStaffel.temperature?.value) }}
            {{ tempInputSpec.unit }}
          </span>
          <span aria-hidden="true">·</span>
          <span>
            RH {{ formatMeasureValue(activeClimateStaffel.humidity?.value) }}
            {{ rhInputSpec.unit }}
          </span>
        </p>
        <p class="ecph-now__empty-text">{{ climateVpdLabel(activeClimateStaffel) }}</p>
      </template>
      <p v-else class="ecph-now__empty-text">
        Kein Klima-Segment für jetzt — Timeline zeigt kein T/RH-Soll, bis ein Ziel gilt.
      </p>
    </div>

    <EmptyState
      v-if="!planStore.isLoading && !planStore.error && climateStaffeln.length === 0"
      :icon="Thermometer"
      title="Noch kein Temperatur/Feuchte-Ziel"
      description="Lege ein Ziel an, z. B. „ab heute 24 °C, 60 %“. VPD erscheint nur, wenn beide Werte im gleichen Zeitraum liegen."
      action-text="Ziel anlegen"
      @action="openCreate('climate')"
    />
    <ul
      v-else-if="!planStore.isLoading && !planStore.error && climateStaffeln.length > 0"
      class="ecph-list"
      aria-label="Gestaffelte Temperatur und Feuchte Ziele"
    >
      <li
        v-for="row in climateStaffeln"
        :key="row.key"
        class="ecph-list__item"
        :class="{ 'ecph-list__item--active': activeClimateStaffel?.key === row.key }"
      >
        <div class="ecph-list__main">
          <span class="ecph-list__range">
            {{ formatStaffelRange(row.fromTs, row.toTs) }}
          </span>
          <span class="ecph-list__values">
            T {{ formatMeasureValue(row.temperature?.value) }} {{ tempInputSpec.unit }}
            · RH {{ formatMeasureValue(row.humidity?.value) }} {{ rhInputSpec.unit }}
          </span>
          <span class="ecph-list__values">{{ climateVpdLabel(row) }}</span>
          <span
            v-if="activeClimateStaffel?.key === row.key"
            class="ecph-list__badge"
          >jetzt</span>
        </div>
        <div class="ecph-list__actions">
          <button
            type="button"
            class="ecph-icon-btn"
            :aria-label="`Klima-Ziel ${formatStaffelRange(row.fromTs, row.toTs)} bearbeiten`"
            @click="openEditClimate(row)"
          >
            <Pencil class="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="ecph-icon-btn ecph-icon-btn--danger"
            :aria-label="`Klima-Ziel ${formatStaffelRange(row.fromTs, row.toTs)} löschen`"
            @click="onDeleteClimate(row)"
          >
            <Trash2 class="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </li>
    </ul>

    <BaseModal
      :open="editorOpen"
      :title="modalTitle"
      max-width="plan-editor-modal-max"
      @update:open="editorOpen = $event"
    >
      <form class="ecph-form" @submit.prevent="onSave">
        <label class="ecph-form__label">
          Von
          <input
            v-model="fromDate"
            type="date"
            class="ecph-form__date"
            required
            aria-label="Gültig ab Datum"
          />
        </label>
        <label class="ecph-form__label">
          Bis (optional)
          <input
            v-model="toDate"
            type="date"
            class="ecph-form__date"
            aria-label="Gültig bis Datum, leer = offen"
          />
        </label>
        <template v-if="isClimate">
          <BaseInput
            v-model="tempValue"
            type="text"
            inputmode="decimal"
            parse-locale-decimal
            :label="`Temperatur-Ziel (${tempInputSpec.unit})`"
            :min="tempInputSpec.min"
            :max="tempInputSpec.max"
            :step="tempInputSpec.step"
            placeholder="z. B. 24"
            aria-label="Temperatur Ziel in Grad Celsius"
          />
          <BaseInput
            v-model="rhValue"
            type="text"
            inputmode="decimal"
            parse-locale-decimal
            :label="`Feuchte-Ziel (${rhInputSpec.unit})`"
            :min="rhInputSpec.min"
            :max="rhInputSpec.max"
            :step="rhInputSpec.step"
            placeholder="z. B. 60"
            aria-label="Luftfeuchte Ziel in Prozent"
          />
          <p class="ecph-form__vpd" role="status">{{ formVpdLabel }}</p>
        </template>
        <template v-else>
          <BaseInput
            v-model="ecValue"
            type="text"
            inputmode="decimal"
            parse-locale-decimal
            :label="`EC-Ziel (${ecInputSpec.unit})`"
            :min="ecInputSpec.min"
            :max="ecInputSpec.max"
            :step="ecInputSpec.step"
            placeholder="z. B. 1400"
            required
            aria-label="EC Ziel in Mikrosiemens pro Zentimeter"
          />
          <BaseInput
            v-model="phValue"
            type="text"
            inputmode="decimal"
            parse-locale-decimal
            label="pH-Ziel"
            :min="phInputSpec.min"
            :max="phInputSpec.max"
            :step="phInputSpec.step"
            placeholder="z. B. 5,9"
            required
            aria-label="pH Ziel"
          />
          <BaseSelect
            id="ecph-phase-ref"
            v-model="phaseRef"
            :options="PHASE_SELECT_OPTIONS"
            label="Nährstoffphase"
            helper="Bestimmt das Stammlösungs-Rezept (dose_role × Phase). Keine Timing-/Umstell-Logik."
          />
        </template>
        <p v-if="formError" class="ecph-form__error" role="alert">{{ formError }}</p>
        <div class="ecph-form__actions">
          <BaseButton type="button" variant="ghost" @click="closeEditor">
            Abbrechen
          </BaseButton>
          <BaseButton
            type="submit"
            variant="primary"
            :loading="planStore.isMutating"
            :disabled="planStore.isMutating"
          >
            Speichern
          </BaseButton>
        </div>
      </form>
    </BaseModal>
  </section>
</template>

<style scoped>
.ecph-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  max-width: 100%;
}

.ecph-editor__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-width: 0;
}

.ecph-editor__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  min-width: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.ecph-editor__hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
  max-width: 100%;
}

.ecph-now {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-md);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.ecph-now--empty {
  border-color: var(--glass-border);
}

.ecph-now__label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.ecph-now__range,
.ecph-now__values,
.ecph-now__empty-text {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  word-break: break-word;
}

.ecph-now__values {
  font-weight: 600;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-2);
}

.ecph-now__empty-text {
  color: var(--color-text-secondary);
}

.ecph-editor__state {
  padding: var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.ecph-editor__state--error {
  color: var(--color-danger);
}

.ecph-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.ecph-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.ecph-list__item--active {
  border-color: var(--color-accent);
}

.ecph-list__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}

.ecph-list__range {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ecph-list__values {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ecph-list__badge {
  align-self: flex-start;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-accent);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ecph-list__actions {
  display: flex;
  gap: var(--space-1);
  flex-shrink: 0;
}

.ecph-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.ecph-icon-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.ecph-icon-btn--danger:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.ecph-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ecph-form__label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.ecph-form__date {
  width: 100%;
  max-width: 100%;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  min-height: 38px;
  box-sizing: border-box;
}

.ecph-form__error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-danger);
}

.ecph-form__vpd {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.ecph-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-2);
  flex-wrap: wrap;
}
</style>

<!--
  BaseModal teleports to body; scoped CSS cannot beat forms.css
  `.modal-content { max-width: 28rem }`. Same compound-selector pattern
  as ConfigWizardModal `.cwm-modal-max` (AUT-1529).
-->
<style>
.modal-content.plan-editor-modal-max {
  max-width: min(94vw, 40rem);
}
</style>
