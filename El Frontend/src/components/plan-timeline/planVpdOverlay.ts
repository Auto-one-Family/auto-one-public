/**
 * Derived VPD-Zielband overlay for Planungs-Zeitstrahl (AUT-1240).
 *
 * Read-only. Never editable. Physically separate from Ist-Telemetrie /
 * past-overlay (UX-6). Mirrors server Magnus-Tetens in vpd_calculator.py
 * and planned_climate.derive_vpd_band_from_planned (point case).
 */

import type { PlanSegment } from '@/types/planSegment'
import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'

export interface PlanVpdOverlayBand {
  id: string
  fromMs: number
  toMs: number
  leftPct: number
  widthPct: number
  computable: boolean
  /** Centre VPD in kPa when computable. */
  vpdKpa: number | null
  reason: string | null
  label: string
  tooltip: string
}

/** Magnus-Tetens Air-VPD (kPa) — same formula as server vpd_calculator. */
export function calculateVpdKpa(
  temperatureC: number,
  humidityRh: number,
): number | null {
  if (!(humidityRh >= 0 && humidityRh <= 100)) return null
  if (!(temperatureC >= -40 && temperatureC <= 80)) return null
  const svp =
    0.6108 * Math.exp((17.27 * temperatureC) / (temperatureC + 237.3))
  const avp = svp * (humidityRh / 100)
  return Math.round((svp - avp) * 10000) / 10000
}

function reasonLabel(reason: string | null): string {
  switch (reason) {
    case 'missing_target_temperature':
      return 'VPD nicht berechenbar (Temperatur-Ziel fehlt)'
    case 'missing_target_humidity':
      return 'VPD nicht berechenbar (Feuchte-Ziel fehlt)'
    case 'missing_target_temperature_and_humidity':
      return 'VPD nicht berechenbar (Temperatur- und Feuchte-Ziel fehlen)'
    case 'inputs_out_of_range':
      return 'VPD nicht berechenbar (Werte außerhalb Bereich)'
    default:
      return 'VPD nicht berechenbar'
  }
}

type Interval = {
  fromMs: number
  toMs: number
  temp: number | null
  humidity: number | null
}

/**
 * Build non-editable VPD overlay bands for a zone's climate segments
 * inside the visible window. Overlapping T+RH → computable band;
 * only one base measure → explicit non-computable band (anti-silence).
 */
export function buildVpdOverlayBands(
  segments: PlanSegment[],
  zoneId: string,
  window: PlanTimelineWindow,
): PlanVpdOverlayBand[] {
  const climate = segments.filter(
    (s) =>
      s.zone_id === zoneId &&
      s.domain === 'climate' &&
      (s.measure === 'target_temperature' || s.measure === 'target_humidity'),
  )
  if (climate.length === 0) return []

  const bounds = new Set<number>([window.startMs, window.endMs])
  for (const seg of climate) {
    const fromMs = Date.parse(seg.from_ts)
    const toMs = seg.to_ts ? Date.parse(seg.to_ts) : window.endMs
    if (!Number.isNaN(fromMs)) bounds.add(Math.max(fromMs, window.startMs))
    if (!Number.isNaN(toMs)) bounds.add(Math.min(toMs, window.endMs))
  }

  const edges = [...bounds].sort((a, b) => a - b)
  const intervals: Interval[] = []
  for (let i = 0; i < edges.length - 1; i++) {
    const fromMs = edges[i]
    const toMs = edges[i + 1]
    if (toMs <= fromMs) continue
    const mid = (fromMs + toMs) / 2
    let temp: number | null = null
    let humidity: number | null = null
    for (const seg of climate) {
      const sFrom = Date.parse(seg.from_ts)
      const sTo = seg.to_ts ? Date.parse(seg.to_ts) : window.endMs
      if (Number.isNaN(sFrom) || Number.isNaN(sTo)) continue
      if (mid < sFrom || mid >= sTo) continue
      if (seg.measure === 'target_temperature' && seg.value != null) {
        temp = seg.value
      }
      if (seg.measure === 'target_humidity' && seg.value != null) {
        humidity = seg.value
      }
    }
    if (temp === null && humidity === null) continue
    intervals.push({ fromMs, toMs, temp, humidity })
  }

  const span = Math.max(window.endMs - window.startMs, 1)
  return intervals.map((iv, idx): PlanVpdOverlayBand => {
    let computable = false
    let vpdKpa: number | null = null
    let reason: string | null = null
    if (iv.temp === null && iv.humidity === null) {
      reason = 'missing_target_temperature_and_humidity'
    } else if (iv.temp === null) {
      reason = 'missing_target_temperature'
    } else if (iv.humidity === null) {
      reason = 'missing_target_humidity'
    } else {
      vpdKpa = calculateVpdKpa(iv.temp, iv.humidity)
      if (vpdKpa === null) reason = 'inputs_out_of_range'
      else computable = true
    }

    const leftPct = ((iv.fromMs - window.startMs) / span) * 100
    const widthPct = ((iv.toMs - iv.fromMs) / span) * 100
    const label = computable
      ? `VPD ${vpdKpa!.toFixed(2)} kPa`
      : reasonLabel(reason)
    const tooltip = computable
      ? `VPD-Zielband (abgeleitet)\n${vpdKpa!.toFixed(2)} kPa\naus Temperatur-Ziel ${iv.temp} °C + Feuchte-Ziel ${iv.humidity} %\nNur Anzeige — nicht editierbar`
      : `${reasonLabel(reason)}\nNur Anzeige — nicht editierbar`

    return {
      id: `vpd-${zoneId}-${idx}-${iv.fromMs}`,
      fromMs: iv.fromMs,
      toMs: iv.toMs,
      leftPct,
      widthPct,
      computable,
      vpdKpa,
      reason,
      label,
      tooltip,
    }
  })
}
