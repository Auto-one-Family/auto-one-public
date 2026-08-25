<script setup lang="ts">
/**
 * DomainIstLayer — lazy Ist-context for one domain (AUT-1321).
 *
 * Loads when the parent section expands. Refresh is stale-while-revalidate:
 * existing rows stay visible (no layout jump); only the first load shows a spinner.
 */

import { computed, onUnmounted, ref, watch } from 'vue'
import { zonesApi } from '@/api/zones'
import type { ZoneMonitorData } from '@/types/monitor'
import { getSensorConfig } from '@/utils/sensorDefaults'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'

interface Props {
  domainKey: string
  /** Zone IDs to load; empty = nothing to fetch */
  zoneIds: string[]
  /** Zone id → Klarname */
  zoneNames: Record<string, string>
  active: boolean
}

const props = defineProps<Props>()

interface IstRow {
  zoneLabel: string
  placeLabel: string
  measureLabel: string
  valueDisplay: string
  quality: string
}

/** First paint only — never blank the list on background refresh. */
const initialLoading = ref(false)
const refreshing = ref(false)
const error = ref<string | null>(null)
const rows = ref<IstRow[]>([])
let abortController: AbortController | null = null
let lastLoadKey = ''
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let refreshInterval: ReturnType<typeof setInterval> | null = null

/** Quiet background refresh while section is open — never blanks the list. */
const BACKGROUND_REFRESH_MS = 30_000

const loadKey = computed(() => {
  const zones = [...props.zoneIds].filter(Boolean).sort().join('|')
  return `${props.domainKey}::${zones}`
})

function measureFromType(sensorType: string, name: string | null): string {
  const cfg = getSensorConfig(sensorType)
  if (cfg?.label) return cfg.label
  if (name?.trim()) return name.trim()
  return 'Messgröße'
}

function placeLabel(subzoneName: string | null | undefined): string {
  const n = subzoneName?.trim()
  if (!n || n === 'Keine Subzone' || n === '__none__') return 'Ort ohne Namen'
  return n
}

function formatValue(raw: number | null, unit: string): string {
  if (raw === null || Number.isNaN(raw)) return '—'
  const u = unit && unit !== 'raw' ? ` ${unit}` : ''
  return `${raw}${u}`
}

function qualityLabel(quality: string): string {
  const q = quality.trim().toLowerCase()
  if (q === 'good' || q === 'excellent') return 'gut'
  if (q === 'fair') return 'mäßig'
  if (q === 'poor' || q === 'bad') return 'schlecht'
  if (q === 'stale') return 'veraltet'
  if (q === 'error') return 'Fehler'
  if (!q || q === '—') return '—'
  // Never show raw English quality tokens as primary UI copy when mapped above
  return quality
}

async function load(force = false): Promise<void> {
  if (!props.active) return

  const key = loadKey.value
  if (!force && key === lastLoadKey && rows.value.length > 0 && !error.value) {
    return
  }

  abortController?.abort()
  abortController = new AbortController()
  const signal = abortController.signal

  const sortedZones = [...props.zoneIds].filter(Boolean).sort()
  if (sortedZones.length === 0) {
    rows.value = []
    error.value = null
    initialLoading.value = false
    refreshing.value = false
    lastLoadKey = key
    return
  }

  const isFirstPaint = rows.value.length === 0
  if (isFirstPaint) {
    initialLoading.value = true
  } else {
    refreshing.value = true
  }
  // Keep previous error only until a successful refresh; don't clear rows
  if (isFirstPaint) error.value = null

  try {
    const results = await Promise.all(
      sortedZones.map(async (zoneId) => {
        const data = await zonesApi.getZoneMonitorData(
          zoneId,
          signal,
          props.domainKey,
        )
        return { zoneId, data }
      }),
    )

    if (signal.aborted) return

    const next: IstRow[] = []
    for (const { zoneId, data } of results) {
      const zoneLabel =
        props.zoneNames[zoneId]?.trim()
        || data.zone_name?.trim()
        || 'Ort ohne Namen'
      appendSensorRows(next, zoneLabel, data)
    }
    rows.value = next
    error.value = null
    lastLoadKey = key
  } catch (err) {
    if (signal.aborted) return
    // Keep stale rows on refresh failure — only hard-fail on first paint
    if (rows.value.length === 0) {
      error.value = err instanceof Error ? err.message : 'Ist-Daten konnten nicht geladen werden'
    }
  } finally {
    if (!signal.aborted) {
      initialLoading.value = false
      refreshing.value = false
    }
  }
}

function appendSensorRows(
  target: IstRow[],
  zoneLabel: string,
  data: ZoneMonitorData,
): void {
  for (const group of data.subzones) {
    for (const sensor of group.sensors) {
      target.push({
        zoneLabel,
        placeLabel: placeLabel(group.subzone_name),
        measureLabel: measureFromType(sensor.sensor_type, sensor.name),
        valueDisplay: formatValue(sensor.raw_value, sensor.unit),
        quality: qualityLabel(sensor.quality || '—'),
      })
    }
  }
}

function scheduleLoad(force = false): void {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    void load(force)
  }, 200)
}

function stopBackgroundRefresh(): void {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

function startBackgroundRefresh(): void {
  stopBackgroundRefresh()
  refreshInterval = setInterval(() => {
    if (props.active) void load(true)
  }, BACKGROUND_REFRESH_MS)
}

watch(
  () => [props.active, loadKey.value] as const,
  ([active]) => {
    if (!active) {
      abortController?.abort()
      abortController = null
      if (debounceTimer) {
        clearTimeout(debounceTimer)
        debounceTimer = null
      }
      stopBackgroundRefresh()
      return
    }
    scheduleLoad(false)
    startBackgroundRefresh()
  },
  { immediate: true },
)

onUnmounted(() => {
  abortController?.abort()
  abortController = null
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  stopBackgroundRefresh()
})
</script>

<template>
  <section class="space-y-3" aria-label="Ist-Kontext">
    <div class="flex items-center gap-2">
      <h4 class="text-xs font-semibold uppercase tracking-wide text-dark-300">
        Ist
      </h4>
      <span
        v-if="refreshing"
        class="inline-flex items-center gap-1 text-xs text-dark-400"
        aria-live="polite"
      >
        <BaseSpinner class="h-3 w-3" />
        Aktualisiere…
      </span>
    </div>

    <div
      v-if="initialLoading"
      class="flex items-center gap-2 text-sm text-dark-300"
    >
      <BaseSpinner class="h-4 w-4" />
      <span>Ist-Daten werden geladen…</span>
    </div>

    <ErrorState
      v-else-if="error && rows.length === 0"
      :message="error"
      @retry="load(true)"
    />

    <p
      v-else-if="!initialLoading && rows.length === 0"
      class="text-sm text-dark-300"
    >
      Keine Ist-Messwerte für diese Domäne in den gewählten Zonen.
    </p>

    <ul v-if="rows.length > 0" class="space-y-2">
      <li
        v-for="(row, idx) in rows"
        :key="`${row.zoneLabel}-${row.placeLabel}-${row.measureLabel}-${idx}`"
        class="flex flex-wrap items-baseline justify-between gap-2 rounded-md bg-dark-800/60 px-3 py-2 transition-opacity duration-200"
        :class="refreshing ? 'opacity-80' : 'opacity-100'"
      >
        <div class="min-w-0">
          <p class="text-sm text-dark-100">
            {{ row.measureLabel }}
          </p>
          <p class="text-xs text-dark-400">
            {{ row.zoneLabel }} · {{ row.placeLabel }}
          </p>
        </div>
        <div class="text-right">
          <p class="text-sm font-medium text-dark-50">{{ row.valueDisplay }}</p>
          <p class="text-xs text-dark-400">{{ row.quality }}</p>
        </div>
      </li>
    </ul>
  </section>
</template>
