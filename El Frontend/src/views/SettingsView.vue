<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useUiStore } from '@/shared/stores'
import { useRouter } from 'vue-router'
import {
  ExternalLink,
  FileSpreadsheet,
  LogOut,
  Server,
  Settings,
  User,
  UserPlus,
} from 'lucide-vue-next'
import { SETTINGS_LABELS } from '@/utils/labels'

const authStore = useAuthStore()
const uiStore = useUiStore()
const router = useRouter()

const apiUrl = ref(window.location.origin)

// AUT-450 (S8): Optionaler Sheets-Export-Hinweis.
// Sichtbarkeit ueber Build-Time-Env (vgl. VITE_CALIBRATION_API_KEY-Pattern):
// nur anzeigen, wenn die Server-seitige Pipeline tatsaechlich konfiguriert
// ist und der Operator die Spreadsheet-ID im Frontend hinterlegt hat.
const sheetsSpreadsheetId = computed<string>(() => {
  const raw = import.meta.env.VITE_SHEETS_SPREADSHEET_ID
  return typeof raw === 'string' ? raw.trim() : ''
})
const isSheetsExportConfigured = computed<boolean>(
  () => sheetsSpreadsheetId.value.length > 0,
)
const sheetsSpreadsheetUrl = computed<string>(() =>
  isSheetsExportConfigured.value
    ? `https://docs.google.com/spreadsheets/d/${encodeURIComponent(sheetsSpreadsheetId.value)}/edit`
    : '',
)

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

async function handleLogoutAll() {
  const confirmed = await uiStore.confirm({
    title: 'Alle Geräte abmelden',
    message: 'Du wirst auf allen Geräten abgemeldet. Fortfahren?',
    variant: 'warning',
  })
  if (confirmed) {
    await authStore.logout(true)
    router.push('/login')
  }
}
</script>

<template>
  <div class="h-full overflow-auto space-y-6">
    <!-- User Info -->
    <div class="card">
      <div class="card-header flex items-center gap-3">
        <User class="w-5 h-5 text-blue-400" />
        <h3 class="font-semibold text-dark-100">User Account</h3>
      </div>
      <div class="card-body space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <p class="text-sm text-dark-400">Username</p>
            <p class="text-dark-100">{{ authStore.user?.username }}</p>
          </div>
          <div>
            <p class="text-sm text-dark-400">Email</p>
            <p class="text-dark-100">{{ authStore.user?.email }}</p>
          </div>
          <div>
            <p class="text-sm text-dark-400">Role</p>
            <p class="text-dark-100 capitalize">{{ authStore.user?.role }}</p>
          </div>
          <div>
            <p class="text-sm text-dark-400">Status</p>
            <span class="badge badge-success">Active</span>
          </div>
        </div>

        <div class="flex gap-3 pt-4 border-t border-dark-700">
          <button
            v-if="authStore.user?.role === 'admin'"
            class="btn-secondary"
            data-testid="settings-add-user-button"
            @click="router.push('/users')"
          >
            <UserPlus class="w-4 h-4 mr-2" />
            Neuen Benutzer hinzufügen
          </button>
          <button
            class="btn-secondary"
            data-testid="settings-logout-button"
            @click="handleLogout"
          >
            <LogOut class="w-4 h-4 mr-2" />
            {{ SETTINGS_LABELS.logout }}
          </button>
          <button
            class="btn-ghost text-red-400 hover:bg-red-500/10"
            data-testid="settings-logout-all-button"
            @click="handleLogoutAll"
          >
            <LogOut class="w-4 h-4 mr-2" />
            {{ SETTINGS_LABELS.logoutAllDevices }}
          </button>
        </div>
      </div>
    </div>

    <!-- Server Connection -->
    <div class="card">
      <div class="card-header flex items-center gap-3">
        <Server class="w-5 h-5 text-green-400" />
        <h3 class="font-semibold text-dark-100">Server Connection</h3>
      </div>
      <div class="card-body space-y-4">
        <div>
          <p class="text-sm text-dark-400">API URL</p>
          <p class="text-dark-100 font-mono">{{ apiUrl }}/api/v1</p>
        </div>
        <div>
          <p class="text-sm text-dark-400">WebSocket</p>
          <p class="text-dark-100 font-mono">{{ apiUrl.replace('http', 'ws') }}/ws/realtime</p>
        </div>
        <div class="flex items-center gap-2">
          <span class="status-online"></span>
          <span class="text-dark-300">Connected to God-Kaiser Server</span>
        </div>
      </div>
    </div>

    <!-- Sheets Export (AUT-450 S8, optional) -->
    <section
      v-if="isSheetsExportConfigured"
      class="card"
      aria-labelledby="settings-sheets-export-title"
      data-testid="settings-sheets-export-card"
    >
      <div class="card-header flex items-center gap-3">
        <FileSpreadsheet class="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h3 id="settings-sheets-export-title" class="font-semibold text-dark-100">
          {{ SETTINGS_LABELS.sheetsExportTitle }}
        </h3>
      </div>
      <div class="card-body space-y-4">
        <p class="text-sm text-dark-300">
          {{ SETTINGS_LABELS.sheetsExportHint }}
        </p>
        <div>
          <p class="text-sm text-dark-400" id="settings-sheets-export-id-label">
            {{ SETTINGS_LABELS.sheetsExportSpreadsheetId }}
          </p>
          <p
            class="text-dark-100 font-mono break-all"
            aria-labelledby="settings-sheets-export-id-label"
            data-testid="settings-sheets-export-id"
          >
            {{ sheetsSpreadsheetId }}
          </p>
        </div>
        <div>
          <a
            :href="sheetsSpreadsheetUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="btn-secondary inline-flex items-center"
            :aria-label="SETTINGS_LABELS.sheetsExportOpenLink"
            data-testid="settings-sheets-export-link"
          >
            <ExternalLink class="w-4 h-4 mr-2" aria-hidden="true" />
            {{ SETTINGS_LABELS.sheetsExportOpenLink }}
          </a>
        </div>
      </div>
    </section>

    <!-- About -->
    <div class="card">
      <div class="card-header flex items-center gap-3">
        <Settings class="w-5 h-5 text-purple-400" />
        <h3 class="font-semibold text-dark-100">About</h3>
      </div>
      <div class="card-body">
        <div class="space-y-2 text-sm">
          <p><span class="text-dark-400">Frontend:</span> <span class="text-dark-200">El Frontend v1.0.0</span></p>
          <p><span class="text-dark-400">Stack:</span> <span class="text-dark-200">Vue 3 + TypeScript + Tailwind CSS</span></p>
          <p><span class="text-dark-400">Backend:</span> <span class="text-dark-200">God-Kaiser Server (FastAPI)</span></p>
          <p><span class="text-dark-400">Purpose:</span> <span class="text-dark-200">AutomationOne Steuerungszentrale</span></p>
        </div>
      </div>
    </div>
  </div>
</template>
