<script setup lang="ts">
/**
 * ClaudeChatWidget — AI-powered debugging and stack analysis widget (AUT-272)
 *
 * Renders a chat interface for the Claude AI backend within the dashboard widget system.
 * Streaming responses are displayed character-by-character via SSE.
 *
 * Props: optional espId for context-aware queries (e.g. "what is wrong with this ESP?").
 * Empty-state: shown when the "claude" plugin is disabled or not configured.
 *
 * @see src/composables/useClaude.ts
 * @see El Servador/god_kaiser_server/src/api/v1/ai.py
 */
import { ref, nextTick, watch } from 'vue'
import { Sparkles, Send, Trash2 } from 'lucide-vue-next'
import { useClaude, type ClaudeContext } from '@/composables/useClaude'

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  /** Optional ESP ID to attach as context to all messages. */
  espId?: string
}

const props = withDefaults(defineProps<Props>(), {
  espId: undefined,
})

// ─── Composable ──────────────────────────────────────────────────────────────

const { messages, isStreaming, isAvailable, sendMessage, clearHistory } = useClaude()

// ─── Local State ─────────────────────────────────────────────────────────────

const inputText = ref('')
const chatContainer = ref<HTMLElement | null>(null)

// ─── Scroll to bottom on new messages ────────────────────────────────────────

watch(
  () => messages.value.length,
  () => {
    nextTick(() => {
      if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight
      }
    })
  },
)

// ─── Methods ─────────────────────────────────────────────────────────────────

function buildContext(): ClaudeContext | undefined {
  if (!props.espId) return undefined
  return { espId: props.espId, currentView: 'dashboard' }
}

async function handleSend(): Promise<void> {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return
  inputText.value = ''
  await sendMessage(text, buildContext())
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

function handleClear(): void {
  clearHistory()
}
</script>

<template>
  <div class="claude-chat">
    <!-- Not available empty state -->
    <div v-if="!isAvailable" class="claude-chat__unavailable">
      <Sparkles class="claude-chat__unavailable-icon" />
      <p class="claude-chat__unavailable-title">Claude nicht konfiguriert</p>
      <p class="claude-chat__unavailable-body">
        Das Claude-Plugin ist nicht aktiviert. Aktiviere es unter
        <strong>Einstellungen → Plugins</strong>.
      </p>
    </div>

    <!-- Chat interface -->
    <template v-else>
      <!-- Header actions -->
      <div class="claude-chat__toolbar">
        <span class="claude-chat__toolbar-label">
          <Sparkles class="claude-chat__toolbar-icon" />
          Claude Assistant
          <span v-if="props.espId" class="claude-chat__context-chip">
            {{ props.espId }}
          </span>
        </span>
        <button
          type="button"
          class="claude-chat__clear-btn"
          title="Verlauf löschen"
          :disabled="messages.length === 0 || isStreaming"
          @click="handleClear"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </button>
      </div>

      <!-- Message history -->
      <div ref="chatContainer" class="claude-chat__messages">
        <!-- Empty state -->
        <div v-if="messages.length === 0" class="claude-chat__empty">
          <Sparkles class="claude-chat__empty-icon" />
          <p class="claude-chat__empty-hint">Stelle eine Frage zum System, zu Sensoren oder zu Anomalien.</p>
        </div>

        <template v-else>
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="[
              'claude-chat__message',
              msg.role === 'user' ? 'claude-chat__message--user' : 'claude-chat__message--assistant',
            ]"
          >
            <span
              class="claude-chat__bubble"
              :class="{ 'claude-chat__bubble--streaming': msg.isStreaming }"
            >{{ msg.content }}<span v-if="msg.isStreaming" class="claude-chat__cursor animate-breathe" /></span>
          </div>
        </template>
      </div>

      <!-- Input area -->
      <div class="claude-chat__input-area">
        <textarea
          v-model="inputText"
          class="claude-chat__textarea"
          placeholder="Nachricht eingeben… (Enter = Senden, Shift+Enter = Zeilenumbruch)"
          rows="2"
          :disabled="isStreaming"
          @keydown="handleKeydown"
        />
        <button
          type="button"
          class="claude-chat__send-btn"
          title="Senden"
          :disabled="!inputText.trim() || isStreaming"
          @click="handleSend"
        >
          <Send class="w-4 h-4" />
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.claude-chat {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-size: var(--text-sm);
}

/* ─── Unavailable ─── */

.claude-chat__unavailable {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 100%;
  padding: var(--space-4);
  color: var(--color-text-muted);
  text-align: center;
}

.claude-chat__unavailable-icon {
  width: 32px;
  height: 32px;
  color: var(--color-iridescent-3);
  opacity: 0.5;
}

.claude-chat__unavailable-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.claude-chat__unavailable-body {
  font-size: var(--text-xs);
  line-height: 1.5;
}

/* ─── Toolbar ─── */

.claude-chat__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.claude-chat__toolbar-label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.claude-chat__toolbar-icon {
  width: 14px;
  height: 14px;
  color: var(--color-iridescent-3);
}

.claude-chat__context-chip {
  font-size: var(--text-xs);
  background: rgba(167, 139, 250, 0.12);
  color: var(--color-iridescent-3);
  border: 1px solid rgba(167, 139, 250, 0.25);
  padding: 1px var(--space-1);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-weight: 400;
}

.claude-chat__clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.claude-chat__clear-btn:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.1);
  color: var(--color-error);
}

.claude-chat__clear-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* ─── Messages ─── */

.claude-chat__messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.claude-chat__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--space-2);
  color: var(--color-text-muted);
}

.claude-chat__empty-icon {
  width: 24px;
  height: 24px;
  opacity: 0.3;
  color: var(--color-iridescent-3);
}

.claude-chat__empty-hint {
  font-size: var(--text-xs);
  text-align: center;
  max-width: 220px;
}

.claude-chat__message {
  display: flex;
}

.claude-chat__message--user {
  justify-content: flex-end;
}

.claude-chat__message--assistant {
  justify-content: flex-start;
}

.claude-chat__bubble {
  max-width: 80%;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.claude-chat__message--user .claude-chat__bubble {
  background: rgba(96, 165, 250, 0.15);
  color: var(--color-text-primary);
  border: 1px solid rgba(96, 165, 250, 0.2);
}

.claude-chat__message--assistant .claude-chat__bubble {
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
}

.claude-chat__cursor {
  display: inline-block;
  width: 6px;
  height: 12px;
  background: var(--color-iridescent-3);
  border-radius: 1px;
  vertical-align: middle;
  margin-left: 2px;
  opacity: 0.8;
}

/* ─── Input area ─── */

.claude-chat__input-area {
  display: flex;
  align-items: flex-end;
  gap: var(--space-1);
  padding: var(--space-2);
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.claude-chat__textarea {
  flex: 1;
  resize: none;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-xs);
  font-family: inherit;
  padding: var(--space-1) var(--space-2);
  outline: none;
  transition: border-color 0.15s;
  line-height: 1.4;
}

.claude-chat__textarea:focus {
  border-color: var(--color-iridescent-3);
}

.claude-chat__textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.claude-chat__textarea::placeholder {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.claude-chat__send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: rgba(167, 139, 250, 0.2);
  color: var(--color-iridescent-3);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.claude-chat__send-btn:hover:not(:disabled) {
  background: rgba(167, 139, 250, 0.35);
  color: var(--color-iridescent-2);
}

.claude-chat__send-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
