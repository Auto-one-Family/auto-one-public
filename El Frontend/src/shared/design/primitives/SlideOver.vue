<script setup lang="ts">
/**
 * SlideOver — Slide-in Panel from Right
 *
 * Used for configuration panels (Sensor, Actuator, ESP, Zone).
 * Slides in from the right edge with a semi-transparent backdrop.
 *
 * Features:
 * - 300ms CSS slide-in/out animation
 * - Click outside (backdrop) closes panel
 * - ESC key closes panel
 * - Three width variants: sm (320px), md (400px), lg (560px)
 * - Mobile: 100% width
 * - Teleported to body to avoid z-index issues
 */

import { ref, watch, onMounted, onUnmounted } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  /** Whether the panel is open */
  open: boolean
  /** Panel header title */
  title?: string
  /** Optional one-line context under the title (e.g. operator hints) */
  subtitle?: string
  /** Panel width variant */
  width?: 'sm' | 'md' | 'lg'
  /** Elevation for stacked modals: 'default' | 'high' (z-index +10 when opened over another SlideOver) */
  elevation?: 'default' | 'high'
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  subtitle: '',
  width: 'md',
  elevation: 'default',
})

const emit = defineEmits<{
  close: []
}>()

const openedAt = ref(0)

function handleBackdropClick(e: MouseEvent) {
  if (e.target !== e.currentTarget) return
  // Ignore ghost-clicks fired ~300ms after a touch event opened this panel
  if (Date.now() - openedAt.value < 350) return
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})

// Prevent body scroll when open; record timestamp to guard against ghost-clicks
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    openedAt.value = Date.now()
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
}, { immediate: true })

onUnmounted(() => {
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="slide-over-fade">
      <div
        v-if="open"
        :class="['slide-over-backdrop', { 'slide-over-backdrop--high': elevation === 'high' }]"
        @click="handleBackdropClick"
      >
        <Transition name="slide-over-panel" appear>
          <div
            v-if="open"
            :class="['slide-over', `slide-over--${width}`]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sheet-title"
          >
            <!-- Header -->
            <header class="slide-over__header">
              <div class="slide-over__title-block">
                <h2 id="sheet-title" class="slide-over__title">{{ title }}</h2>
                <p
                  v-if="subtitle"
                  class="slide-over__subtitle"
                >
                  {{ subtitle }}
                </p>
              </div>
              <button
                class="slide-over__close"
                aria-label="Schließen"
                title="Schließen (ESC)"
                @click="emit('close')"
              >
                <X class="w-5 h-5" />
              </button>
            </header>

            <!-- Content -->
            <div class="slide-over__content">
              <slot />
            </div>

            <!-- Footer (optional slot) -->
            <footer v-if="$slots.footer" class="slide-over__footer">
              <slot name="footer" />
            </footer>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   BACKDROP
   ═══════════════════════════════════════════════════════════════════════════ */

.slide-over-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: var(--slide-over-backdrop);
  display: flex;
  justify-content: flex-end;
}

.slide-over-backdrop--high {
  z-index: calc(var(--z-modal) + 10);
}

/* Backdrop fade transition */
.slide-over-fade-enter-active,
.slide-over-fade-leave-active {
  transition: opacity var(--slide-over-duration) var(--ease-out);
}

.slide-over-fade-enter-from,
.slide-over-fade-leave-to {
  opacity: 0;
}

/* ═══════════════════════════════════════════════════════════════════════════
   PANEL
   ═══════════════════════════════════════════════════════════════════════════ */

.slide-over {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-secondary);
  border-left: 1px solid var(--glass-border);
  box-shadow: -8px 0 32px rgba(0, 0, 0, 0.4);
  overflow: hidden;
}

.slide-over--sm {
  width: var(--slide-over-width-sm);
}

.slide-over--md {
  width: var(--slide-over-width-md);
}

.slide-over--lg {
  width: var(--slide-over-width-lg);
}

/* Panel slide transition */
.slide-over-panel-enter-active,
.slide-over-panel-leave-active {
  transition: transform var(--slide-over-duration) var(--ease-out);
}

.slide-over-panel-enter-from,
.slide-over-panel-leave-to {
  transform: translateX(100%);
}

/* ═══════════════════════════════════════════════════════════════════════════
   HEADER
   ═══════════════════════════════════════════════════════════════════════════ */

.slide-over__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.slide-over__title-block {
  flex: 1;
  min-width: 0;
}

.slide-over__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slide-over__subtitle {
  margin: var(--space-1) 0 0;
  font-size: var(--text-sm);
  font-weight: 400;
  line-height: 1.35;
  color: var(--color-text-secondary);
}

.slide-over__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.slide-over__close:hover {
  background: var(--glass-bg-light);
  color: var(--color-text-primary);
}

/* ═══════════════════════════════════════════════════════════════════════════
   CONTENT
   ═══════════════════════════════════════════════════════════════════════════ */

.slide-over__content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}

/* ═══════════════════════════════════════════════════════════════════════════
   FOOTER
   ═══════════════════════════════════════════════════════════════════════════ */

.slide-over__footer {
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}

/* ═══════════════════════════════════════════════════════════════════════════
   RESPONSIVE — Full width on mobile
   ═══════════════════════════════════════════════════════════════════════════ */

@media (max-width: 640px) {
  .slide-over--sm,
  .slide-over--md,
  .slide-over--lg {
    width: 100%;
  }
}
</style>
