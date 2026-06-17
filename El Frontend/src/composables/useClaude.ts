/**
 * useClaude Composable (AUT-272)
 *
 * Provides a reactive chat interface to the Claude AI backend.
 * Uses SSE streaming for assistant responses via the native fetch ReadableStream API
 * (Axios does not natively support streaming body iteration).
 *
 * Availability is determined at mount time by checking whether the "claude" plugin
 * is registered and enabled via GET /api/v1/plugins.
 *
 * @see El Servador/god_kaiser_server/src/api/v1/ai.py  POST /ai/chat
 * @see src/api/plugins.ts  pluginsApi.list()
 */

import { ref, onMounted, type Ref } from 'vue'
import { pluginsApi } from '@/api/plugins'
import { useAuthStore } from '@/shared/stores/auth.store'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  isStreaming?: boolean
}

export interface ClaudeContext {
  espId?: string
  sensorGpio?: number
  currentView?: string
}

export interface UseClaudeReturn {
  messages: Ref<ChatMessage[]>
  isStreaming: Ref<boolean>
  isAvailable: Ref<boolean>
  sendMessage: (text: string, context?: ClaudeContext) => Promise<void>
  clearHistory: () => void
  sessionId: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const CLAUDE_PLUGIN_ID = 'claude'
const CHAT_ENDPOINT = '/api/v1/ai/chat'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * Reactive Claude chat composable.
 * Each call creates a new session (unique sessionId per instance).
 * Call inside setup() context for onMounted lifecycle support.
 */
export function useClaude(): UseClaudeReturn {
  const authStore = useAuthStore()

  /** Unique session identifier for this composable instance */
  const sessionId = crypto.randomUUID()

  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const isAvailable = ref(false)

  // ─── Availability check ───────────────────────────────────────────────────

  async function checkAvailability(): Promise<void> {
    try {
      const plugins = await pluginsApi.list()
      const claudePlugin = plugins.find((p) => p.plugin_id === CLAUDE_PLUGIN_ID)
      isAvailable.value = claudePlugin?.is_enabled === true
    } catch {
      isAvailable.value = false
    }
  }

  // ─── SSE Streaming ────────────────────────────────────────────────────────

  /**
   * Parse a single SSE line and extract the data payload string.
   * Returns null for comment lines, empty lines, or non-data lines.
   */
  function parseSseLine(line: string): string | null {
    if (!line.startsWith('data:')) return null
    const payload = line.slice(5).trim()
    if (payload === '[DONE]') return null
    return payload
  }

  /**
   * Read a SSE ReadableStream and accumulate chunks into the last assistant message.
   */
  async function consumeStream(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<void> {
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        // Keep the last (potentially incomplete) line in the buffer
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          const chunk = parseSseLine(line)
          if (chunk === null) continue

          // Append chunk to the last assistant message
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg?.role === 'assistant') {
            lastMsg.content += chunk
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }

  // ─── Public API ───────────────────────────────────────────────────────────

  /**
   * Send a user message and stream the assistant response.
   * The token is read directly from the auth store to mirror the Axios interceptor pattern.
   */
  async function sendMessage(text: string, context?: ClaudeContext): Promise<void> {
    if (isStreaming.value || !text.trim()) return

    const userMessage: ChatMessage = {
      role: 'user',
      content: text.trim(),
      timestamp: new Date().toISOString(),
    }
    messages.value.push(userMessage)

    const assistantMessage: ChatMessage = {
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
    }
    messages.value.push(assistantMessage)
    isStreaming.value = true

    try {
      const token = authStore.accessToken
      const requestBody: Record<string, unknown> = {
        message: text.trim(),
        session_id: sessionId,
      }
      if (context?.espId) requestBody.esp_id = context.espId
      if (context) requestBody.context = context

      const response = await fetch(CHAT_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok || !response.body) {
        const errorText = await response.text().catch(() => 'Unbekannter Fehler')
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg?.role === 'assistant') {
          lastMsg.content = `Fehler: ${response.status} — ${errorText}`
          lastMsg.isStreaming = false
        }
        return
      }

      const reader = response.body.getReader()
      await consumeStream(reader)
    } catch (err) {
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg?.role === 'assistant') {
        lastMsg.content = `Verbindungsfehler: ${err instanceof Error ? err.message : 'Unbekannt'}`
      }
    } finally {
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg?.role === 'assistant') {
        lastMsg.isStreaming = false
      }
      isStreaming.value = false
    }
  }

  /** Clear the local message history (does not affect server-side session). */
  function clearHistory(): void {
    messages.value = []
  }

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  onMounted(() => {
    checkAvailability()
  })

  return {
    messages,
    isStreaming,
    isAvailable,
    sendMessage,
    clearHistory,
    sessionId,
  }
}
