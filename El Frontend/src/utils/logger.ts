/**
 * Structured Logger for AutomationOne Frontend.
 *
 * Outputs JSON-structured logs to console for Docker/Promtail ingestion.
 * In DEV mode, also outputs human-readable format to browser console.
 *
 * JSON format: {"level","component","message","timestamp"}
 * Promtail Stage 3 extracts level + component as Loki labels.
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const LOG_LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
}

const configuredLevel: LogLevel = (
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_LOG_LEVEL) || 'debug'
).toLowerCase() as LogLevel

function shouldLog(level: LogLevel): boolean {
  return LOG_LEVEL_PRIORITY[level] >= (LOG_LEVEL_PRIORITY[configuredLevel] ?? 0)
}

export interface Logger {
  debug: (...args: unknown[]) => void
  info: (...args: unknown[]) => void
  warn: (...args: unknown[]) => void
  error: (...args: unknown[]) => void
}

export function createLogger(namespace: string): Logger {
  const isDev = typeof import.meta !== 'undefined' && import.meta.env?.DEV

  function emit(level: LogLevel, args: unknown[]): void {
    if (!shouldLog(level)) return

    const message = args
      .map((a) => (typeof a === 'string' ? a : JSON.stringify(a)))
      .join(' ')

    // Structured JSON output for Docker stdout → Promtail → Loki
    const entry = JSON.stringify({
      level,
      component: namespace,
      message,
      timestamp: new Date().toISOString(),
    })

    // Use console methods so Docker json-file driver captures via stdout/stderr
    switch (level) {
      case 'error':
        console.error(entry)
        break
      case 'warn':
        console.warn(entry)
        break
      case 'info':
        console.info(entry)
        break
      default:
        console.debug(entry)
    }

    // DEV mode: also print human-readable for browser DevTools
    if (isDev) {
      const prefix = `[${namespace}]`
      switch (level) {
        case 'error':
          console.error(prefix, ...args)
          break
        case 'warn':
          console.warn(prefix, ...args)
          break
        case 'info':
          console.info(prefix, ...args)
          break
        default:
          console.debug(prefix, ...args)
      }
    }
  }

  return {
    debug: (...args: unknown[]) => emit('debug', args),
    info: (...args: unknown[]) => emit('info', args),
    warn: (...args: unknown[]) => emit('warn', args),
    error: (...args: unknown[]) => emit('error', args),
  }
}
