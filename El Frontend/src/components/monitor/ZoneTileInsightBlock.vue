<script setup lang="ts">
/**
 * Monitor L1 — Zoneinsight (read-only): VPD aus Zonen-Ø T+RH, 24h-Temperaturspanne (Repräsentativsensor).
 * Kein zweites Klima-Tacho; ergänzt die Ø-KPI-Zeile um fachliche Kennzahlen.
 *
 * 24h-Stats: nur bei Lead-Sensor-Wechsel oder TTL-Refresh (nicht bei jedem WS-Sensor-Tick).
 */
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useEspStore } from '@/stores/esp'
import { sensorsApi } from '@/api/sensors'
import { computeZoneVpdKpaFromKpiSensorTypes, isValidSensorValue } from '@/utils/sensorDefaults'
import { pickZoneLeadTemperatureSensor } from '@/utils/zoneTileInsight'
import { formatNumber } from '@/utils/formatters'
import type { ZoneKPI } from '@/composables/useZoneKPIs'
import { Loader2 } from 'lucide-vue-next'

interface Props {
  zone: ZoneKPI
}

const props = defineProps<Props>()

const espStore = useEspStore()

/** 24h-Min/Max aendert sich langsam — kein Per-Sensor-Tick-Fetch (verhindert Layout-Spruenge). */
const TEMP_SPAN_REFRESH_MS = 5 * 60 * 1000

const vpdKpa = computed(() => computeZoneVpdKpaFromKpiSensorTypes(props.zone.aggregation.sensorTypes))

const leadTemp = computed(() =>
  pickZoneLeadTemperatureSensor(espStore.devices, props.zone.zoneId, espStore.getDeviceId),
)

const spanLoading = ref(false)
const spanError = ref<string | null>(null)
const tempMin = ref<number | null>(null)
const tempMax = ref<number | null>(null)

let statsRequestSeq = 0
let refreshTimer: ReturnType<typeof setInterval> | null = null

function hasCachedSpan(): boolean {
  return tempMin.value != null && tempMax.value != null
}

async function fetchTempSpan(options: { showLoading: boolean }): Promise<void> {
  const lead = leadTemp.value
  if (!lead) {
    tempMin.value = null
    tempMax.value = null
    spanError.value = null
    spanLoading.value = false
    return
  }

  const mySeq = ++statsRequestSeq
  const keepPreviousOnError = hasCachedSpan()
  if (options.showLoading && !keepPreviousOnError) {
    spanLoading.value = true
  }
  if (!keepPreviousOnError) {
    spanError.value = null
  }

  try {
    const now = new Date()
    const startTime = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString()
    const endTime = now.toISOString()
    const response = await sensorsApi.getStats(lead.espId, lead.gpio, {
      start_time: startTime,
      end_time: endTime,
      sensor_type: lead.sensorType,
    })
    if (mySeq !== statsRequestSeq) return
    tempMin.value = response.stats.min_value
    tempMax.value = response.stats.max_value
    spanError.value = null
  } catch {
    if (mySeq !== statsRequestSeq) return
    // Hintergrund-Refresh: bestehende Werte behalten (kein Flicker)
    if (!keepPreviousOnError) {
      spanError.value = '24h-Spanne nicht verfügbar'
      tempMin.value = null
      tempMax.value = null
    }
  } finally {
    if (mySeq === statsRequestSeq) spanLoading.value = false
  }
}

/**
 * Wichtig: einzelne Getter als Source-Array — NICHT `() => [a, b, c]`.
 * Ein neues Array pro Getter-Lauf gilt bei Vue als Change (Object.is),
 * obwohl die Primitiven gleich bleiben → Fetch bei jedem WS-Sensor-Tick.
 */
watch(
  [
    () => props.zone.zoneId,
    () => leadTemp.value?.espId,
    () => leadTemp.value?.gpio,
    () => leadTemp.value?.sensorType,
  ],
  (_next, prev) => {
    // Lead-Identitaet gewechselt → alte Min/Max verwerfen
    if (prev != null) {
      tempMin.value = null
      tempMax.value = null
    }
    void fetchTempSpan({ showLoading: true })
  },
  { immediate: true },
)

onMounted(() => {
  refreshTimer = setInterval(() => {
    void fetchTempSpan({ showLoading: false })
  }, TEMP_SPAN_REFRESH_MS)
})

onUnmounted(() => {
  statsRequestSeq++
  if (refreshTimer != null) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})

// AUT-613: unified label schema <Name> (<Zeitraum>) for both ZONEINSIGHT rows
const vpdLine = computed(() => {
  const v = vpdKpa.value
  if (v == null) return { primary: '—', hint: 'VPD (aktuell)' }
  return {
    primary: `${formatNumber(v, 2, '—')} kPa`,
    hint: 'VPD (Zonen-Ø, aktuell)',
  }
})

// AUT-605: useGrouping:false prevents thousands separator; per-value validation skips outliers
// gracefully (e.g. 26895 °C from a bad reading is excluded while valid min is still shown).
const spanLine = computed(() => {
  // Nur initial ohne Cache „…“ — sonst bleiben sichtbare Werte stabil waehrend Refresh
  if (spanLoading.value && !hasCachedSpan()) {
    return { primary: '…', hint: 'Temperatur 24h' }
  }
  if (spanError.value && !hasCachedSpan()) {
    return { primary: '—', hint: 'Temperatur 24h' }
  }
  const lo = tempMin.value
  const hi = tempMax.value
  if (lo == null || hi == null) return { primary: '—', hint: 'Temperatur 24h' }

  const sensorType = leadTemp.value?.sensorType ?? ''
  const loValid = isValidSensorValue(sensorType, lo)
  const hiValid = isValidSensorValue(sensorType, hi)

  if (loValid && hiValid) {
    return {
      primary: `${formatNumber(lo, 1, '—', false)} – ${formatNumber(hi, 1, '—', false)} °C`,
      hint: 'Temperatur 24h (Min–Max)',
    }
  }
  const single = loValid ? lo : hiValid ? hi : null
  if (single == null) return { primary: '—', hint: 'Temperatur 24h' }
  return {
    primary: `${formatNumber(single, 1, '—', false)} °C`,
    hint: 'Temperatur 24h',
  }
})

const showSpanSpinner = computed(() => spanLoading.value && !hasCachedSpan())

// AUT-624 Fix B: VPD color indicator using established agronomic thresholds
const VPD_OPTIMAL_MAX = 1.2
const VPD_STRESS_MAX = 1.8
const VPD_MIN = 0.4

const vpdDotClass = computed(() => {
  const v = vpdKpa.value
  if (v == null) return null
  if (v < VPD_MIN || v > VPD_STRESS_MAX) return 'zone-tile-insight__vpd-dot--danger'
  if (v > VPD_OPTIMAL_MAX) return 'zone-tile-insight__vpd-dot--warning'
  return 'zone-tile-insight__vpd-dot--ok'
})
</script>

<template>
  <div
    class="zone-tile-insight"
    role="region"
    aria-label="Zoneinsight"
  >
    <div class="zone-tile-insight__title">
      Zoneinsight
    </div>
    <div class="zone-tile-insight__rows">
      <div class="zone-tile-insight__row">
        <span class="zone-tile-insight__hint">{{ vpdLine.hint }}</span>
        <span class="zone-tile-insight__value-with-dot">
          <span class="zone-tile-insight__value">{{ vpdLine.primary }}</span>
          <span
            v-if="vpdDotClass"
            :class="['zone-tile-insight__vpd-dot', vpdDotClass]"
            aria-label="VPD-Ampel"
          >●</span>
        </span>
      </div>
      <div class="zone-tile-insight__row">
        <span class="zone-tile-insight__hint">{{ spanLine.hint }}</span>
        <span class="zone-tile-insight__row-value">
          <Loader2
            v-if="showSpanSpinner"
            class="zone-tile-insight__spinner"
            aria-hidden="true"
          />
          <span class="zone-tile-insight__value">{{ spanLine.primary }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.zone-tile-insight {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
}

.zone-tile-insight__title {
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.zone-tile-insight__rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.zone-tile-insight__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: var(--text-xs);
  min-width: 0;
}

.zone-tile-insight__hint {
  color: var(--color-text-muted);
  flex: 1;
  min-width: 0;
}

.zone-tile-insight__row-value {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
  min-height: 1.25em;
}

.zone-tile-insight__value-with-dot {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-1);
  flex-shrink: 0;
}

.zone-tile-insight__value {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.zone-tile-insight__spinner {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  animation: zone-tile-insight-spin 0.9s linear infinite;
}

@keyframes zone-tile-insight-spin {
  to {
    transform: rotate(360deg);
  }
}

/* AUT-624 Fix B: VPD status color dot */
.zone-tile-insight__vpd-dot {
  font-size: 9px;
  line-height: 1;
}

.zone-tile-insight__vpd-dot--ok {
  color: var(--color-success);
}

.zone-tile-insight__vpd-dot--warning {
  color: var(--color-warning);
}

.zone-tile-insight__vpd-dot--danger {
  color: var(--color-danger);
}
</style>
