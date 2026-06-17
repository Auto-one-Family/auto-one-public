import { ref, readonly } from 'vue'

const ZONE_STORAGE_KEY = 'camera_zone_id'

const _assignedZoneId = ref<string | null>(localStorage.getItem(ZONE_STORAGE_KEY))

export function useCameraZone() {
  function assignZone(zoneId: string | null): void {
    _assignedZoneId.value = zoneId
    if (zoneId) {
      localStorage.setItem(ZONE_STORAGE_KEY, zoneId)
    } else {
      localStorage.removeItem(ZONE_STORAGE_KEY)
    }
  }

  return {
    assignedZoneId: readonly(_assignedZoneId),
    assignZone,
  }
}
