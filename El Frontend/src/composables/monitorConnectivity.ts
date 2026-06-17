export type MonitorConnectivityState =
  | 'connected'
  | 'stale'
  | 'reconnecting'
  | 'degraded_api'
  | 'disconnected'

export type MonitorDataMode = 'Live' | 'Hybrid' | 'Snapshot'

export interface MonitorConnectivityInput {
  wsStatus: 'connected' | 'connecting' | 'disconnected' | 'error'
  hasZoneApiError: boolean
  hasDetailApiError: boolean
  lastApiSuccessAt: number | null
  nowTs?: number
  staleAfterMs?: number
}

export interface MonitorDataModeInput {
  hasSnapshotBase: boolean
  hasLiveOverlay: boolean
  monitorState: MonitorConnectivityState
}

const DEFAULT_STALE_AFTER_MS = 90_000

export function resolveMonitorConnectivityState(input: MonitorConnectivityInput): MonitorConnectivityState {
  const nowTs = input.nowTs ?? Date.now()
  const staleAfterMs = input.staleAfterMs ?? DEFAULT_STALE_AFTER_MS

  if (input.wsStatus === 'disconnected' || input.wsStatus === 'error') {
    return 'disconnected'
  }

  if (input.hasZoneApiError || input.hasDetailApiError) {
    return 'degraded_api'
  }

  if (input.wsStatus === 'connecting') {
    return 'reconnecting'
  }

  if (input.lastApiSuccessAt != null && nowTs - input.lastApiSuccessAt > staleAfterMs) {
    return 'stale'
  }

  return 'connected'
}

export function resolveMonitorDataMode(input: MonitorDataModeInput): MonitorDataMode {
  if (input.monitorState === 'disconnected' || input.monitorState === 'degraded_api') {
    return 'Snapshot'
  }
  if (input.hasSnapshotBase && input.hasLiveOverlay) {
    return 'Hybrid'
  }
  if (!input.hasSnapshotBase && input.hasLiveOverlay) {
    return 'Live'
  }
  return 'Snapshot'
}

// ============================================================================
// Device Flapping Detection (PKG-20)
// ============================================================================

const FLAPPING_WINDOW_MS = 5 * 60 * 1000 // 5 minutes
const FLAPPING_THRESHOLD = 3             // ≥3 disconnects → flapping

export interface DeviceFlappingState {
  espId: string
  disconnectCount: number
  windowMs: number
}

/**
 * Prunes entries older than `windowMs` and returns true when the remaining
 * disconnect count meets or exceeds `threshold`.
 */
export function isDeviceFlapping(
  timestamps: number[],
  nowTs: number = Date.now(),
  windowMs: number = FLAPPING_WINDOW_MS,
  threshold: number = FLAPPING_THRESHOLD,
): boolean {
  const cutoff = nowTs - windowMs
  let recentCount = 0
  for (const ts of timestamps) {
    if (ts >= cutoff) recentCount++
  }
  return recentCount >= threshold
}

/**
 * Returns the number of disconnect events within the window.
 */
export function countRecentDisconnects(
  timestamps: number[],
  nowTs: number = Date.now(),
  windowMs: number = FLAPPING_WINDOW_MS,
): number {
  const cutoff = nowTs - windowMs
  let count = 0
  for (const ts of timestamps) {
    if (ts >= cutoff) count++
  }
  return count
}

/**
 * Prunes timestamps older than `windowMs` in-place (GC-friendly).
 */
export function pruneOldTimestamps(
  timestamps: number[],
  nowTs: number = Date.now(),
  windowMs: number = FLAPPING_WINDOW_MS,
): void {
  const cutoff = nowTs - windowMs
  let writeIdx = 0
  for (let i = 0; i < timestamps.length; i++) {
    if (timestamps[i] >= cutoff) {
      timestamps[writeIdx++] = timestamps[i]
    }
  }
  timestamps.length = writeIdx
}

export { FLAPPING_WINDOW_MS, FLAPPING_THRESHOLD }

// ============================================================================
// Recovery Orchestrator
// ============================================================================

export function createMonitorRecoveryOrchestrator(runSteps: () => Promise<void>) {
  let running: Promise<void> | null = null
  let rerunRequested = false

  async function executeLoop(): Promise<void> {
    do {
      rerunRequested = false
      await runSteps()
    } while (rerunRequested)
  }

  async function trigger(): Promise<void> {
    if (running) {
      rerunRequested = true
      return running
    }
    running = executeLoop().finally(() => {
      running = null
    })
    return running
  }

  function isRunning(): boolean {
    return running != null
  }

  return {
    trigger,
    isRunning,
  }
}
