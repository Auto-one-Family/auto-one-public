import api from './index'

export interface CameraStatus {
  enabled: boolean
  available: boolean
  model?: string
  last_capture?: string | null
  interval_seconds?: number
  error?: string | null
  status?: string
}

export const cameraApi = {
  async getStatus(): Promise<CameraStatus> {
    const response = await api.get<CameraStatus>('/camera/status')
    return response.data
  },

  async fetchSnapshot(): Promise<string> {
    const response = await api.get<Blob>('/camera/snapshot', { responseType: 'blob' })
    return URL.createObjectURL(response.data)
  },
}
