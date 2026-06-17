import axios from 'axios'
import api from './index'

export interface UsbDevice {
  port: string
  description: string
  hwid: string
  chip_family: string
  board_type: string
  vid: number
  pid: number
}

export interface DeviceListResponse {
  success: boolean
  scanning_available: boolean
  count: number
  devices: UsbDevice[]
}

export interface FlashExecuteResponse {
  success: boolean
  port: string
  env: string
  output: string
}

interface FlashErrorDetail {
  error_code?: number
  detail?: string
  platform_note?: string
}

export class FlashPlatformUnavailableError extends Error {
  readonly kind = 'platform_unavailable' as const
  readonly platform_note: string
  readonly retryable = false as const

  constructor(platform_note: string, detail: string) {
    super(detail)
    this.name = 'FlashPlatformUnavailableError'
    this.platform_note = platform_note
  }
}

export class FlashExecuteError extends Error {
  readonly kind = 'flash_execute_error' as const
  readonly error_code: number
  readonly retryable = false as const

  constructor(error_code: number, detail: string) {
    super(detail)
    this.name = 'FlashExecuteError'
    this.error_code = error_code
  }
}

function extractErrorCode(err: unknown): number | undefined {
  if (!axios.isAxiosError(err)) return undefined
  const body = err.response?.data as { detail?: FlashErrorDetail | string } | undefined
  const detail = body?.detail
  if (detail && typeof detail === 'object') return detail.error_code
  return undefined
}

function extractErrorDetail(err: unknown): string {
  if (!axios.isAxiosError(err)) return err instanceof Error ? err.message : 'Unbekannter Fehler'
  const body = err.response?.data as { detail?: FlashErrorDetail | string } | undefined
  const detail = body?.detail
  if (detail && typeof detail === 'object') return detail.detail ?? 'Flash-Fehler'
  if (typeof detail === 'string') return detail
  return 'Flash-Fehler'
}

// =============================================================================
// NVS Secrets API — AUT-767
// =============================================================================

export interface NvsSecretsResponse {
  success: boolean
  env: string
  ssid: string
  password: string
  server_address: string
  mqtt_port: number
  mqtt_username: string
  mqtt_password: string
  configured: number
}

export interface NvsSecretsCreate {
  ssid: string
  password?: string
  server_address: string
  mqtt_port: number
  mqtt_username: string
  mqtt_password?: string
  configured?: number
}

export interface SecretsWriteResponse {
  success: boolean
  path: string
}

export interface SecretsBuildResponse {
  success: boolean
  env: string
  binary_path: string
  size_bytes: number
}

export const secretsApi = {
  async getEnv(): Promise<string> {
    const response = await api.get<{ env: string }>('/flash/env')
    return response.data.env
  },

  async getSecrets(env: string): Promise<NvsSecretsResponse> {
    const response = await api.get<NvsSecretsResponse>(`/flash/secrets/${env}`)
    return response.data
  },

  async putSecrets(env: string, secrets: NvsSecretsCreate): Promise<SecretsWriteResponse> {
    const response = await api.put<SecretsWriteResponse>(`/flash/secrets/${env}`, secrets)
    return response.data
  },

  async buildSecrets(env: string): Promise<SecretsBuildResponse> {
    const response = await api.post<SecretsBuildResponse>(`/flash/secrets/${env}/build`)
    return response.data
  },
}

export const flashApi = {
  async listDevices(): Promise<DeviceListResponse> {
    try {
      const response = await api.get<DeviceListResponse>('/flash/devices')
      return response.data
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 503) {
        const body = err.response.data as { detail?: FlashErrorDetail } | undefined
        const detail = body?.detail
        if (detail?.error_code === 3101) {
          throw new FlashPlatformUnavailableError(
            detail.platform_note ?? 'docker-windows-degraded',
            detail.detail ?? 'USB-Scanning nicht verfügbar auf dieser Plattform',
          )
        }
      }
      throw err
    }
  },

  async executeFlash(
    port: string,
    env: string,
    flashType: 'nvs' | 'firmware' | 'full' = 'nvs',
    eraseConfirm = false,
  ): Promise<FlashExecuteResponse> {
    try {
      const response = await api.post<FlashExecuteResponse>('/flash/execute', {
        port,
        env,
        flash_type: flashType,
        erase_confirm: eraseConfirm,
      })
      return response.data
    } catch (err) {
      const code = extractErrorCode(err)
      const detail = extractErrorDetail(err)
      if (code !== undefined) {
        throw new FlashExecuteError(code, detail)
      }
      throw err
    }
  },
}
