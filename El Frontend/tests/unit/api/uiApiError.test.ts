import { describe, expect, it } from 'vitest'
import { toUiApiError } from '@/api/uiApiError'

describe('toUiApiError', () => {
  it('mappt GodKaiser-Fehler mit numeric_code und request_id korrekt', () => {
    const error = {
      message: 'Request failed with status code 500',
      response: {
        status: 500,
        headers: { 'x-request-id': 'req-header-1' },
        data: {
          success: false,
          error: {
            code: 'ESP_NOT_FOUND',
            numeric_code: 5001,
            message: 'ESP32 device not found',
            request_id: 'req-body-1',
          },
        },
      },
    }

    const ui = toUiApiError(error, 'Fallback')
    expect(ui.message).toBe('ESP32 device not found')
    expect(ui.numeric_code).toBe(5001)
    expect(ui.request_id).toBe('req-body-1')
    expect(ui.status).toBe(500)
    expect(ui.retryability).toBe('yes')
  })

  it('mappt FastAPI detail ohne numeric_code mit sauberem Fallback', () => {
    const error = {
      message: 'Request failed with status code 400',
      response: {
        status: 400,
        headers: { 'x-request-id': 'req-fastapi-1' },
        data: {
          detail: 'Validation failed',
        },
      },
    }

    const ui = toUiApiError(error, 'Fallback')
    expect(ui.message).toBe('Validation failed')
    expect(ui.numeric_code).toBeNull()
    expect(ui.request_id).toBe('req-fastapi-1')
    expect(ui.status).toBe(400)
    expect(ui.retryability).toBe('no')
  })

  it('mappt Netzwerkfehler ohne Response auf status=0 und nachvollziehbare Retryability', () => {
    const error = {
      message: 'Network Error',
    }

    const ui = toUiApiError(error, 'Fallback')
    expect(ui.status).toBe(0)
    expect(ui.numeric_code).toBeNull()
    expect(ui.request_id).toBeNull()
    expect(ui.retryability).toBe('yes')
    expect(ui.message).toContain('Network Error')
  })

  it('mappt 403 konsistent als Zugriff verweigert mit retryability=no', () => {
    const error = {
      message: 'Request failed with status code 403',
      response: {
        status: 403,
        headers: { 'x-request-id': 'req-403-1' },
        data: {
          detail: 'Forbidden',
        },
      },
    }

    const ui = toUiApiError(error, 'Fallback')
    expect(ui.status).toBe(403)
    expect(ui.retryability).toBe('no')
    expect(ui.request_id).toBe('req-403-1')
    expect(ui.message).toBe('Zugriff verweigert. Sie haben keine Berechtigung für diese Aktion.')
  })
})
