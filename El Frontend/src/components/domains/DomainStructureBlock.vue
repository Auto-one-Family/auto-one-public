<script setup lang="ts">
/**
 * DomainStructureBlock — read-only Mess-Struktur (AUT-1321).
 *
 * Quellen: ESP-/Zone-/Tank-Stores + useSensorSubzoneCoverage (n:m).
 * KEIN Monitor-Call, KEINE Aktoren.
 *
 * Prüfpunkt Messgröße: device.sensors[].sensor_type kommt mit espStore.fetchAll()
 * im Geräte-Store mit. Label via getSensorConfig — kein separater Config-Call und
 * kein Verschieben in den Ist-Layer nötig.
 */

import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { ESPDevice } from '@/api/esp'
import type { MockSensor, Tank } from '@/types'
import { useSensorSubzoneCoverage } from '@/composables/useSensorSubzoneCoverage'
import { getSensorConfig } from '@/utils/sensorDefaults'
import TankIstSollPanel from '@/components/plants/TankIstSollPanel.vue'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'

export interface StructureDeviceRef {
  device: ESPDevice
  deviceId: string
}

export interface DomainStructureRow {
  key: string
  deviceName: string
  deviceId: string
  zoneLabel: string
  placeLabel: string
  measureLabel: string
}

interface Props {
  domainKey: string
  devices: StructureDeviceRef[]
  tanks: Tank[]
  zoneNames: Record<string, string>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  rows: [rows: DomainStructureRow[]]
}>()

const router = useRouter()
const { listSubzonesForSensor } = useSensorSubzoneCoverage()

/** First coverage pass only — keep rows visible while refreshing. */
const initialLoading = ref(false)
const refreshing = ref(false)
const rows = ref<DomainStructureRow[]>([])
let lastDeviceKey = ''

function deviceDisplayName(device: ESPDevice): string {
  const n = device.name?.trim()
  return n || 'Gerät ohne Namen'
}

function zoneLabelFor(device: ESPDevice): string {
  const fromName = device.zone_name?.trim()
  if (fromName) return fromName
  const zid = device.zone_id
  if (zid && props.zoneNames[zid]?.trim()) return props.zoneNames[zid]
  if (zid) return 'Ort ohne Namen'
  return 'Kein Ort zugewiesen'
}

function measureLabelFor(sensor: MockSensor): string {
  const cfg = getSensorConfig(sensor.sensor_type)
  if (cfg?.label) return cfg.label
  const n = sensor.name?.trim()
  if (n) return n
  return 'Messgröße'
}

function placeName(raw: string | null | undefined): string {
  const n = raw?.trim()
  if (!n || n === 'Keine Subzone' || n === '__none__') return 'Ort ohne Namen'
  return n
}

async function rebuildRows(): Promise<void> {
  const deviceKey = props.devices.map((d) => d.deviceId).sort().join('|')
  if (deviceKey === lastDeviceKey && rows.value.length > 0) return

  const isFirstPaint = rows.value.length === 0
  if (isFirstPaint) initialLoading.value = true
  else refreshing.value = true

  try {
    const next: DomainStructureRow[] = []
    for (const { device, deviceId } of props.devices) {
      const sensors = (device.sensors ?? []) as MockSensor[]
      const zoneLabel = zoneLabelFor(device)
      const deviceName = deviceDisplayName(device)
      const subzoneRefs = (device.subzones ?? []).map((sz) => ({
        id: sz.subzone_id,
        name: placeName(sz.subzone_name),
      }))

      if (sensors.length === 0) {
        next.push({
          key: `${deviceId}-empty`,
          deviceName,
          deviceId,
          zoneLabel,
          placeLabel: 'Keine Sensoren',
          measureLabel: 'Messgröße',
        })
        continue
      }

      for (const sensor of sensors) {
        const measureLabel = measureLabelFor(sensor)
        const configId = sensor.config_id
        let places: Array<{ placeLabel: string }> = []

        if (configId && subzoneRefs.length > 0) {
          try {
            const coverage = await listSubzonesForSensor(deviceId, configId, subzoneRefs)
            places = coverage.map((c) => ({
              placeLabel: placeName(c.name),
            }))
          } catch {
            places = []
          }
        }

        if (places.length === 0) {
          // Keine n:m-Abdeckung → Ort ohne Namen (kein UUID/subzone_id anzeigen)
          places = [{ placeLabel: 'Ort ohne Namen' }]
        }

        for (const place of places) {
          next.push({
            key: `${deviceId}-${sensor.config_id ?? sensor.gpio}-${place.placeLabel}-${measureLabel}`,
            deviceName,
            deviceId,
            zoneLabel,
            placeLabel: place.placeLabel,
            measureLabel,
          })
        }
      }
    }
    rows.value = next
    lastDeviceKey = deviceKey
    emit('rows', next)
  } finally {
    initialLoading.value = false
    refreshing.value = false
  }
}

watch(
  () => props.devices.map((d) => d.deviceId).sort().join('|'),
  () => {
    void rebuildRows()
  },
  { immediate: true },
)

function openDeviceSettings(deviceId: string): void {
  void router.push({
    name: 'hardware',
    query: { openSettings: deviceId },
  })
}
</script>

<template>
  <section class="space-y-4" aria-label="Struktur">
    <!--
      Prüfpunkt Messgröße (AUT-1321): sensor_type liegt im ESP-Store (device.sensors).
      Label aus getSensorConfig — Struktur-Block ohne Monitor- und ohne Config-API-Call.
    -->
    <h4 class="text-xs font-semibold uppercase tracking-wide text-dark-300">
      Struktur
    </h4>

    <div v-if="initialLoading" class="flex items-center gap-2 text-sm text-dark-300">
      <BaseSpinner class="h-4 w-4" />
      <span>Verortung wird gelesen…</span>
    </div>

    <div
      v-else-if="refreshing"
      class="flex items-center gap-1 text-xs text-dark-400"
      aria-live="polite"
    >
      <BaseSpinner class="h-3 w-3" />
      <span>Verortung aktualisiert…</span>
    </div>

    <ul v-if="rows.length > 0" class="space-y-2">
      <li
        v-for="row in rows"
        :key="row.key"
        class="rounded-md border border-[var(--glass-border)] bg-dark-800/40 px-3 py-2 transition-opacity duration-200"
        :class="refreshing ? 'opacity-80' : 'opacity-100'"
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="text-sm font-medium text-dark-50">{{ row.deviceName }}</p>
            <p class="text-xs text-dark-300">
              {{ row.zoneLabel }} · {{ row.placeLabel }} · {{ row.measureLabel }}
            </p>
          </div>
          <button
            type="button"
            class="text-xs text-[var(--color-iridescent-1)] underline-offset-2 hover:underline"
            :aria-label="`Einstellungen für ${row.deviceName}`"
            @click="openDeviceSettings(row.deviceId)"
          >
            Einstellungen
          </button>
        </div>
      </li>
    </ul>

    <p v-else-if="!initialLoading" class="text-sm text-dark-300">
      Keine Geräte in dieser Domäne für den gewählten Zonenfilter.
    </p>

    <div v-if="domainKey === 'wasser' && tanks.length > 0" class="space-y-3 pt-2">
      <h5 class="text-xs font-semibold uppercase tracking-wide text-dark-300">
        Tanks
      </h5>
      <TankIstSollPanel
        v-for="tank in tanks"
        :key="tank.id"
        :tank-id="tank.id"
      />
    </div>
  </section>
</template>
