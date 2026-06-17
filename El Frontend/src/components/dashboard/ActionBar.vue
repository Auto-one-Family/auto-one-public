<script setup lang="ts">
/**
 * ActionBar Component
 *
 * Consolidated dashboard control bar with three clear sections:
 * LEFT:   Status filter pills (Online | Offline | Warning | SafeMode)
 * CENTER: Type filter segmented control (All / Mock / Real)
 * RIGHT:  Action buttons (Pending devices, +Mock)
 *
 * Design: Industrial precision instrument aesthetic.
 * No Tailwind utility classes - pure BEM with CSS custom properties.
 */

import { computed } from 'vue'
import { Plus, Sparkles, Radio, AlertTriangle } from 'lucide-vue-next'
import StatusPill from './StatusPill.vue'

type StatusFilter = 'online' | 'offline' | 'warning' | 'safemode'
type TypeFilter = 'all' | 'mock' | 'real'

interface Props {
  onlineCount: number
  offlineCount: number
  warningCount: number
  safeModeCount: number
  pendingCount?: number
  activeFilters: Set<StatusFilter>
  hasProblems?: boolean
  problemMessage?: string
  filterType?: TypeFilter
  totalCount?: number
  mockCount?: number
  realCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  hasProblems: false,
  problemMessage: '',
  pendingCount: 0,
  filterType: 'all',
  totalCount: 0,
  mockCount: 0,
  realCount: 0
})

const emit = defineEmits<{
  toggleFilter: [filter: StatusFilter]
  'update:filterType': [filter: TypeFilter]
  createMockEsp: []
  openPendingDevices: [event: MouseEvent]
}>()

const hasPendingDevices = computed(() => props.pendingCount > 0)
const isFilterActive = (filter: StatusFilter) => props.activeFilters.has(filter)
</script>

<template>
  <div
    :class="[
      'action-bar',
      {
        'action-bar--alert': hasProblems && warningCount > 0
      }
    ]"
  >
    <!-- Problem Indicator Strip (subtle top accent) -->
    <div
      v-if="hasProblems && problemMessage"
      class="action-bar__alert-strip"
    >
      <AlertTriangle class="action-bar__alert-icon" />
      <span class="action-bar__alert-text">{{ problemMessage }}</span>
    </div>

    <!-- Main Bar Content -->
    <div class="action-bar__content">
      <!-- LEFT: Status Filter Pills -->
      <div class="action-bar__filters">
        <StatusPill
          type="online"
          :count="onlineCount"
          label="Online"
          :active="isFilterActive('online')"
          @click="emit('toggleFilter', 'online')"
        />
        <StatusPill
          type="offline"
          :count="offlineCount"
          label="Offline"
          :active="isFilterActive('offline')"
          @click="emit('toggleFilter', 'offline')"
        />
        <StatusPill
          v-if="warningCount > 0"
          type="warning"
          :count="warningCount"
          label="Fehler"
          :active="isFilterActive('warning')"
          @click="emit('toggleFilter', 'warning')"
        />
        <StatusPill
          v-if="safeModeCount > 0"
          type="safemode"
          :count="safeModeCount"
          label="Safe Mode"
          :active="isFilterActive('safemode')"
          @click="emit('toggleFilter', 'safemode')"
        />
      </div>

      <!-- CENTER: Type Filter Segmented Control -->
      <div class="action-bar__type-filter">
        <div class="type-segment">
          <button
            :class="['type-segment__btn', { 'type-segment__btn--active': filterType === 'all' }]"
            @click="emit('update:filterType', 'all')"
          >
            Alle
            <span class="type-segment__count">{{ totalCount }}</span>
          </button>
          <button
            :class="[
              'type-segment__btn',
              'type-segment__btn--mock',
              { 'type-segment__btn--active': filterType === 'mock' }
            ]"
            @click="emit('update:filterType', 'mock')"
          >
            Mock
            <span class="type-segment__count">{{ mockCount }}</span>
          </button>
          <button
            :class="[
              'type-segment__btn',
              'type-segment__btn--real',
              { 'type-segment__btn--active': filterType === 'real' }
            ]"
            @click="emit('update:filterType', 'real')"
          >
            Real
            <span class="type-segment__count">{{ realCount }}</span>
          </button>
        </div>
      </div>

      <!-- RIGHT: Action Buttons -->
      <div class="action-bar__actions">
        <!-- Pending Devices Button -->
        <button
          :class="[
            'action-btn',
            hasPendingDevices ? 'action-btn--pending' : 'action-btn--default'
          ]"
          :title="hasPendingDevices ? 'Neue Geräte warten auf Genehmigung' : 'Geräte verwalten'"
          @click="(e) => emit('openPendingDevices', e)"
        >
          <component
            :is="hasPendingDevices ? Sparkles : Radio"
            class="action-btn__icon"
          />
          <span class="action-btn__label">
            {{ hasPendingDevices ? `${pendingCount} Neue` : 'Geräte' }}
          </span>
        </button>

        <!-- Create Mock ESP -->
        <button
          class="action-btn action-btn--create"
          title="Test-ESP erstellen"
          @click="emit('createMockEsp')"
        >
          <Plus class="action-btn__icon" />
          <span class="action-btn__label">Mock</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   ACTION BAR — Industrial Control Strip
   Token-aligned spacing, consistent elevation
   ═══════════════════════════════════════════════════════════════════════════ */

.action-bar {
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: border-color var(--transition-base);
}

.action-bar--alert {
  border-color: rgba(245, 158, 11, 0.3);
}

/* ── Alert Strip ── */
.action-bar__alert-strip {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-4);
  background: rgba(245, 158, 11, 0.06);
  border-bottom: 1px solid rgba(245, 158, 11, 0.12);
  font-size: var(--text-sm);
  color: var(--color-warning);
}

.action-bar__alert-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.action-bar__alert-text {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Main Content Row ── */
.action-bar__content {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
}

/* ── Left: Status Filters ── */
.action-bar__filters {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

/* ── Center: Type Filter ── */
.action-bar__type-filter {
  margin-left: auto;
  flex-shrink: 0;
}

.type-segment {
  display: flex;
  gap: 2px;
  background: var(--color-bg-primary);
  padding: 3px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.type-segment__btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 5px 10px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.type-segment__btn:hover {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
}

.type-segment__btn--active {
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.type-segment__btn--mock.type-segment__btn--active {
  color: var(--color-mock);
}

.type-segment__btn--real.type-segment__btn--active {
  color: var(--color-real);
}

.type-segment__count {
  font-size: var(--text-xs);
  font-variant-numeric: tabular-nums;
  opacity: 0.6;
}

.type-segment__btn--active .type-segment__count {
  opacity: 1;
}

/* ── Right: Action Buttons ── */
.action-bar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-left: var(--space-1);
  flex-shrink: 0;
}

/* ── Action Button Base ── */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 6px var(--space-3);
  font-size: var(--text-sm);
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.action-btn__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.action-btn__label {
  display: none;
}

@media (min-width: 768px) {
  .action-btn__label {
    display: inline;
  }
}

/* ── Default State (Devices Button) ── */
.action-btn--default {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--glass-border);
}

.action-btn--default:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--glass-border-hover);
}

/* ── Pending State (Pulsing Iridescent) ── */
.action-btn--pending {
  position: relative;
  color: white;
  background: linear-gradient(
    135deg,
    rgba(96, 165, 250, 0.15) 0%,
    rgba(129, 140, 248, 0.15) 50%,
    rgba(167, 139, 250, 0.15) 100%
  );
  border-color: transparent;
  overflow: hidden;
  animation: iridescent-pulse 3s ease-in-out infinite;
}

.action-btn--pending::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: var(--gradient-iridescent);
  -webkit-mask:
    linear-gradient(white 0 0) content-box,
    linear-gradient(white 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  animation: iridescent-shift 3s ease-in-out infinite;
  pointer-events: none;
}

.action-btn--pending::after {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 50%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.06),
    transparent
  );
  animation: shimmer 3s ease-in-out infinite;
  pointer-events: none;
}

.action-btn--pending:hover {
  transform: translateY(-1px);
  box-shadow:
    0 4px 12px rgba(96, 165, 250, 0.2),
    0 0 16px rgba(129, 140, 248, 0.1);
}

/* ── Create Mock Button ── */
.action-btn--create {
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.06);
  border-color: rgba(52, 211, 153, 0.15);
}

.action-btn--create:hover {
  background: rgba(52, 211, 153, 0.12);
  border-color: rgba(52, 211, 153, 0.3);
}

/* ── Responsive: Stack on small screens ── */
@media (max-width: 640px) {
  .action-bar__content {
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .action-bar__filters {
    order: 1;
    flex: 1;
  }

  .action-bar__actions {
    order: 2;
    margin-left: auto;
  }

  .action-bar__type-filter {
    order: 3;
    width: 100%;
    margin-left: 0;
  }

  .type-segment {
    width: 100%;
  }

  .type-segment__btn {
    flex: 1;
    justify-content: center;
  }
}
</style>
