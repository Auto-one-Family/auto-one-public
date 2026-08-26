/**
 * Inbox-Detail-Fenster (AUT-1510)
 *
 * Bestehendes SlideOver: nach vorn, Satellite treffbar, kein Mute, kein Timeout.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import NotificationDrawer from '@/components/notifications/NotificationDrawer.vue'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import drawerSource from '@/components/notifications/NotificationDrawer.vue?raw'
import slideOverSource from '@/shared/design/primitives/SlideOver.vue?raw'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import type { NotificationDTO } from '@/api/notifications'

const { notificationsApiMock } = vi.hoisted(() => ({
  notificationsApiMock: {
    list: vi.fn(),
    getUnreadCount: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    acknowledgeAlert: vi.fn(),
    resolveAlert: vi.fn(),
    getAlertStats: vi.fn(),
    getPreferences: vi.fn().mockResolvedValue({
      websocket_enabled: true,
      email_enabled: false,
      email_address: null,
      email_severities: ['critical', 'warning'],
      quiet_hours_enabled: false,
      quiet_hours_start: '22:00',
      quiet_hours_end: '07:00',
      digest_interval_minutes: 60,
      browser_notifications: false,
    }),
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
    show: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('@/api/notifications', () => ({
  notificationsApi: notificationsApiMock,
}))

function makeNotification(overrides: Partial<NotificationDTO> = {}): NotificationDTO {
  return {
    id: 'inbox-row-1',
    user_id: 1,
    channel: 'websocket',
    severity: 'warning',
    category: 'data_quality',
    title: 'EC über Schwelle',
    body: 'EC 2.4',
    metadata: { esp_id: 'ESP_TEST_001' },
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

function mountDrawer() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const inboxStore = useNotificationInboxStore()
  const alertStore = useAlertCenterStore()
  inboxStore.notifications = [makeNotification()]
  inboxStore.isDrawerOpen = true
  alertStore.alertStats = {
    success: true,
    active_count: 1,
    acknowledged_count: 0,
    resolved_today_count: 0,
    critical_active: 0,
    warning_active: 1,
    mean_time_to_acknowledge_s: null,
    mean_time_to_resolve_s: null,
  }
  return {
    wrapper: mount(NotificationDrawer, {
      global: { plugins: [pinia] },
      attachTo: document.body,
    }),
    inboxStore,
    alertStore,
  }
}

describe('NotificationDrawer — Inbox-Detail (AUT-1510)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    notificationsApiMock.list.mockResolvedValue({
      data: [],
      pagination: { page: 1, page_size: 50, total_items: 0, total_pages: 0 },
    })
    notificationsApiMock.getUnreadCount.mockResolvedValue({ count: 0 })
    notificationsApiMock.getAlertStats.mockResolvedValue({
      success: true,
      active_count: 1,
      acknowledged_count: 0,
      resolved_today_count: 0,
      critical_active: 0,
      warning_active: 1,
      mean_time_to_acknowledge_s: null,
      mean_time_to_resolve_s: null,
    })
  })

  it('should pass hits through the backdrop and keep Ack/Resolve chrome, not Mute or Timeout', () => {
    const { wrapper } = mountDrawer()
    const inboxSheet = wrapper.findAllComponents(SlideOver)[0]

    expect(inboxSheet.props('allowBackgroundInteraction')).toBe(true)
    expect(inboxSheet.props('inert')).toBe(false)
    expect(inboxSheet.props('width')).toBe('lg')
    expect(wrapper.find('.slide-over-backdrop--pass-through').exists()).toBe(true)
    expect(wrapper.get('[data-testid="notification-drawer-panel"]').text()).toContain('Alle erledigen')
    expect(wrapper.text()).not.toMatch(/Mute|Stumm/i)
    expect(wrapper.get('[data-testid="notification-drawer-panel"]').text()).not.toMatch(/Timeout/i)
    wrapper.unmount()
  })

  it('should size toolbar actions to at least 44px', () => {
    const { wrapper } = mountDrawer()
    expect(wrapper.get('[data-testid="notification-resolve-all"]').classes()).toContain('drawer__action-btn')
    expect(wrapper.get('[data-testid="notification-settings-toggle"]').classes()).toContain('drawer__settings-btn')
    expect(wrapper.find('.slide-over__close').exists()).toBe(true)
    expect(drawerSource).toMatch(/\.drawer__actions-row \.drawer__action-btn \{[\s\S]*?min-height: 44px/)
    expect(drawerSource).toMatch(/\.drawer__settings-btn \{[\s\S]*?min-height: 44px/)
    expect(slideOverSource).toMatch(/\.slide-over__close \{[\s\S]*?min-height: 44px/)
    wrapper.unmount()
  })

  it('should stack preferences above the inbox without drawing a Mute control', async () => {
    const { wrapper, inboxStore } = mountDrawer()
    inboxStore.isPreferencesOpen = true
    await wrapper.vm.$nextTick()

    const sheets = wrapper.findAllComponents(SlideOver)
    const inbox = sheets.find((sheet) => sheet.props('title') === 'Benachrichtigungen')
    const prefs = sheets.find((sheet) => sheet.props('title') === 'Benachrichtigungs-Einstellungen')
    expect(prefs?.props('elevation')).toBe('high')
    expect(prefs?.props('allowBackgroundInteraction')).toBe(true)
    expect(inbox?.props('inert')).toBe(true)
    expect(inbox?.find('.slide-over').attributes('inert')).toBeDefined()
    expect(wrapper.text()).not.toMatch(/Mute|Stumm/i)
    wrapper.unmount()
  })
})
