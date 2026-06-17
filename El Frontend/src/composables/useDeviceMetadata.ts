/**
 * useDeviceMetadata — Composable for loading, editing, and saving device metadata
 *
 * Uses the existing server metadata JSON fields (sensor_metadata / actuator_metadata).
 * No new API endpoints needed.
 */

import { ref, computed } from 'vue'
import type { DeviceMetadata } from '@/types/device-metadata'
import {
  parseDeviceMetadata,
  mergeDeviceMetadata,
  getNextMaintenanceDate,
  isMaintenanceOverdue,
} from '@/types/device-metadata'
interface UseDeviceMetadataOptions {
  /** Raw metadata from server response (Record<string, unknown> | null) */
  initialMetadata?: Record<string, unknown> | null
}

export function useDeviceMetadata(options: UseDeviceMetadataOptions = {}) {
  // Structured metadata extracted from raw server data
  const metadata = ref<DeviceMetadata>(
    parseDeviceMetadata(options.initialMetadata)
  )

  // Track whether metadata was modified
  const isDirty = ref(false)

  // Computed helpers
  const nextMaintenance = computed(() => getNextMaintenanceDate(metadata.value))
  const maintenanceOverdue = computed(() =>
    isMaintenanceOverdue(metadata.value)
  )

  /**
   * Update a single metadata field.
   */
  function updateField<K extends keyof DeviceMetadata>(
    field: K,
    value: DeviceMetadata[K]
  ) {
    metadata.value = { ...metadata.value, [field]: value }
    isDirty.value = true
  }

  /**
   * Replace entire metadata (e.g., after loading from server).
   */
  function loadFromRaw(raw: Record<string, unknown> | null | undefined) {
    metadata.value = parseDeviceMetadata(raw)
    isDirty.value = false
  }

  /**
   * Merge structured metadata into a raw record for saving.
   * Preserves existing fields not managed by DeviceMetadata.
   */
  function toRawMetadata(
    existingRaw: Record<string, unknown> | null | undefined
  ): Record<string, unknown> {
    return mergeDeviceMetadata(existingRaw, metadata.value)
  }

  return {
    metadata,
    isDirty,
    nextMaintenance,
    maintenanceOverdue,
    updateField,
    loadFromRaw,
    toRawMetadata,
  }
}
