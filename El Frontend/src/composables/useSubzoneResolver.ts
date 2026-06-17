/**
 * useSubzoneResolver — GPIO → Subzone Map (Fallback for Monitor L2)
 *
 * When GET /zone/{zone_id}/monitor-data is unavailable, this composable
 * builds a Map from (esp_id, gpio) to { subzoneId, subzoneName } using
 * subzone_configs.assigned_gpios from the Subzone API.
 *
 * Used with useZoneGrouping for fallback data source.
 */

import { computed, ref, watch, type Ref, type ComputedRef } from 'vue'
import { useEspStore } from '@/stores/esp'
import { subzonesApi } from '@/api/subzones'

export interface SubzoneResolved {
  subzoneId: string
  subzoneName: string
}

interface SubzoneResolverOptions {
  /** When true, does not auto-trigger on zone changes. Call buildResolver() manually. */
  lazy?: boolean
}

/**
 * Builds Map: `${espId}-${gpio}` → { subzoneId, subzoneName }
 */
export function useSubzoneResolver(
  zoneIdRef: Ref<string | null> | ComputedRef<string | null>,
  options: SubzoneResolverOptions = {},
) {
  const espStore = useEspStore()
  const resolverMap = ref<Map<string, SubzoneResolved>>(new Map())
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const zoneId = computed(() => zoneIdRef.value)

  const devicesInZone = computed(() => {
    const id = zoneId.value
    if (!id) return []
    return espStore.devices.filter(d => d.zone_id === id)
  })

  async function buildResolver() {
    if (!zoneId.value || devicesInZone.value.length === 0) {
      resolverMap.value = new Map()
      return
    }

    isLoading.value = true
    error.value = null
    const map = new Map<string, SubzoneResolved>()

    try {
      const espIds = devicesInZone.value
        .map(d => espStore.getDeviceId(d))
        .filter((id): id is string => !!id)

      const results = await Promise.allSettled(
        espIds.map(async (espId) => ({
          espId,
          subzones: (await subzonesApi.getSubzones(espId)).subzones ?? [],
        })),
      )

      for (const result of results) {
        if (result.status === 'rejected') continue
        const { espId, subzones } = result.value
        for (const sz of subzones) {
          const subzoneId = sz.subzone_id ?? ''
          const subzoneName = sz.subzone_name ?? subzoneId
          for (const gpio of sz.assigned_gpios ?? []) {
            map.set(`${espId}-${gpio}`, { subzoneId, subzoneName })
          }
        }
      }

      resolverMap.value = map
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Fehler beim Laden'
      resolverMap.value = new Map()
    } finally {
      isLoading.value = false
    }
  }

  if (!options.lazy) {
    watch(
      [zoneId, () => devicesInZone.value.length],
      () => {
        buildResolver()
      },
      { immediate: true },
    )
  }

  return {
    resolverMap,
    isLoading,
    error,
    buildResolver,
  }
}
