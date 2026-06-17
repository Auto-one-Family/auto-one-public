#ifndef UTILS_WATCHDOG_STORAGE_H
#define UTILS_WATCHDOG_STORAGE_H

#include <stdint.h>

struct WatchdogDiagnostics;

/**
 * Call once per boot after storageManager.begin().
 * Captures whether this boot was caused by task watchdog reset.
 */
void watchdogStorageInitEarly();

/**
 * After valid wall time is available (NTP), records this boot's WDT event in NVS
 * and evaluates 3×/24h (logging only — full safe-mode policy stays elsewhere).
 * Safe to call repeatedly until time is valid; then becomes a no-op.
 */
void watchdogStorageTryFinalizeBootRecord();

/**
 * Number of recorded watchdog timeout events in the rolling 24h window.
 */
uint8_t watchdogStorageGetCountLast24h();

/**
 * Counter for expected missing watchdog history key reads.
 */
uint32_t watchdogStorageGetHistNotFoundExpectedCount();

/**
 * Counter for unexpected missing watchdog history key reads.
 */
uint32_t watchdogStorageGetHistNotFoundUnexpectedCount();

/**
 * Persist last diagnostic snapshot (best-effort; provisioning / pre-panic paths).
 */
void watchdogStorageSaveDiagnosticsSnapshot(const WatchdogDiagnostics& diag);

/**
 * Log last persisted snapshot from NVS after a WDT boot (if any).
 */
void watchdogStorageLogLastSnapshotIfAny();

#endif
