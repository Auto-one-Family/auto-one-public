import type { AlertLifecycleFailure } from '@/shared/stores/alert-center.store'

/** Einheitliche Fehlertexte für Ack/Resolve (Finalität, inkl. optionaler Request-ID). */
export function formatAlertLifecycleFailureMessage(failure: AlertLifecycleFailure): string {
  return failure.requestId
    ? `${failure.message} (Request-ID: ${failure.requestId})`
    : failure.message
}
