<script setup lang="ts">
/**
 * TroubleshootingPanel - Zeigt Troubleshooting-Schritte für Fehler
 *
 * Wird verwendet in:
 * - ErrorDetailsModal (primär)
 * - EventDetailsPanel (für error_event Typ)
 *
 * Server-Centric: Troubleshooting-Schritte kommen vom Server
 * (esp32_error_mapping.py), Frontend zeigt nur an.
 */

import { AlertTriangle, CheckCircle2 } from 'lucide-vue-next'
import type { ErrorSeverity } from '@/utils/errorCodeTranslator'

interface Props {
  steps: string[]
  userActionRequired: boolean
  severity?: ErrorSeverity
}

defineProps<Props>()
</script>

<template>
  <div class="troubleshooting-panel" :class="[`troubleshooting-panel--${severity || 'error'}`]">
    <!-- Action Required Badge -->
    <div v-if="userActionRequired" class="action-required-badge">
      <AlertTriangle :size="14" />
      <span>Handlungsbedarf</span>
    </div>

    <!-- Steps -->
    <div v-if="steps.length > 0" class="troubleshooting-steps">
      <div class="steps-label">Troubleshooting-Schritte:</div>
      <ol class="steps-list">
        <li v-for="(step, index) in steps" :key="index" class="step-item">
          <span class="step-number">{{ index + 1 }}</span>
          <span class="step-text">{{ step }}</span>
        </li>
      </ol>
    </div>

    <!-- No action required hint -->
    <div v-if="!userActionRequired && steps.length > 0" class="auto-resolve-hint">
      <CheckCircle2 :size="14" />
      <span>Dieser Fehler kann sich automatisch beheben</span>
    </div>
  </div>
</template>

<style scoped>
.troubleshooting-panel {
  padding: 0.875rem 1rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.troubleshooting-panel--critical {
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(220, 38, 38, 0.06);
}

.troubleshooting-panel--error {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.04);
}

.troubleshooting-panel--warning {
  border-color: rgba(245, 158, 11, 0.2);
  background: rgba(245, 158, 11, 0.04);
}

.action-required-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  border-radius: var(--radius-full);
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  background: rgba(220, 38, 38, 0.15);
  color: var(--color-error);
  border: 1px solid rgba(220, 38, 38, 0.25);
  margin-bottom: 0.75rem;
}

.steps-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.5rem;
}

.steps-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
}

.step-number {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.375rem;
  height: 1.375rem;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  font-size: 0.6875rem;
  font-weight: 700;
  color: var(--color-text-secondary);
}

.step-text {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--color-text-secondary);
  padding-top: 0.1rem;
}

.auto-resolve-hint {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.75rem;
  font-size: 0.75rem;
  color: var(--color-success);
  opacity: 0.8;
}
</style>
