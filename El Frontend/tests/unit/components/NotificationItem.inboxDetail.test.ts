/**
 * Inbox-Detail-Zeile (AUT-1510)
 *
 * Zeile = Expand. Buttons = Bestätigen/Erledigen.
 * Kein Mute, kein Timeout als B1-Aktion. Status auf der Zeile = Button-Bedeutung.
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import NotificationItem from '@/components/notifications/NotificationItem.vue'
import itemSource from '@/components/notifications/NotificationItem.vue?raw'
import type { NotificationDTO } from '@/api/notifications'

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
  }),
}))

function makeNotification(overrides: Partial<NotificationDTO> = {}): NotificationDTO {
  return {
    id: 'inbox-1',
    user_id: 1,
    channel: 'websocket',
    severity: 'critical',
    category: 'data_quality',
    title: 'pH über Schwelle',
    body: 'pH 7.2',
    metadata: { esp_id: 'ESP_TEST_001', sensor_type: 'ph' },
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

function mountItem(notification: NotificationDTO = makeNotification()) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(NotificationItem, {
    props: { notification },
    global: { plugins: [pinia] },
  })
}

describe('NotificationItem — Inbox-Detail (AUT-1510)', () => {
  it('should expand the row on click and not offer Mute or Timeout', async () => {
    const wrapper = mountItem()
    expect(wrapper.find('.item__details').exists()).toBe(false)

    await wrapper.get(`[data-testid="notification-item-inbox-1"]`).trigger('click')

    expect(wrapper.find('.item__details').exists()).toBe(true)
    expect(wrapper.text()).toContain('Bestätigen')
    expect(wrapper.text()).toContain('Erledigen')
    expect(wrapper.text()).not.toMatch(/Mute|Stumm/i)
    expect(wrapper.text()).not.toMatch(/Timeout/i)
    wrapper.unmount()
  })

  it('should show Aktiv on the row and emit acknowledge/resolve from matching buttons', async () => {
    const wrapper = mountItem()
    expect(wrapper.find('.item__status').text()).toBe('Aktiv')

    await wrapper.get(`[data-testid="notification-item-inbox-1"]`).trigger('click')
    await wrapper.get('[data-testid="notification-alert-ack-inbox-1"]').trigger('click')
    await wrapper.get('[data-testid="notification-alert-resolve-inbox-1"]').trigger('click')

    expect(wrapper.emitted('acknowledge')).toEqual([['inbox-1']])
    expect(wrapper.emitted('resolve')).toEqual([['inbox-1']])
    wrapper.unmount()
  })

  it('should show Bestätigt and only Erledigen after ack, not a second mute control', async () => {
    const wrapper = mountItem(makeNotification({ status: 'acknowledged', is_read: true }))
    expect(wrapper.find('.item__status').text()).toBe('Bestätigt')

    await wrapper.get(`[data-testid="notification-item-inbox-1"]`).trigger('click')

    expect(wrapper.find('[data-testid="notification-alert-ack-inbox-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="notification-alert-resolve-inbox-1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Erledigen')
    expect(wrapper.text()).not.toMatch(/Mute|Stumm|Timeout/i)
    wrapper.unmount()
  })

  it('should size existing action targets to at least 44px', async () => {
    const wrapper = mountItem()
    await wrapper.get(`[data-testid="notification-item-inbox-1"]`).trigger('click')

    const ack = wrapper.get('[data-testid="notification-alert-ack-inbox-1"]')
    expect(ack.classes()).toContain('item__action')
    expect(itemSource).toMatch(/\.item__action \{[\s\S]*?min-height: 44px/)
    expect(itemSource).toMatch(/\.item__action \{[\s\S]*?min-width: 44px/)
    wrapper.unmount()
  })
})
