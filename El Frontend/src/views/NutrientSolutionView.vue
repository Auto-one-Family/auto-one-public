<script setup lang="ts">
/**
 * NutrientSolutionView — Nährlösungs-Tab
 * (AUT-1338 P4 + AUT-1339 P5 + AUT-1340 P6 + AUT-1344 P7 + AUT-1387 P-B + AUT-1388 P-E·FE)
 *
 * Top-level Heimat für Tank-Bausteine:
 *  - Zone-scoped Tank-Liste (kanonisch: useTankStore / GET /v1/tanks)
 *  - Detail: Kopf + Geräte + TankIstSollPanel + EC/pH-Plan-Editor (P6)
 *    + Rezept-Wochenraster (AUT-1386/1387, gewandert aus PlanTimelineView)
 *    + Stock-Ansetz-Rechner (AUT-1361/1387, gewandert aus ActuatorConfigPanel)
 *    + Salz-Bibliothek (AUT-1422 B5)
 *    + Salzrechner-Panel (P7)
 *
 * Reuse: Pflanzenview-Muster; TankIstSollPanel (AUT-1225); deviceIdsForTank (tank_id);
 * planSegments store (AUT-1232/1235) — Plan bleibt SSOT, kein Tank-Zielfeld.
 * Route: /nutrient-solution[+/:tankId]
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronRight, Cpu, Droplets, Pencil, Plus } from 'lucide-vue-next'
import { tanksApi } from '@/api/tanks'
import { useTankStore } from '@/shared/stores/tank.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { usePlanSegmentsStore } from '@/shared/stores/planSegments.store'
import { useEspStore } from '@/stores/esp'
import { TANK_OPERATION_MODE_LABELS } from '@/components/plants/tankLabels'
import TankCreateModal from '@/components/plants/TankCreateModal.vue'
import TankEditModal from '@/components/plants/TankEditModal.vue'
import TankIstSollPanel from '@/components/plants/TankIstSollPanel.vue'
import TankEcPhPlanEditor from '@/components/plants/TankEcPhPlanEditor.vue'
import TankSaltCalculatorPanel from '@/components/plants/TankSaltCalculatorPanel.vue'
import TankStockMixRecipePanel from '@/components/plants/TankStockMixRecipePanel.vue'
import SaltCompositionLibraryPanel from '@/components/plants/SaltCompositionLibraryPanel.vue'
import PlanRecipeWeekGrid from '@/components/plan-timeline/PlanRecipeWeekGrid.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import { useToast } from '@/composables/useToast'
import { deviceIdsForTank } from '@/utils/zoneTankEcPh'
import type { Tank, TankVolumeResponse } from '@/types'
import { createLogger } from '@/utils/logger'

const logger = createLogger('NutrientSolutionView')
const VOLUME_POLL_MS = 30_000

interface TankMemberDevice {
  id: string
  name: string
}

const route = useRoute()
const router = useRouter()
const tankStore = useTankStore()
const zoneStore = useZoneStore()
const planStore = usePlanSegmentsStore()
const espStore = useEspStore()
const toast = useToast()

const selectedZoneId = ref('')
const showTankCreateModal = ref(false)
/** AUT-1388: Nennwert + Frischwasser-EC/pH nachträglich. */
const showTankEditModal = ref(false)
/** Bump quiet-refetches Soll in TankIstSollPanel after plan edits (AUT-1358, no remount). */
const istSollRefreshKey = ref(0)
/** P6 editor — System-EC übernehmen uses the same plan_segment write path. */
const planEditorRef = ref<InstanceType<typeof TankEcPhPlanEditor> | null>(null)
const saltCalculatorRef = ref<InstanceType<typeof TankSaltCalculatorPanel> | null>(null)

/** AUT-1377: running volume (Anker±Flow) — never confuse with nominal. */
const volumeTruth = ref<TankVolumeResponse | null>(null)
const volumeError = ref<string | null>(null)
let volumePollTimer: ReturnType<typeof setInterval> | null = null
let volumeFetchSeq = 0

const zoneOptions = computed(() => zoneStore.activeZones)

const tankIdParam = computed(() => {
  const raw = route.params.tankId
  return typeof raw === 'string' && raw.length > 0 ? raw : null
})

const isDetailRoute = computed(() => tankIdParam.value !== null)

/** Tanks of the selected („current“) zone — sorted by name via store helper. */
const zoneTanks = computed((): Tank[] => {
  if (!selectedZoneId.value) return []
  return tankStore.tanksForZone(selectedZoneId.value)
})

const selectedTank = computed((): Tank | null => {
  const id = tankIdParam.value
  if (!id) return null
  return tankStore.tanks.find((t) => t.id === id) ?? null
})

const selectedZoneName = computed(() => {
  if (selectedTank.value?.zone_id) {
    const byTank = zoneOptions.value.find((z) => z.zone_id === selectedTank.value!.zone_id)
    if (byTank) return byTank.name
  }
  const zone = zoneOptions.value.find((z) => z.zone_id === selectedZoneId.value)
  return zone?.name ?? selectedZoneId.value
})

/**
 * Membership via esp_devices.tank_id (AUT-1223) — same source as Messpunkt-Linse /
 * TankIstSollPanel assigned devices. Names primary; id only if no name.
 */
const memberDevices = computed((): TankMemberDevice[] => {
  const tank = selectedTank.value
  if (!tank) return []
  const ids = deviceIdsForTank(espStore.devices, tank.id)
  return ids
    .map((id) => {
      const device = espStore.devices.find((d) => d.device_id === id || d.esp_id === id)
      const name = device?.name?.trim()
      return { id, name: name && name.length > 0 ? name : id }
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'de'))
})

function formatNominalVolume(tank: Tank): string {
  const vol = tank.nominal_volume_l
  if (typeof vol === 'number' && Number.isFinite(vol)) {
    return `Nennwert: ${vol.toLocaleString('de-DE', { maximumFractionDigits: 1 })} L`
  }
  return 'Nennwert: nicht konfiguriert'
}

function formatMode(tank: Tank): string {
  return TANK_OPERATION_MODE_LABELS[tank.operation_mode] ?? '—'
}

/** List-row secondary metric: Nennwert preferred (not Ist), else mode. */
function formatVolumeMetric(tank: Tank): string {
  const vol = formatNominalVolume(tank)
  if (vol !== 'Nennwert: nicht konfiguriert') return vol
  return formatMode(tank)
}

/** Ist = V_real (Anker±Flow) — never show nominal as Ist. */
const runningVolumeDisplay = computed((): string => {
  const v = volumeTruth.value?.volume_l
  if (typeof v === 'number' && Number.isFinite(v)) {
    return `${v.toLocaleString('de-DE', { maximumFractionDigits: 1 })} L (gemessen)`
  }
  return '— (gemessen)'
})

function formatFreshWaterSummary(tank: Tank): string {
  const ec = tank.fresh_water_ec_us_cm
  const ph = tank.fresh_water_ph
  const ecPart =
    typeof ec === 'number' && Number.isFinite(ec)
      ? `FW-EC ${ec.toLocaleString('de-DE', { maximumFractionDigits: 0 })} µS/cm`
      : 'FW-EC nicht konfiguriert'
  const phPart =
    typeof ph === 'number' && Number.isFinite(ph)
      ? `FW-pH ${ph.toLocaleString('de-DE', { maximumFractionDigits: 1 })}`
      : 'FW-pH nicht konfiguriert'
  return `${ecPart} · ${phPart}`
}

const hasDrainLimitation = computed(
  () => volumeTruth.value?.limitations?.includes('drain_not_in_flow') ?? false,
)

async function loadVolumeTruth(tankId: string): Promise<void> {
  const seq = ++volumeFetchSeq
  try {
    const data = await tanksApi.getVolume(tankId)
    if (seq !== volumeFetchSeq) return
    volumeTruth.value = data
    volumeError.value = null
  } catch (e) {
    if (seq !== volumeFetchSeq) return
    volumeTruth.value = null
    // AUT-1388: no raw 404/route noise — Ist stays „—“; soft operator message
    volumeError.value =
      'Ist-Volumen gerade nicht verfügbar (Anker ± Flow). Nennwert ist davon unabhängig.'
    logger.warn('AUT-1377 volume fetch failed', e)
  }
}

function stopVolumePoll(): void {
  if (volumePollTimer != null) {
    clearInterval(volumePollTimer)
    volumePollTimer = null
  }
}

function startVolumePoll(tankId: string): void {
  stopVolumePoll()
  void loadVolumeTruth(tankId)
  volumePollTimer = setInterval(() => {
    void loadVolumeTruth(tankId)
  }, VOLUME_POLL_MS)
}

function ensureDefaultZone(): void {
  if (selectedZoneId.value) return
  const first = zoneOptions.value[0]
  if (first) selectedZoneId.value = first.zone_id
}

function openTank(tank: Tank): void {
  void router.push({ name: 'nutrient-solution-tank', params: { tankId: tank.id } })
}

function backToList(): void {
  void router.push({ name: 'nutrient-solution' })
}

function openTankCreateModal(): void {
  showTankCreateModal.value = true
}

function openTankEditModal(): void {
  showTankEditModal.value = true
}

async function onTankCreated(tankId: string): Promise<void> {
  showTankCreateModal.value = false
  try {
    await tankStore.fetchTanks()
  } catch {
    // store.error already set
  }
  toast.success('Tank angelegt')
  const created = tankStore.tanks.find((t) => t.id === tankId)
  if (created?.zone_id) {
    selectedZoneId.value = created.zone_id
  }
}

async function onTankEdited(_tank: Tank): Promise<void> {
  showTankEditModal.value = false
  try {
    await tankStore.fetchTanks()
  } catch {
    // store.error already set
  }
  void saltCalculatorRef.value?.reload()
}

/** AUT-1344: System-EC → plan_segment target_ec via P6 editor (no second write path). */
async function onApplySystemEc(ecUsCm: number): Promise<void> {
  try {
    await planEditorRef.value?.applySystemEcAsTarget(ecUsCm)
    toast.success('Gemessenen EC als Ziel übernommen')
    istSollRefreshKey.value += 1
    await saltCalculatorRef.value?.reload()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Übernehmen fehlgeschlagen')
  }
}

function onPlanChanged(): void {
  istSollRefreshKey.value += 1
  void saltCalculatorRef.value?.reload()
}

watch(zoneOptions, () => ensureDefaultZone(), { immediate: true })

watch(
  selectedTank,
  (tank) => {
    if (tank?.zone_id) selectedZoneId.value = tank.zone_id
    if (tank?.id) {
      startVolumePoll(tank.id)
    } else {
      stopVolumePoll()
      volumeTruth.value = null
      volumeError.value = null
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
    void zoneStore.fetchZoneEntities().then(() => ensureDefaultZone())
  } else {
    ensureDefaultZone()
  }
  // AUT-1220: Server-SSOT — immer frisch laden (localStorage nur Cache)
  void tankStore.fetchTanks()
  if (espStore.devices.length === 0) {
    void espStore.fetchAll()
  }
})

onUnmounted(() => {
  volumeFetchSeq += 1
  stopVolumePoll()
})
</script>

<template>
  <div class="nutrient-view">
    <!-- ── Detail (AUT-1339 P5) ── -->
    <template v-if="isDetailRoute">
      <div class="nutrient-header">
        <button
          type="button"
          class="nutrient-btn nutrient-btn--ghost"
          aria-label="Zurück zur Tank-Liste"
          @click="backToList"
        >
          <ArrowLeft class="w-4 h-4" aria-hidden="true" />
          <span>Zurück</span>
        </button>
      </div>

      <div v-if="tankStore.isLoading" class="nutrient-state">
        Lade Tank…
      </div>
      <div v-else-if="selectedTank" class="nutrient-detail">
        <!-- Kopf: Ist = V_real (Anker±Flow) klar getrennt vom Nennwert (AUT-1388) -->
        <header class="nutrient-detail__head">
          <div class="nutrient-detail__icon" aria-hidden="true">
            <Droplets class="w-7 h-7" />
          </div>
          <div class="nutrient-detail__head-text">
            <div class="nutrient-detail__title-row">
              <h1 class="nutrient-detail__title">
                {{ selectedTank.name }}
              </h1>
              <button
                type="button"
                class="nutrient-btn nutrient-btn--ghost nutrient-detail__edit"
                aria-label="Tank bearbeiten: Nennwert und Frischwasser"
                title="Nennwert und Frischwasser bearbeiten"
                @click="openTankEditModal"
              >
                <Pencil class="w-4 h-4" aria-hidden="true" />
                <span>Bearbeiten</span>
              </button>
            </div>
            <p class="nutrient-detail__metrics" aria-label="Tankvolumen Ist gemessen und Nennwert">
              <span title="Laufendes Volumen V_real: 20-Liter-Anker ± Flow GPIO14">
                Ist: {{ runningVolumeDisplay }}
              </span>
              <span aria-hidden="true">·</span>
              <span title="Nennwert = angenommene volle Tankgröße, nicht der Ist-Füllstand">
                {{ formatNominalVolume(selectedTank) }}
              </span>
              <span aria-hidden="true">·</span>
              <span>{{ formatMode(selectedTank) }}</span>
              <template v-if="selectedZoneName">
                <span aria-hidden="true">·</span>
                <span class="nutrient-detail__zone">{{ selectedZoneName }}</span>
              </template>
            </p>
            <p
              class="nutrient-detail__fw"
              aria-label="Frischwasser-Kennwerte"
              title="Frischwasser-EC/pH — eine Stelle, bearbeitbar über Bearbeiten"
            >
              {{ formatFreshWaterSummary(selectedTank) }}
            </p>
            <p
              v-if="hasDrainLimitation"
              class="nutrient-detail__volume-limit"
              title="Owner: AUT-1286 — Flow erfasst nur Zulauf"
            >
              Entnahmen (Drain-to-Waste) sind im Flow nicht erfasst — Ist ohne Abfluss-Korrektur.
            </p>
            <p v-else-if="volumeError" class="nutrient-detail__volume-limit">
              {{ volumeError }}
            </p>
          </div>
        </header>

        <TankEditModal
          :open="showTankEditModal"
          :tank="selectedTank"
          @close="showTankEditModal = false"
          @saved="onTankEdited"
        />

        <!-- Geräte-Mitglieder (Namen primär, esp_devices.tank_id) -->
        <section class="nutrient-members" aria-labelledby="nutrient-members-heading">
          <h2 id="nutrient-members-heading" class="nutrient-members__title">
            <Cpu class="w-4 h-4 shrink-0" aria-hidden="true" />
            <span>Geräte</span>
          </h2>
          <EmptyState
            v-if="memberDevices.length === 0"
            :icon="Cpu"
            title="Kein Gerät zugeordnet"
            description="Ordne diesem Tank mindestens ein Gerät zu (Wasser-Domain / Tank-Zuordnung), damit Ist-Werte und Mitglieder hier erscheinen."
            :show-action="false"
          />
          <ul v-else class="nutrient-members__list" aria-label="Geräte-Mitglieder des Tanks">
            <li
              v-for="device in memberDevices"
              :key="device.id"
              class="nutrient-members__item"
            >
              <span class="nutrient-members__name">{{ device.name }}</span>
            </li>
          </ul>
        </section>

        <!-- Ist/Soll + Delta — wiederverwendet (AUT-1225) -->
        <section class="nutrient-ist-soll" aria-label="Ist und Soll EC und pH">
          <TankIstSollPanel
            :tank-id="selectedTank.id"
            :tank-name="selectedTank.name"
            :refresh-token="istSollRefreshKey"
          />
        </section>

        <!-- EC/pH-Plan-Editor (AUT-1340) — schreibt plan_segments, Plan = SSOT -->
        <TankEcPhPlanEditor
          ref="planEditorRef"
          :zone-id="selectedTank.zone_id"
          :zone-name="selectedZoneName"
          @changed="onPlanChanged"
        />

        <!-- Rezeptur nach Plansegmenten (AUT-1386/1421) — Spalten = EC/pH-Staffeln -->
        <PlanRecipeWeekGrid
          :segments="planStore.segments"
          :zone-id="selectedTank.zone_id"
        />

        <!-- Stock-Ansetz-Rechner (AUT-1361/1387) — gewandert aus ActuatorConfigPanel -->
        <TankStockMixRecipePanel
          :tank-id="selectedTank.id"
          :tank-name="selectedTank.name"
        />

        <!-- Salz-Referenzbibliothek (AUT-1422 B5) -->
        <SaltCompositionLibraryPanel />

        <!-- Salzrechner (AUT-1344) — Erwartung + System-EC → P6-Ziel -->
        <TankSaltCalculatorPanel
          ref="saltCalculatorRef"
          :tank-id="selectedTank.id"
          :tank-name="selectedTank.name"
          :nominal-volume-l="selectedTank.nominal_volume_l"
          @apply-system-ec="onApplySystemEc"
          @changed="istSollRefreshKey += 1"
        />
      </div>
      <EmptyState
        v-else
        :icon="Droplets"
        title="Tank nicht gefunden"
        description="Dieser Tank ist in der aktuellen Liste nicht enthalten. Zurück zur Übersicht und erneut wählen."
        action-text="Zur Tank-Liste"
        @action="backToList"
      />
    </template>

    <!-- ── Listen-Shell ── -->
    <template v-else>
      <div class="nutrient-header">
        <h1 class="nutrient-header__title">
          <Droplets class="w-6 h-6 shrink-0" aria-hidden="true" />
          <span>Nährlösung</span>
        </h1>
        <button
          type="button"
          class="nutrient-btn nutrient-btn--primary"
          aria-label="Tank anlegen"
          @click="openTankCreateModal"
        >
          <Plus class="w-4 h-4" aria-hidden="true" />
          <span>Tank</span>
        </button>
      </div>

      <div class="nutrient-filters">
        <label class="nutrient-filter">
          <span class="nutrient-filter__label">Zone</span>
          <select
            v-model="selectedZoneId"
            class="nutrient-filter__input"
            aria-label="Zone wählen"
          >
            <option
              v-for="zone in zoneOptions"
              :key="zone.zone_id"
              :value="zone.zone_id"
            >
              {{ zone.name }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="tankStore.isLoading" class="nutrient-state">
        Lade Tanks…
      </div>
      <div v-else-if="tankStore.error" class="nutrient-state nutrient-state--error">
        {{ tankStore.error }}
      </div>
      <EmptyState
        v-else-if="!selectedZoneId"
        :icon="Droplets"
        title="Keine Zone verfügbar"
        description="Lege zuerst eine Zone an, bevor du Nährlösungs-Tanks zuordnen kannst."
        :show-action="false"
      />
      <EmptyState
        v-else-if="zoneTanks.length === 0"
        :icon="Droplets"
        title="Noch kein Tank in dieser Zone"
        :description="`In „${selectedZoneName}“ ist noch kein Nährlösungs-Tank angelegt. Lege einen Tank an, um hier zu starten.`"
        action-text="Tank anlegen"
        @action="openTankCreateModal"
      />
      <ul v-else class="nutrient-list" aria-label="Tanks der Zone">
        <li v-for="tank in zoneTanks" :key="tank.id">
          <button
            type="button"
            class="nutrient-list__item"
            :aria-label="`Tank ${tank.name} öffnen`"
            @click="openTank(tank)"
          >
            <div class="nutrient-list__main">
              <span class="nutrient-list__name">{{ tank.name }}</span>
              <span class="nutrient-list__metric">{{ formatVolumeMetric(tank) }}</span>
            </div>
            <ChevronRight class="nutrient-list__chevron" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </template>

    <TankCreateModal
      :open="showTankCreateModal"
      @close="showTankCreateModal = false"
      @created="onTankCreated"
    />
  </div>
</template>

<style scoped>
.nutrient-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  height: 100%;
  max-width: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  padding: var(--space-3);
  box-sizing: border-box;
}

.nutrient-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  min-width: 0;
}

.nutrient-header__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.nutrient-header__title span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nutrient-filters {
  display: flex;
  gap: var(--space-3);
  align-items: end;
  flex-wrap: wrap;
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  min-width: 0;
}

.nutrient-filter {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1 1 100%;
}

@media (min-width: 480px) {
  .nutrient-filter {
    flex: 1 1 220px;
    max-width: 320px;
  }
}

.nutrient-filter__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.nutrient-filter__input {
  width: 100%;
  max-width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  min-height: 38px;
  box-sizing: border-box;
}

.nutrient-filter__input:focus {
  border-color: var(--color-accent);
}

.nutrient-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 38px;
  min-width: 44px;
  border: 1px solid transparent;
}

.nutrient-btn--primary {
  background: var(--color-accent);
  color: white;
}

.nutrient-btn--primary:hover {
  background: var(--color-accent-bright);
}

.nutrient-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.nutrient-btn--ghost:hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.nutrient-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.nutrient-state--error {
  color: var(--color-danger);
}

.nutrient-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.nutrient-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  width: 100%;
  max-width: 100%;
  min-width: 0;
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast);
  box-sizing: border-box;
}

.nutrient-list__item:hover {
  border-color: var(--color-accent);
  background: rgba(255, 255, 255, 0.03);
}

.nutrient-list__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}

.nutrient-list__name {
  font-size: var(--text-base);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nutrient-list__metric {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nutrient-list__chevron {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
  color: var(--color-text-muted);
}

.nutrient-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  max-width: 100%;
}

.nutrient-detail__head {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  min-width: 0;
  max-width: 100%;
}

.nutrient-detail__icon {
  flex-shrink: 0;
  color: var(--color-iridescent-1);
}

.nutrient-detail__head-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}

.nutrient-detail__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  min-width: 0;
}

.nutrient-detail__title {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
  word-break: break-word;
  max-width: 100%;
  flex: 1 1 12rem;
}

.nutrient-detail__edit {
  flex-shrink: 0;
}

.nutrient-detail__metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1) var(--space-2);
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  min-width: 0;
  max-width: 100%;
}

.nutrient-detail__fw {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  max-width: 100%;
}

.nutrient-detail__zone {
  color: var(--color-text-muted);
}

.nutrient-detail__volume-limit {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  max-width: 42rem;
}

.nutrient-members {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  max-width: 100%;
}

.nutrient-members__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.nutrient-members__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.nutrient-members__item {
  display: flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-sizing: border-box;
}

.nutrient-members__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  max-width: 100%;
}

.nutrient-ist-soll {
  min-width: 0;
  max-width: 100%;
}

.nutrient-ist-soll :deep(.tank-ist-soll-panel--compact),
.nutrient-ist-soll :deep([data-variant]) {
  max-width: 100%;
}
</style>
