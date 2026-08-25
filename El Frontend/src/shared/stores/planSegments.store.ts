/**
 * Plan Segments Store (AUT-1234 T4 / AUT-1235 T5)
 *
 * Store→API load/mutate path for the Planungs-Zeitstrahl tab.
 * All writes go through planSegmentsApi → POST/PATCH/DELETE /plan-segments.
 * No local draft store that outlives a failed persist.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import { planSegmentsApi } from '@/api/planSegments'
import type {
  PlanSegment,
  PlanSegmentCreate,
  PlanSegmentListParams,
  PlanSegmentUpdate,
} from '@/types/planSegment'
import { createLogger } from '@/utils/logger'

const logger = createLogger('PlanSegmentsStore')

export const usePlanSegmentsStore = defineStore('planSegments', () => {
  const segments = ref<PlanSegment[]>([])
  const isLoading = ref(false)
  const isMutating = ref(false)
  const error = ref<string | null>(null)
  const lastListParams = ref<PlanSegmentListParams>({})

  async function fetchSegments(params: PlanSegmentListParams = {}): Promise<void> {
    isLoading.value = true
    error.value = null
    lastListParams.value = { ...params }
    try {
      segments.value = await planSegmentsApi.list(params)
    } catch (e) {
      segments.value = []
      const status = axios.isAxiosError(e) ? e.response?.status : undefined
      if (status === 404) {
        error.value = null
        logger.info('GET /plan-segments not available yet (404) — empty scaffold')
      } else {
        error.value =
          e instanceof Error ? e.message : 'Plan-Segmente konnten nicht geladen werden'
        logger.error('Failed to fetch plan segments', e)
      }
    } finally {
      isLoading.value = false
    }
  }

  async function refresh(): Promise<void> {
    await fetchSegments(lastListParams.value)
  }

  async function createSegment(payload: PlanSegmentCreate): Promise<PlanSegment> {
    isMutating.value = true
    error.value = null
    try {
      const created = await planSegmentsApi.create(payload)
      await refresh()
      return created
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Plan-Segment konnte nicht angelegt werden'
      logger.error('Failed to create plan segment', e)
      throw e
    } finally {
      isMutating.value = false
    }
  }

  async function updateSegment(
    id: string,
    payload: PlanSegmentUpdate,
  ): Promise<PlanSegment> {
    isMutating.value = true
    error.value = null
    try {
      const updated = await planSegmentsApi.update(id, payload)
      await refresh()
      return updated
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Plan-Segment konnte nicht aktualisiert werden'
      logger.error('Failed to update plan segment', e)
      throw e
    } finally {
      isMutating.value = false
    }
  }

  async function deleteSegment(id: string): Promise<void> {
    isMutating.value = true
    error.value = null
    try {
      await planSegmentsApi.remove(id)
      await refresh()
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Plan-Segment konnte nicht gelöscht werden'
      logger.error('Failed to delete plan segment', e)
      throw e
    } finally {
      isMutating.value = false
    }
  }

  function clear(): void {
    segments.value = []
    error.value = null
  }

  return {
    segments,
    isLoading,
    isMutating,
    error,
    fetchSegments,
    refresh,
    createSegment,
    updateSegment,
    deleteSegment,
    clear,
  }
})
