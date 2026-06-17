<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ShieldX } from 'lucide-vue-next'

const route = useRoute()

const deniedTarget = computed(() => {
  const from = route.query.from
  if (typeof from === 'string' && from.trim().length > 0) {
    return from
  }
  return '/system-monitor'
})
</script>

<template>
  <section class="access-denied">
    <div class="access-denied__card glass-panel">
      <ShieldX class="access-denied__icon" aria-hidden="true" />
      <h1 class="access-denied__title">Zugriff verweigert</h1>
      <p class="access-denied__text">
        Fuer diesen Bereich fehlen die erforderlichen Berechtigungen.
      </p>
      <p class="access-denied__path" aria-label="Angeforderter Admin-Pfad">
        {{ deniedTarget }}
      </p>

      <div class="access-denied__actions">
        <RouterLink to="/hardware" class="btn-primary">
          Zur Uebersicht
        </RouterLink>
        <RouterLink to="/settings" class="btn-secondary">
          Zu Einstellungen
        </RouterLink>
      </div>

      <p class="access-denied__contact">
        Du benoetigst Admin-Rechte fuer diesen Bereich? Wende dich an einen
        bestehenden Administrator. Die Verwaltung der Berechtigungen erfolgt
        unter <RouterLink to="/users" class="access-denied__contact-link">Benutzer-Verwaltung</RouterLink>.
      </p>
    </div>
  </section>
</template>

<style scoped>
.access-denied {
  min-height: calc(100vh - var(--header-height));
  display: grid;
  place-items: center;
  padding: var(--space-6);
}

.access-denied__card {
  width: min(640px, 100%);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  border: 1px solid var(--glass-border);
  text-align: center;
}

.access-denied__icon {
  width: 40px;
  height: 40px;
  color: var(--color-error);
  margin: 0 auto var(--space-4);
}

.access-denied__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.access-denied__text {
  color: var(--color-text-secondary);
}

.access-denied__path {
  margin-top: var(--space-3);
  font-family: var(--font-family-mono);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  word-break: break-word;
}

.access-denied__actions {
  margin-top: var(--space-5);
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  flex-wrap: wrap;
}

.access-denied__contact {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--glass-border);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.access-denied__contact-link {
  color: var(--color-iridescent-1);
  text-decoration: none;
}

.access-denied__contact-link:hover {
  text-decoration: underline;
}
</style>
