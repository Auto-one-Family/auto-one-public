import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { createLogger } from '@/utils/logger'

import './styles/main.css'

const app = createApp(App)
const logger = createLogger('Global')

/**
 * Fire-and-forget POST to backend log endpoint.
 * Uses relative URL so Vite proxy handles routing (avoids CORS in dev mode).
 * Catches and silently ignores network errors.
 */
function reportToBackend(payload: Record<string, unknown>): void {
  fetch('/api/v1/logs/frontend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).catch(() => {})
}

app.use(createPinia())
app.use(router)

// Global Vue Error Handler - structured logging + backend reporting
app.config.errorHandler = (err, instance, info) => {
  const component = instance?.$options?.name || 'Unknown'
  const message = err instanceof Error ? err.message : String(err)
  const stack = err instanceof Error ? err.stack : undefined

  logger.error('Vue error', { error: message, stack, component, info })

  reportToBackend({
    level: 'error',
    component,
    message,
    stack,
    info,
    url: window.location.href,
    timestamp: new Date().toISOString(),
  })
}

app.config.warnHandler = (msg, instance, trace) => {
  logger.warn('Vue warning', {
    message: msg,
    component: instance?.$options?.name || 'Unknown',
    trace,
  })
}

// Global Unhandled Promise Rejection Handler
window.addEventListener('unhandledrejection', (event) => {
  const message = event.reason instanceof Error ? event.reason.message : String(event.reason)
  const stack = event.reason instanceof Error ? event.reason.stack : undefined

  logger.error('Unhandled rejection', { reason: message, stack })

  reportToBackend({
    level: 'error',
    component: 'PromiseRejection',
    message,
    stack,
    url: window.location.href,
    timestamp: new Date().toISOString(),
  })
})

// Global window.onerror Handler - catches synchronous JS errors
window.onerror = (message, source, lineno, colno, error) => {
  const msg = String(message)

  logger.error('Uncaught error', { message: msg, source, lineno, colno, stack: error?.stack })

  reportToBackend({
    level: 'error',
    component: 'WindowError',
    message: msg,
    stack: error?.stack,
    info: `${source}:${lineno}:${colno}`,
    url: window.location.href,
    timestamp: new Date().toISOString(),
  })
}

app.mount('#app')
