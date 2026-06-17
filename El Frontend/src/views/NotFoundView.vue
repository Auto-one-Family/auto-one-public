<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { SearchX } from 'lucide-vue-next'

const route = useRoute()

const sourcePath = computed(() => {
  const from = route.query.from
  if (typeof from === 'string' && from.trim().length > 0) {
    return from
  }
  return route.fullPath
})
</script>

<template>
  <section class="not-found">
    <div class="not-found__card glass-panel">
      <SearchX class="not-found__icon" aria-hidden="true" />
      <h1 class="not-found__title">Route nicht gefunden</h1>
      <p class="not-found__text">
        Der angeforderte Pfad existiert nicht oder wurde verschoben.
      </p>
      <p class="not-found__path" aria-label="Angeforderter Pfad">
        {{ sourcePath }}
      </p>

      <div class="not-found__actions">
        <RouterLink to="/hardware" class="btn-primary">
          Zur Hardware-Uebersicht
        </RouterLink>
        <RouterLink to="/monitor" class="btn-secondary">
          Zum Live-Monitor
        </RouterLink>
        <RouterLink to="/sensors" class="btn-secondary">
          Zur Wissensdatenbank
        </RouterLink>
      </div>

      <p class="not-found__hint">
        Falls du ueber einen Lesezeichen-Link hier gelandet bist, wurde die Route
        moeglicherweise umbenannt. Pruefe den Pfad oder waehle einen Bereich oben.
      </p>
    </div>
  </section>
</template>

<style scoped>
.not-found {
  min-height: calc(100vh - var(--header-height));
  display: grid;
  place-items: center;
  padding: var(--space-6);
}

.not-found__card {
  width: min(640px, 100%);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  border: 1px solid var(--glass-border);
  text-align: center;
}

.not-found__icon {
  width: 40px;
  height: 40px;
  color: var(--color-warning);
  margin: 0 auto var(--space-4);
}

.not-found__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.not-found__text {
  color: var(--color-text-secondary);
}

.not-found__path {
  margin-top: var(--space-3);
  font-family: var(--font-family-mono);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  word-break: break-word;
}

.not-found__actions {
  margin-top: var(--space-5);
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  flex-wrap: wrap;
}

.not-found__hint {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--glass-border);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  line-height: 1.5;
}
</style>
