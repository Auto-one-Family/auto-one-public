/**
 * useSubzoneCRUD — Reusable Subzone CRUD Logic
 *
 * Extracted from SensorsView for reuse in HardwareView, MonitorView, and SensorsView.
 * Provides create, rename, and delete operations for subzones.
 *
 * B1/B5 Fix: ESP-Lookup via subzonesApi.getSubzones (device.subzone_id is unreliable).
 * Rename: assigned_gpios aus getSubzone laden, damit nicht überschrieben werden.
 */

import { ref } from 'vue'
import { subzonesApi } from '@/api/subzones'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'
import { slugifyGerman } from '@/utils/subzoneHelpers'

export function useSubzoneCRUD() {
  const espStore = useEspStore()
  const toast = useToast()

  // State
  const creatingSubzoneForZone = ref<string | null>(null)
  const newSubzoneName = ref('')
  const editingSubzoneId = ref<string | null>(null)
  const editingSubzoneName = ref('')
  const subzoneActionLoading = ref(false)

  /**
   * Find ESP that owns this subzone by querying getSubzones for each device in zone.
   */
  async function findEspForSubzone(subzoneId: string, zoneId: string | null): Promise<string | null> {
    const devicesInZone = zoneId
      ? espStore.devices.filter(d => (d.zone_id || null) === zoneId)
      : espStore.devices
    for (const device of devicesInZone) {
      const espId = espStore.getDeviceId(device)
      try {
        const result = await subzonesApi.getSubzones(espId)
        const list = (result as { subzones?: Array<{ subzone_id?: string; id?: string }> }).subzones ?? []
        const hasSubzone = list.some((sz: { subzone_id?: string; id?: string }) =>
          (sz.subzone_id ?? sz.id ?? '') === subzoneId
        )
        if (hasSubzone) return espId
      } catch {
        continue
      }
    }
    return null
  }

  // =========================================================================
  // Create
  // =========================================================================

  function startCreateSubzone(zoneId: string | null) {
    creatingSubzoneForZone.value = zoneId ?? '__unassigned__'
    newSubzoneName.value = ''
  }

  function cancelCreateSubzone() {
    creatingSubzoneForZone.value = null
    newSubzoneName.value = ''
  }

  /**
   * Create subzone. Assigns GPIOs if provided.
   * @param zoneId - Zone ID
   * @param assignedGpios - Optional GPIOs to assign (e.g. from SensorConfigPanel). Empty = leere Subzone.
   */
  async function confirmCreateSubzone(zoneId: string | null, assignedGpios: number[] = []) {
    if (!newSubzoneName.value.trim()) return
    subzoneActionLoading.value = true
    try {
      const espInZone = espStore.devices.find(d => (d.zone_id || null) === zoneId)
      if (!espInZone) {
        toast.error('Kein Geraet in dieser Zone gefunden')
        return
      }
      const espId = espStore.getDeviceId(espInZone)
      const subzoneId = slugifyGerman(newSubzoneName.value)
      await subzonesApi.assignSubzone(espId, {
        subzone_id: subzoneId,
        subzone_name: newSubzoneName.value.trim(),
        parent_zone_id: zoneId || undefined,
        assigned_gpios: assignedGpios,
      })
      await espStore.fetchAll()
      if (assignedGpios.length === 0) {
        toast.success(`Subzone "${newSubzoneName.value.trim()}" erstellt. Zuweisung ueber Sensor/Aktor-Konfiguration.`)
      } else {
        toast.success(`Subzone "${newSubzoneName.value.trim()}" erstellt`)
      }
      cancelCreateSubzone()
    } catch {
      toast.error('Subzone konnte nicht erstellt werden')
    } finally {
      subzoneActionLoading.value = false
    }
  }

  // =========================================================================
  // Rename
  // =========================================================================

  function startRenameSubzone(subzoneId: string, currentName: string) {
    editingSubzoneId.value = subzoneId
    editingSubzoneName.value = currentName
  }

  function cancelRenameSubzone() {
    editingSubzoneId.value = null
    editingSubzoneName.value = ''
  }

  async function saveSubzoneName(subzoneId: string, zoneId: string | null) {
    if (!editingSubzoneName.value.trim()) return
    subzoneActionLoading.value = true
    try {
      const espId = await findEspForSubzone(subzoneId, zoneId)
      if (!espId) {
        toast.error('Subzone konnte nicht gefunden werden')
        cancelRenameSubzone()
        return
      }
      const existing = await subzonesApi.getSubzone(espId, subzoneId)
      const assignedGpios = existing.assigned_gpios ?? []
      await subzonesApi.assignSubzone(espId, {
        subzone_id: subzoneId,
        subzone_name: editingSubzoneName.value.trim(),
        parent_zone_id: zoneId || existing.parent_zone_id || undefined,
        assigned_gpios: assignedGpios,
      })
      await espStore.fetchAll()
      toast.success('Subzone umbenannt')
      cancelRenameSubzone()
    } catch {
      toast.error('Subzone konnte nicht umbenannt werden')
    } finally {
      subzoneActionLoading.value = false
    }
  }

  // =========================================================================
  // Delete
  // =========================================================================

  async function deleteSubzone(subzoneId: string, subzoneName?: string, zoneId?: string | null) {
    subzoneActionLoading.value = true
    try {
      const espId = await findEspForSubzone(subzoneId, zoneId ?? null)
      if (!espId) {
        toast.error('Subzone konnte nicht gefunden werden')
        return
      }
      await subzonesApi.removeSubzone(espId, subzoneId)
      await espStore.fetchAll()
      toast.success(`Subzone "${subzoneName || subzoneId}" geloescht`)
    } catch {
      toast.error('Subzone konnte nicht geloescht werden')
    } finally {
      subzoneActionLoading.value = false
    }
  }

  return {
    // State
    creatingSubzoneForZone,
    newSubzoneName,
    editingSubzoneId,
    editingSubzoneName,
    subzoneActionLoading,

    // Create
    startCreateSubzone,
    cancelCreateSubzone,
    confirmCreateSubzone,

    // Rename
    startRenameSubzone,
    cancelRenameSubzone,
    saveSubzoneName,

    // Delete
    deleteSubzone,
  }
}
