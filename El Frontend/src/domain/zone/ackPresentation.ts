/**
 * Zone/Subzone ACK presentation (P0-D).
 * reason_code = Brückengrund (MQTT/Firmware), nicht Intent-Outcome-Code.
 */

export interface ZoneAckToastParts {
  title: string
  bridgeLine: string | null
}

export function formatZoneAckSuccess(parts: {
  deviceName: string
  zoneName: string
  reasonCode?: string | null
}): ZoneAckToastParts {
  const title = `"${parts.deviceName}" wurde zu "${parts.zoneName}" zugewiesen`
  const bridgeLine =
    parts.reasonCode && String(parts.reasonCode).trim().length > 0
      ? `Brückengrund (Zone): ${parts.reasonCode}`
      : null
  return { title, bridgeLine }
}

export function formatZoneAckRemoved(parts: {
  deviceName: string
  zoneName: string
  reasonCode?: string | null
}): ZoneAckToastParts {
  const title = `"${parts.deviceName}" wurde aus "${parts.zoneName}" entfernt`
  const bridgeLine =
    parts.reasonCode && String(parts.reasonCode).trim().length > 0
      ? `Brückengrund (Zone): ${parts.reasonCode}`
      : null
  return { title, bridgeLine }
}

export function formatZoneAckError(parts: {
  message?: string | null
  reasonCode?: string | null
}): { headline: string; bridgeLine: string | null } {
  const headline = parts.message?.trim() || 'Zone-Zuweisung fehlgeschlagen'
  const bridgeLine =
    parts.reasonCode && String(parts.reasonCode).trim().length > 0
      ? `Brückengrund (Zone): ${parts.reasonCode}`
      : null
  return { headline, bridgeLine }
}

export function formatSubzoneAckSuccess(parts: {
  deviceLabel: string
  reasonCode?: string | null
}): ZoneAckToastParts {
  const title = `Subzone zugewiesen: ${parts.deviceLabel}`
  const bridgeLine =
    parts.reasonCode && String(parts.reasonCode).trim().length > 0
      ? `Brückengrund (Subzone): ${parts.reasonCode}`
      : null
  return { title, bridgeLine }
}

export function formatSubzoneRemoved(parts: {
  deviceLabel: string
  reasonCode?: string | null
}): ZoneAckToastParts {
  const title = `Subzone entfernt: ${parts.deviceLabel}`
  const bridgeLine =
    parts.reasonCode && String(parts.reasonCode).trim().length > 0
      ? `Brückengrund (Subzone): ${parts.reasonCode}`
      : null
  return { title, bridgeLine }
}

export function formatSubzoneAckError(parts: {
  message?: string | null
  reasonCode?: string | null
  errorCode?: string | null
}): { headline: string; bridgeLine: string | null; errorCodeLine: string | null } {
  const headline = parts.message?.trim() || 'Subzone-Zuweisung fehlgeschlagen'
  const bridgeLine =
    parts.reasonCode && String(parts.reasonCode).trim().length > 0
      ? `Brückengrund (Subzone): ${parts.reasonCode}`
      : null
  const errorCodeLine =
    parts.errorCode && String(parts.errorCode).trim().length > 0
      ? `Fehlercode (Subzone): ${parts.errorCode}`
      : null
  return { headline, bridgeLine, errorCodeLine }
}
