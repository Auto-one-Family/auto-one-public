/**
 * QuickAlertPanel mute copy + inbox chain (AUT-1560)
 *
 * Mute = "keine neuen". Offene Inbox-Zeile bleibt.
 * Ack/Resolve bleiben die Inbox-Kette — Mute darf sie nicht aufrufen.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import QuickAlertPanel from '@/components/quick-action/QuickAlertPanel.vue'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import type { NotificationDTO } from '@/api/notifications'

const toastSuccess = vi.fn()
const toastError = vi.fn()

const { sensorsApiMock, notificationsApiMock } = vi.hoisted(() => ({
  sensorsApiMock: {
    updateAlertConfig: vi.fn(),
    getAlertConfig: vi.fn(),
  },
  notificationsApiMock: {
    list: vi.fn(),
    getUnreadCount: vi.fn(),
    acknowledgeAlert: vi.fn(),
    resolveAlert: vi.fn(),
    getAlertStats: vi.fn(),
  },
}))

const mockRouteQuery = vi.hoisted(() => ({} as Record<string, unknown>))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/router', () => ({
  default: {
    currentRoute: {
      get value() {
        return { query: mockRouteQuery }
      },
    },
    replace: vi.fn(),
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: toastSuccess,
    error: toastError,
    warning: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('@/api/sensors', () => ({
  sensorsApi: sensorsApiMock,
}))

vi.mock('@/api/notifications', () => ({
  notificationsApi: notificationsApiMock,
}))

function makeAlert(overrides: Partial<NotificationDTO> = {}): NotificationDTO {
  return {
    id: 'alert-1',
    user_id: 1,
    channel: 'websocket',
    severity: 'warning',
    category: 'data_quality',
    title: 'pH über Schwelle',
    body: 'pH 7.2',
    metadata: { sensor_config_id: 'sensor-cfg-1', esp_id: 'ESP_TEST_001' },
    source: 'sensor_threshold',
    is_read: false,
    is_archived: false,
    digest_sent: false,
    parent_notification_id: null,
    fingerprint: null,
    created_at: new Date().toISOString(),
    updated_at: null,
    read_at: null,
    status: 'active',
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    correlation_id: null,
    ...overrides,
  }
}

function mountPanel(alert: NotificationDTO = makeAlert()) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const inboxStore = useNotificationInboxStore()
  inboxStore.notifications = [alert]
  return {
    wrapper: mount(QuickAlertPanel, {
      global: { plugins: [pinia] },
    }),
    inboxStore,
    alert,
  }
}

describe('QuickAlertPanel — mute copy (AUT-1560)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const key of Object.keys(mockRouteQuery)) {
      delete mockRouteQuery[key]
    }
    sensorsApiMock.updateAlertConfig.mockResolvedValue({ alert_config: {} })
    sensorsApiMock.getAlertConfig.mockResolvedValue({ alert_config: {} })
    notificationsApiMock.acknowledgeAlert.mockResolvedValue(makeAlert({ status: 'acknowledged' }))
    notificationsApiMock.resolveAlert.mockResolvedValue(makeAlert({ status: 'resolved' }))
    notificationsApiMock.getAlertStats.mockResolvedValue({
      active_count: 1,
      acknowledged_count: 0,
      resolved_count: 0,
    })
  })

  it('should label mute as keine neuen, not as inbox ack', () => {
    const { wrapper } = mountPanel()
    expect(wrapper.get('[data-testid="quick-alert-row-alert-1"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="quick-alert-ack-alert-1"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="quick-alert-resolve-alert-1"]').exists()).toBe(true)
  })

  it('should keep the open inbox row and skip ack/resolve when mute is used', async () => {
    const { wrapper, inboxStore, alert } = mountPanel()

    await wrapper.get('[data-testid="quick-alert-expand-alert-1"]').trigger('click')
    const mute = wrapper.get('[data-testid="quick-alert-mute-alert-1"]')
    expect(mute.text()).toContain('Keine neuen')
    expect(mute.attributes('title')).toContain('offene Inbox-Zeile bleibt')

    await mute.trigger('click')
    await wrapper.get('[data-testid="quick-alert-mute-preset-1h"]').trigger('click')
    await Promise.resolve()
    await Promise.resolve()

    expect(sensorsApiMock.updateAlertConfig).toHaveBeenCalledWith('sensor-cfg-1', {
      alerts_enabled: false,
      suppression_until: expect.any(String),
      suppression_reason: 'custom',
      suppression_note: 'Snooze 1 Stunde via Quick Alert Panel',
    })
    expect(notificationsApiMock.acknowledgeAlert).not.toHaveBeenCalled()
    expect(notificationsApiMock.resolveAlert).not.toHaveBeenCalled()
    expect(inboxStore.notifications[0]?.status).toBe('active')
    expect(inboxStore.notifications[0]?.id).toBe(alert.id)
    expect(toastSuccess).toHaveBeenCalledWith(
      'Keine neuen Alerts für 1 Stunde — offene Zeile bleibt',
    )
  })

  it('should still ack through the inbox chain button', async () => {
    const { wrapper } = mountPanel()
    await wrapper.get('[data-testid="quick-alert-ack-alert-1"]').trigger('click')
    await Promise.resolve()
    await Promise.resolve()
    expect(notificationsApiMock.acknowledgeAlert).toHaveBeenCalledWith('alert-1')
    expect(sensorsApiMock.updateAlertConfig).not.toHaveBeenCalled()
  })

  it('should still resolve through the inbox chain button', async () => {
    const { wrapper } = mountPanel()
    await wrapper.get('[data-testid="quick-alert-resolve-alert-1"]').trigger('click')
    await Promise.resolve()
    await Promise.resolve()
    expect(notificationsApiMock.resolveAlert).toHaveBeenCalledWith('alert-1')
    expect(sensorsApiMock.updateAlertConfig).not.toHaveBeenCalled()
  })
})
