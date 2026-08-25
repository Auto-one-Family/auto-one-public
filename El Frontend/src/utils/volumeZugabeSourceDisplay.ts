/**
 * AUT-1397 / AUT-1398 — Frischwasser source labels (manual | measured | none).
 */

import type { VolumeZugabeSource } from '@/types/measureBinding'

export function volumeZugabeSourceLabel(source: string | null | undefined): string {
  if (source === 'manual') return 'manuell'
  if (source === 'measured') return 'gemessen'
  if (source === 'none') return 'keine'
  return source || 'keine'
}

export function isVolumeZugabeSource(value: unknown): value is VolumeZugabeSource {
  return value === 'manual' || value === 'measured' || value === 'none'
}

/**
 * Herkunftszeile für gemessene Frischwasser-Liter (M-6).
 * Names + time — no raw UUIDs in the primary label.
 */
export function formatMeasuredFreshWaterOrigin(input: {
  ruleName?: string | null
  occurredAt?: string | null
  volumeL?: number | null
}): string {
  const parts: string[] = ['gemessen']
  if (input.ruleName?.trim()) {
    parts.push(`während ${input.ruleName.trim()}`)
  } else {
    parts.push('während Nachfüllung')
  }
  if (input.volumeL != null && Number.isFinite(input.volumeL)) {
    parts.push(`Δ = ${formatLiters(input.volumeL)} L`)
  }
  if (input.occurredAt) {
    const d = new Date(input.occurredAt)
    if (!Number.isNaN(d.getTime())) {
      parts.push(
        `· ${d.toLocaleString('de-DE', {
          day: '2-digit',
          month: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })}`,
      )
    }
  }
  return parts.join(' ')
}

function formatLiters(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}
