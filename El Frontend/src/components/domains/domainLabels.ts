/**
 * German labels for device report domains (AUT-1321).
 *
 * Single source for ESPSettingsSheet + DomainAuswertungView.
 * Values must stay in sync with server esp_devices.domain.
 * Never render the raw technical key (e.g. "wasser") in visible UI text.
 */

export const DEVICE_DOMAIN_KEYS = [
  'luft',
  'wasser',
  'boden',
  'licht',
  'mensch',
  'pflanze',
] as const

export type DeviceDomainKey = (typeof DEVICE_DOMAIN_KEYS)[number]

export const DOMAIN_LABELS: Record<DeviceDomainKey, string> = {
  luft: 'Luft',
  wasser: 'Wasser',
  boden: 'Boden',
  licht: 'Licht',
  mensch: 'Mensch',
  pflanze: 'Pflanze',
}

/** Options for BaseSelect (empty = keine Domäne). */
export const DOMAIN_SELECT_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: '', label: 'Keine Domäne' },
  ...DEVICE_DOMAIN_KEYS.map((key) => ({
    value: key,
    label: DOMAIN_LABELS[key],
  })),
]

export function isDeviceDomainKey(value: string | null | undefined): value is DeviceDomainKey {
  return !!value && (DEVICE_DOMAIN_KEYS as readonly string[]).includes(value)
}

/** Klarname for UI — never returns a technical domain key. */
export function getDomainLabel(domain: string | null | undefined): string {
  if (!domain) return 'Keine Domäne'
  if (isDeviceDomainKey(domain)) return DOMAIN_LABELS[domain]
  return 'Unbekannte Domäne'
}
