import { describe, expect, it, vi } from 'vitest'
import {
  createMonitorRecoveryOrchestrator,
  resolveMonitorConnectivityState,
  resolveMonitorDataMode,
} from '@/composables/monitorConnectivity'

describe('monitorConnectivity', () => {
  describe('resolveMonitorConnectivityState', () => {
    it('mappt auf disconnected bei ws disconnect/error', () => {
      const disconnected = resolveMonitorConnectivityState({
        wsStatus: 'disconnected',
        hasZoneApiError: false,
        hasDetailApiError: false,
        lastApiSuccessAt: Date.now(),
      })
      const errored = resolveMonitorConnectivityState({
        wsStatus: 'error',
        hasZoneApiError: false,
        hasDetailApiError: false,
        lastApiSuccessAt: Date.now(),
      })

      expect(disconnected).toBe('disconnected')
      expect(errored).toBe('disconnected')
    })

    it('mappt auf degraded_api bei API-Fehler trotz WS', () => {
      const state = resolveMonitorConnectivityState({
        wsStatus: 'connected',
        hasZoneApiError: true,
        hasDetailApiError: false,
        lastApiSuccessAt: Date.now(),
      })
      expect(state).toBe('degraded_api')
    })

    it('mappt auf reconnecting waehrend connecting', () => {
      const state = resolveMonitorConnectivityState({
        wsStatus: 'connecting',
        hasZoneApiError: false,
        hasDetailApiError: false,
        lastApiSuccessAt: Date.now(),
      })
      expect(state).toBe('reconnecting')
    })

    it('mappt auf stale bei ueberfaelligem API-Erfolgstimestamp', () => {
      const now = Date.now()
      const state = resolveMonitorConnectivityState({
        wsStatus: 'connected',
        hasZoneApiError: false,
        hasDetailApiError: false,
        lastApiSuccessAt: now - 91_000,
        nowTs: now,
      })
      expect(state).toBe('stale')
    })

    it('mappt auf connected bei frischem Zustand', () => {
      const now = Date.now()
      const state = resolveMonitorConnectivityState({
        wsStatus: 'connected',
        hasZoneApiError: false,
        hasDetailApiError: false,
        lastApiSuccessAt: now - 10_000,
        nowTs: now,
      })
      expect(state).toBe('connected')
    })
  })

  describe('resolveMonitorDataMode', () => {
    it('liefert Hybrid fuer Snapshot-Basis plus Live-Overlay', () => {
      const mode = resolveMonitorDataMode({
        hasSnapshotBase: true,
        hasLiveOverlay: true,
        monitorState: 'connected',
      })
      expect(mode).toBe('Hybrid')
    })

    it('liefert Live ohne Snapshot-Basis bei aktivem Overlay', () => {
      const mode = resolveMonitorDataMode({
        hasSnapshotBase: false,
        hasLiveOverlay: true,
        monitorState: 'connected',
      })
      expect(mode).toBe('Live')
    })

    it('liefert Snapshot bei disconnected/degraded', () => {
      const disconnectedMode = resolveMonitorDataMode({
        hasSnapshotBase: true,
        hasLiveOverlay: true,
        monitorState: 'disconnected',
      })
      const degradedMode = resolveMonitorDataMode({
        hasSnapshotBase: true,
        hasLiveOverlay: true,
        monitorState: 'degraded_api',
      })
      expect(disconnectedMode).toBe('Snapshot')
      expect(degradedMode).toBe('Snapshot')
    })
  })

  describe('createMonitorRecoveryOrchestrator', () => {
    it('serialisiert mehrfach-trigger und fuehrt dedupliziert nach', async () => {
      const steps = vi.fn(async () => {
        await Promise.resolve()
      })
      const orchestrator = createMonitorRecoveryOrchestrator(steps)

      await Promise.all([
        orchestrator.trigger(),
        orchestrator.trigger(),
        orchestrator.trigger(),
      ])

      expect(steps).toHaveBeenCalledTimes(2)
      expect(orchestrator.isRunning()).toBe(false)
    })
  })
})
