<script setup lang="ts">
/**
 * NotificationPreferences — Settings panel for notification delivery
 *
 * Opens as a second SlideOver (width="md") on top of the drawer.
 * Features:
 * - Basic zone: WebSocket (Echtzeit-Updates), Email on/off, email address, severity checkboxes
 * - Advanced zone (AccordionSection): Quiet hours, digest interval, browser notifications
 * - Save button with loading state
 */

import { ref, watch } from 'vue'
import { Send, Clock, Bell, Radio } from 'lucide-vue-next'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import AccordionSection from '@/shared/design/primitives/AccordionSection.vue'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import {
  notificationsApi,
  type NotificationPreferencesDTO,
  type NotificationPreferencesUpdate,
} from '@/api/notifications'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'

const logger = createLogger('NotificationPreferences')
const toast = useToast()
const inboxStore = useNotificationInboxStore()

// Form state
const websocketEnabled = ref(true)
const emailEnabled = ref(false)
const emailAddress = ref('')
const emailSeverities = ref<string[]>(['critical', 'warning'])
const quietHoursEnabled = ref(false)
const quietHoursStart = ref('22:00')
const quietHoursEnd = ref('07:00')
const digestIntervalMinutes = ref(60)
const browserNotifications = ref(false)

const isLoading = ref(false)
const isSaving = ref(false)
const isSendingTest = ref(false)

const severityOptions = [
  { value: 'critical', label: 'Kritisch' },
  { value: 'warning', label: 'Warnung' },
  { value: 'info', label: 'Info' },
]

// Load preferences when panel opens
watch(
  () => inboxStore.isPreferencesOpen,
  async (isOpen) => {
    if (isOpen) {
      await loadPreferences()
    }
  },
)

async function loadPreferences(): Promise<void> {
  isLoading.value = true
  try {
    const prefs = await notificationsApi.getPreferences()
    applyPrefs(prefs)
  } catch (err) {
    logger.error('Failed to load preferences', err)
    toast.error('Einstellungen konnten nicht geladen werden')
  } finally {
    isLoading.value = false
  }
}

function applyPrefs(prefs: NotificationPreferencesDTO): void {
  websocketEnabled.value = prefs.websocket_enabled ?? true
  emailEnabled.value = prefs.email_enabled
  emailAddress.value = prefs.email_address || ''
  emailSeverities.value = prefs.email_severities || ['critical', 'warning']
  quietHoursEnabled.value = prefs.quiet_hours_enabled
  quietHoursStart.value = prefs.quiet_hours_start || '22:00'
  quietHoursEnd.value = prefs.quiet_hours_end || '07:00'
  digestIntervalMinutes.value = prefs.digest_interval_minutes
  browserNotifications.value = prefs.browser_notifications
}

async function save(): Promise<void> {
  isSaving.value = true
  try {
    const update: NotificationPreferencesUpdate = {
      websocket_enabled: websocketEnabled.value,
      email_enabled: emailEnabled.value,
      email_address: emailAddress.value || null,
      email_severities: emailSeverities.value,
      quiet_hours_enabled: quietHoursEnabled.value,
      quiet_hours_start: quietHoursStart.value,
      quiet_hours_end: quietHoursEnd.value,
      digest_interval_minutes: digestIntervalMinutes.value,
      browser_notifications: browserNotifications.value,
    }

    const prefs = await notificationsApi.updatePreferences(update)
    applyPrefs(prefs)
    toast.success('Einstellungen gespeichert')

    // Request browser notification permission if enabled
    if (browserNotifications.value && 'Notification' in window) {
      if (Notification.permission === 'default') {
        Notification.requestPermission()
      }
    }
  } catch (err) {
    logger.error('Failed to save preferences', err)
    toast.error('Einstellungen konnten nicht gespeichert werden')
  } finally {
    isSaving.value = false
  }
}

async function sendTestEmail(): Promise<void> {
  isSendingTest.value = true
  try {
    const res = await notificationsApi.sendTestEmail({
      email: emailAddress.value || null,
    })
    toast.success(res.message || 'Test-E-Mail gesendet')
  } catch (err) {
    logger.error('Failed to send test email', err)
    toast.error('Test-E-Mail konnte nicht gesendet werden')
  } finally {
    isSendingTest.value = false
  }
}

function toggleSeverity(severity: string): void {
  const idx = emailSeverities.value.indexOf(severity)
  if (idx >= 0) {
    emailSeverities.value.splice(idx, 1)
  } else {
    emailSeverities.value.push(severity)
  }
}

function handleClose(): void {
  inboxStore.closePreferences()
}
</script>

<template>
  <SlideOver
    :open="inboxStore.isPreferencesOpen"
    title="Benachrichtigungs-Einstellungen"
    width="md"
    @close="handleClose"
  >
    <template #default>
      <div v-if="isLoading" class="prefs__loading">
        Lade Einstellungen...
      </div>

      <div v-else class="prefs">
        <!-- ═══ Basic Zone: WebSocket + Email ═══ -->
        <div class="prefs__section">
          <div class="prefs__field">
            <div class="prefs__row">
              <label class="prefs__label">
                <Radio class="prefs__label-icon" />
                Echtzeit-Updates (WebSocket)
              </label>
              <button
                :class="['prefs__toggle', { 'prefs__toggle--active': websocketEnabled }]"
                @click="websocketEnabled = !websocketEnabled"
              >
                <span class="prefs__toggle-dot" />
              </button>
            </div>
            <p class="prefs__hint">
              Neue Alerts sofort im Browser anzeigen. Wenn ausgeschaltet, werden Alerts nur beim manuellen Aktualisieren geladen.
            </p>
          </div>

          <div class="prefs__row">
            <label class="prefs__label">
              <Send class="prefs__label-icon" />
              E-Mail-Benachrichtigungen
            </label>
            <button
              :class="['prefs__toggle', { 'prefs__toggle--active': emailEnabled }]"
              @click="emailEnabled = !emailEnabled"
            >
              <span class="prefs__toggle-dot" />
            </button>
          </div>

          <div v-if="emailEnabled" class="prefs__sub-section">
            <div class="prefs__field">
              <label class="prefs__field-label">E-Mail-Adresse</label>
              <input
                v-model="emailAddress"
                type="email"
                class="prefs__input"
                placeholder="name@example.com"
              />
            </div>

            <div class="prefs__field">
              <label class="prefs__field-label">Schweregrad für E-Mail</label>
              <div class="prefs__checkboxes">
                <label
                  v-for="opt in severityOptions"
                  :key="opt.value"
                  class="prefs__checkbox"
                >
                  <input
                    type="checkbox"
                    :checked="emailSeverities.includes(opt.value)"
                    @change="toggleSeverity(opt.value)"
                  />
                  <span class="prefs__checkbox-label">{{ opt.label }}</span>
                </label>
              </div>
            </div>

            <button
              class="prefs__test-btn"
              :disabled="isSendingTest || !emailAddress"
              @click="sendTestEmail"
            >
              {{ isSendingTest ? 'Sende...' : 'Test-E-Mail senden' }}
            </button>
          </div>
        </div>

        <!-- ═══ Advanced Zone ═══ -->
        <AccordionSection
          title="Erweiterte Einstellungen"
          :icon="Clock"
          storage-key="ao-notification-prefs-advanced"
        >
          <!-- Quiet Hours -->
          <div class="prefs__field">
            <div class="prefs__row">
              <label class="prefs__label prefs__label--sm">
                Ruhezeiten
              </label>
              <button
                :class="['prefs__toggle', { 'prefs__toggle--active': quietHoursEnabled }]"
                @click="quietHoursEnabled = !quietHoursEnabled"
              >
                <span class="prefs__toggle-dot" />
              </button>
            </div>
            <p class="prefs__hint">
              Während der Ruhezeit nur Critical-Meldungen per E-Mail.
            </p>
            <div v-if="quietHoursEnabled" class="prefs__time-row">
              <div class="prefs__time-field">
                <label class="prefs__field-label">Von</label>
                <input
                  v-model="quietHoursStart"
                  type="time"
                  class="prefs__input prefs__input--time"
                />
              </div>
              <div class="prefs__time-field">
                <label class="prefs__field-label">Bis</label>
                <input
                  v-model="quietHoursEnd"
                  type="time"
                  class="prefs__input prefs__input--time"
                />
              </div>
            </div>
          </div>

          <!-- Digest Interval -->
          <div class="prefs__field">
            <label class="prefs__field-label">Digest-Intervall (Minuten)</label>
            <p class="prefs__hint">
              Sammelt Warnungen und sendet gebündelt per E-Mail. 0 = deaktiviert.
            </p>
            <input
              v-model.number="digestIntervalMinutes"
              type="number"
              min="0"
              max="1440"
              class="prefs__input prefs__input--number"
            />
          </div>

          <!-- Browser Notifications -->
          <div class="prefs__field">
            <div class="prefs__row">
              <label class="prefs__label prefs__label--sm">
                <Bell class="prefs__label-icon" />
                Browser-Benachrichtigungen
              </label>
              <button
                :class="['prefs__toggle', { 'prefs__toggle--active': browserNotifications }]"
                @click="browserNotifications = !browserNotifications"
              >
                <span class="prefs__toggle-dot" />
              </button>
            </div>
            <p class="prefs__hint">
              Push-Benachrichtigungen im Browser bei kritischen Alarmen.
            </p>
          </div>
        </AccordionSection>
      </div>
    </template>

    <template #footer>
      <div class="prefs__footer">
        <button
          class="prefs__cancel-btn"
          @click="handleClose"
        >
          Abbrechen
        </button>
        <button
          class="prefs__save-btn"
          :disabled="isSaving"
          @click="save"
        >
          {{ isSaving ? 'Speichere...' : 'Speichern' }}
        </button>
      </div>
    </template>
  </SlideOver>
</template>

<style scoped>
.prefs {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.prefs__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-8);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* Section */
.prefs__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.prefs__sub-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-left: var(--space-3);
  border-left: 2px solid var(--glass-border);
}

/* Row */
.prefs__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

/* Label */
.prefs__label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.prefs__label--sm {
  font-size: var(--text-sm);
  font-weight: 500;
}

.prefs__label-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-secondary);
}

/* Toggle Switch */
.prefs__toggle {
  position: relative;
  width: 36px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.prefs__toggle--active {
  background: var(--color-accent);
  border-color: var(--color-accent);
}

.prefs__toggle-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: var(--radius-full);
  background: var(--color-text-primary);
  transition: transform var(--transition-fast);
}

.prefs__toggle--active .prefs__toggle-dot {
  transform: translateX(16px);
}

/* Fields */
.prefs__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.prefs__field-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.prefs__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
}

.prefs__input {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}

.prefs__input:focus {
  border-color: var(--color-accent);
}

.prefs__input--time,
.prefs__input--number {
  width: 120px;
}

/* Time Row */
.prefs__time-row {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-1);
}

.prefs__time-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

/* Checkboxes */
.prefs__checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.prefs__checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
}

.prefs__checkbox input[type="checkbox"] {
  width: 14px;
  height: 14px;
  accent-color: var(--color-accent);
}

.prefs__checkbox-label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

/* Test Button */
.prefs__test-btn {
  align-self: flex-start;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.prefs__test-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
}

.prefs__test-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Footer */
.prefs__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.prefs__cancel-btn {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.prefs__cancel-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
}

.prefs__save-btn {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-inverse);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.prefs__save-btn:hover:not(:disabled) {
  filter: brightness(1.1);
}

.prefs__save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
