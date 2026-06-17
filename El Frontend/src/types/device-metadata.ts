/**
 * DeviceMetadata — Structured metadata for sensors and actuators
 *
 * Persisted in the server's sensor_metadata / actuator_metadata JSON fields.
 * The server accepts any Record<string, unknown> — this interface provides
 * frontend type safety for the structured subset.
 */

export interface DeviceMetadata {
  // Manufacturer & Product
  manufacturer?: string
  model?: string
  datasheet_url?: string
  serial_number?: string
  firmware_version?: string

  // Installation
  installation_date?: string // ISO date (YYYY-MM-DD)
  installation_location?: string

  // Maintenance
  maintenance_interval_days?: number
  last_maintenance?: string // ISO date (YYYY-MM-DD)

  // Documentation
  notes?: string

  // Extensible: free-form key-value pairs for future use
  // (plants, substrate, project details, etc.)
  custom_fields?: Record<string, unknown>
}

/**
 * Extract DeviceMetadata from generic metadata record.
 * Validates known fields and ignores unknown ones.
 */
export function parseDeviceMetadata(
  raw: Record<string, unknown> | null | undefined
): DeviceMetadata {
  if (!raw) return {}

  return {
    manufacturer:
      typeof raw.manufacturer === 'string' ? raw.manufacturer : undefined,
    model: typeof raw.model === 'string' ? raw.model : undefined,
    datasheet_url:
      typeof raw.datasheet_url === 'string' ? raw.datasheet_url : undefined,
    serial_number:
      typeof raw.serial_number === 'string' ? raw.serial_number : undefined,
    firmware_version:
      typeof raw.firmware_version === 'string' ? raw.firmware_version : undefined,
    installation_date:
      typeof raw.installation_date === 'string'
        ? raw.installation_date
        : undefined,
    installation_location:
      typeof raw.installation_location === 'string'
        ? raw.installation_location
        : undefined,
    maintenance_interval_days:
      typeof raw.maintenance_interval_days === 'number'
        ? raw.maintenance_interval_days
        : undefined,
    last_maintenance:
      typeof raw.last_maintenance === 'string'
        ? raw.last_maintenance
        : undefined,
    notes: typeof raw.notes === 'string' ? raw.notes : undefined,
    custom_fields:
      typeof raw.custom_fields === 'object' && raw.custom_fields !== null
        ? (raw.custom_fields as Record<string, unknown>)
        : undefined,
  }
}

/**
 * Merge DeviceMetadata back into a generic metadata record,
 * preserving any existing fields that are not part of DeviceMetadata.
 */
export function mergeDeviceMetadata(
  existing: Record<string, unknown> | null | undefined,
  structured: DeviceMetadata
): Record<string, unknown> {
  const base = existing ? { ...existing } : {}

  // Write structured fields (only if defined, remove if undefined)
  const fields: (keyof DeviceMetadata)[] = [
    'manufacturer',
    'model',
    'datasheet_url',
    'serial_number',
    'firmware_version',
    'installation_date',
    'installation_location',
    'maintenance_interval_days',
    'last_maintenance',
    'notes',
    'custom_fields',
  ]

  for (const field of fields) {
    const value = structured[field]
    if (value !== undefined && value !== '') {
      base[field] = value
    } else {
      delete base[field]
    }
  }

  return base
}

/**
 * Calculate next maintenance date from last maintenance + interval.
 */
export function getNextMaintenanceDate(
  metadata: DeviceMetadata
): Date | null {
  if (!metadata.last_maintenance || !metadata.maintenance_interval_days)
    return null
  const last = new Date(metadata.last_maintenance)
  if (isNaN(last.getTime())) return null
  last.setDate(last.getDate() + metadata.maintenance_interval_days)
  return last
}

/**
 * Check if maintenance is overdue.
 */
export function isMaintenanceOverdue(metadata: DeviceMetadata): boolean {
  const next = getNextMaintenanceDate(metadata)
  if (!next) return false
  return next.getTime() < Date.now()
}
