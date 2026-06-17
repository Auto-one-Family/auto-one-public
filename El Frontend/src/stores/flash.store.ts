import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import { secretsApi, type NvsSecretsCreate } from '@/api/flash'

const PASSWORD_MASK = '***'

export type BuildStatus = 'idle' | 'saving' | 'building' | 'ready' | 'error'

export const useFlashStore = defineStore('flash', () => {
  // Form state — session-only, never persisted to storage
  const ssid = ref('')
  const wifiPassword = ref('')
  const serverAddress = ref('')
  const mqttPort = ref(1883)
  const mqttUsername = ref('')
  const mqttPassword = ref('')

  // Current flash env — populated by fetchEnv() on panel open
  const currentEnv = ref('dev-local')

  // Flash mode selection — nvs=credentials only, firmware=fw+nvs, full=erase+fw+nvs
  const flashType = ref<'nvs' | 'firmware' | 'full'>('nvs')

  // Build pipeline state
  const buildStatus = ref<BuildStatus>('idle')
  const buildError = ref<string | null>(null)

  // Load state
  const isLoading = ref(false)
  const loadError = ref<string | null>(null)

  async function fetchEnv(): Promise<void> {
    try {
      currentEnv.value = await secretsApi.getEnv()
    } catch {
      // Non-fatal: keep existing value (dev-local default) if server unreachable
    }
  }

  async function loadSecrets(env: string): Promise<void> {
    isLoading.value = true
    loadError.value = null
    try {
      const data = await secretsApi.getSecrets(env)
      ssid.value = data.ssid
      wifiPassword.value = PASSWORD_MASK
      serverAddress.value = data.server_address
      mqttPort.value = data.mqtt_port
      mqttUsername.value = data.mqtt_username
      mqttPassword.value = PASSWORD_MASK
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        // No CSV yet — pre-fill defaults, no error shown
        mqttPort.value = 1883
      } else {
        loadError.value = err instanceof Error ? err.message : 'Laden fehlgeschlagen'
      }
    } finally {
      isLoading.value = false
    }
  }

  async function saveAndBuild(env: string): Promise<void> {
    buildStatus.value = 'saving'
    buildError.value = null
    try {
      const payload: NvsSecretsCreate = {
        ssid: ssid.value,
        server_address: serverAddress.value,
        mqtt_port: mqttPort.value,
        mqtt_username: mqttUsername.value,
      }
      // Only send passwords if the user changed them from the mask
      if (wifiPassword.value !== PASSWORD_MASK) {
        payload.password = wifiPassword.value
      }
      if (mqttPassword.value !== PASSWORD_MASK) {
        payload.mqtt_password = mqttPassword.value
      }

      await secretsApi.putSecrets(env, payload)

      // Clear password fields after successful save (Gate V6 + AUT-767 requirement)
      wifiPassword.value = PASSWORD_MASK
      mqttPassword.value = PASSWORD_MASK

      buildStatus.value = 'building'
      await secretsApi.buildSecrets(env)
      buildStatus.value = 'ready'
    } catch (err) {
      buildStatus.value = 'error'
      const detail =
        axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : err instanceof Error
            ? err.message
            : 'Fehler beim Speichern'
      buildError.value = detail
    }
  }

  function $reset(): void {
    ssid.value = ''
    wifiPassword.value = ''
    serverAddress.value = ''
    mqttPort.value = 1883
    mqttUsername.value = ''
    mqttPassword.value = ''
    buildStatus.value = 'idle'
    buildError.value = null
    isLoading.value = false
    loadError.value = null
    flashType.value = 'nvs'
  }

  return {
    currentEnv,
    flashType,
    ssid,
    wifiPassword,
    serverAddress,
    mqttPort,
    mqttUsername,
    mqttPassword,
    buildStatus,
    buildError,
    isLoading,
    loadError,
    fetchEnv,
    loadSecrets,
    saveAndBuild,
    $reset,
  }
})
