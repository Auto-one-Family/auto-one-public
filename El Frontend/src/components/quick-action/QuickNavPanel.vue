<script setup lang="ts">
/**
 * QuickNavPanel — Navigation sub-panel in the FAB.
 *
 * Shows MRU (Most Recently Used) routes, favorites,
 * and a Quick-Search trigger for the command palette.
 *
 * Data source: useNavigationHistory composable (localStorage-backed).
 */

import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  Star,
  StarOff,
  Search,
  Clock,
  ChevronRight,
} from 'lucide-vue-next'
import { useNavigationHistory } from '@/composables/useNavigationHistory'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import { useUiStore } from '@/shared/stores/ui.store'

const router = useRouter()
const quickActionStore = useQuickActionStore()
const uiStore = useUiStore()
const { recentNavItems, favorites, isFavorite, toggleFavorite } = useNavigationHistory()

function handleBack(): void {
  quickActionStore.setActivePanel('menu')
}

function handleNavigate(path: string): void {
  void router.push(path)
  quickActionStore.closeMenu()
}

function handleQuickSearch(): void {
  quickActionStore.closeMenu()
  uiStore.toggleCommandPalette()
}
</script>

<template>
  <div class="qa-nav-panel" role="region" aria-label="Quick Navigation">
    <!-- Header -->
    <div class="qa-nav-panel__header">
      <button class="qa-nav-panel__back" aria-label="Zurück" @click="handleBack">
        <ArrowLeft class="qa-nav-panel__back-icon" />
      </button>
      <span class="qa-nav-panel__title">Navigation</span>
    </div>

    <!-- Quick Search -->
    <button class="qa-nav-panel__search" @click="handleQuickSearch">
      <Search class="qa-nav-panel__search-icon" />
      <span>Suche...</span>
      <kbd class="qa-nav-panel__kbd">Ctrl+K</kbd>
    </button>

    <!-- Favorites -->
    <div v-if="favorites.length > 0" class="qa-nav-panel__section">
      <span class="qa-nav-panel__section-label">
        <Star class="qa-nav-panel__section-icon" />
        Favoriten
      </span>
      <div
        v-for="fav in favorites"
        :key="fav.path"
        class="nav-item"
        @click="handleNavigate(fav.path)"
      >
        <component :is="fav.icon" class="nav-item__icon" />
        <span class="nav-item__label">{{ fav.label }}</span>
        <button
          class="nav-item__star nav-item__star--active"
          title="Favorit entfernen"
          @click.stop="toggleFavorite(fav.path)"
        >
          <Star class="nav-item__star-icon" />
        </button>
      </div>
    </div>

    <!-- Recent -->
    <div v-if="recentNavItems.length > 0" class="qa-nav-panel__section">
      <span class="qa-nav-panel__section-label">
        <Clock class="qa-nav-panel__section-icon" />
        Zuletzt besucht
      </span>
      <div
        v-for="item in recentNavItems"
        :key="item.path"
        class="nav-item"
        @click="handleNavigate(item.path)"
      >
        <component :is="item.icon" class="nav-item__icon" />
        <span class="nav-item__label">{{ item.label }}</span>
        <div class="nav-item__actions">
          <button
            class="nav-item__star"
            :class="{ 'nav-item__star--active': isFavorite(item.path) }"
            :title="isFavorite(item.path) ? 'Favorit entfernen' : 'Als Favorit merken'"
            @click.stop="toggleFavorite(item.path)"
          >
            <Star v-if="isFavorite(item.path)" class="nav-item__star-icon" />
            <StarOff v-else class="nav-item__star-icon" />
          </button>
          <ChevronRight class="nav-item__chevron" />
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="recentNavItems.length === 0 && favorites.length === 0" class="qa-nav-panel__empty">
      <span>Noch keine Navigation aufgezeichnet</span>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   QUICK NAV PANEL — Sub-panel inside the FAB
   ═══════════════════════════════════════════════════════════════════════════ */

.qa-nav-panel {
  position: absolute;
  bottom: calc(100% + var(--space-2));
  right: 0;
  width: 280px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-md);
  background: rgba(20, 20, 30, 0.9);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border: 1px solid var(--glass-border);
  box-shadow: var(--elevation-floating);
  transform-origin: bottom right;
  overflow: hidden;
}

/* ── Header ── */

.qa-nav-panel__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.qa-nav-panel__back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qa-nav-panel__back:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
}

.qa-nav-panel__back-icon {
  width: 14px;
  height: 14px;
}

.qa-nav-panel__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
}

/* ── Quick Search ── */

.qa-nav-panel__search {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-2) var(--space-2) 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qa-nav-panel__search:hover {
  border-color: var(--glass-border-hover);
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-secondary);
}

.qa-nav-panel__search-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.qa-nav-panel__kbd {
  margin-left: auto;
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  padding: 1px 5px;
  border-radius: var(--radius-xs);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--glass-border);
  color: var(--color-text-muted);
}

/* ── Section ── */

.qa-nav-panel__section {
  padding: var(--space-1) var(--space-2);
}

.qa-nav-panel__section-label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xxs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  opacity: 0.6;
}

.qa-nav-panel__section-icon {
  width: 10px;
  height: 10px;
}

/* ── Nav Item ── */

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.nav-item__icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.nav-item__label {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-item__actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.nav-item__star {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  opacity: 0;
  transition: all var(--transition-fast);
}

.nav-item:hover .nav-item__star {
  opacity: 1;
}

.nav-item__star:hover {
  color: var(--color-warning);
  background: rgba(255, 255, 255, 0.08);
}

.nav-item__star--active {
  opacity: 1;
  color: var(--color-warning);
}

.nav-item__star-icon {
  width: 12px;
  height: 12px;
}

.nav-item__chevron {
  width: 12px;
  height: 12px;
  color: var(--color-text-muted);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.nav-item:hover .nav-item__chevron {
  opacity: 0.6;
}

/* ── Empty State ── */

.qa-nav-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6) var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
</style>
