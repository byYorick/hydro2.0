import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const pageState = vi.hoisted(() => ({
  role: 'admin' as string,
}))

const healthMock = vi.hoisted(() => vi.fn())

const statusState = vi.hoisted(() => ({
  core: 'ok',
  db: 'ok',
  ws: 'connected',
  mqtt: 'online',
  historyLogger: 'ok',
  automationEngine: 'fail',
}))

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'variant', 'disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

vi.mock('@/utils/formatTime', () => ({
  formatTime: () => 'только что',
}))

vi.mock('@/services/api', () => ({
  api: {
    system: {
      health: healthMock,
    },
  },
}))

vi.mock('@/composables/useSystemStatus', async () => {
  const { ref } = await import('vue')
  return {
    useSystemStatus: () => ({
      coreStatus: ref(statusState.core),
      dbStatus: ref(statusState.db),
      wsStatus: ref(statusState.ws),
      mqttStatus: ref(statusState.mqtt),
      historyLoggerStatus: ref(statusState.historyLogger),
      automationEngineStatus: ref(statusState.automationEngine),
      lastUpdate: ref(new Date('2026-08-19T10:00:00Z')),
      checkHealth: vi.fn().mockResolvedValue(undefined),
      checkWebSocketStatus: vi.fn(),
    }),
  }
})

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: {
        user: { role: pageState.role },
      },
    },
  }),
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

import MonitoringIndex from '../Index.vue'

function mountPage(role: string) {
  pageState.role = role
  return mount(MonitoringIndex)
}

describe('Monitoring/Index.vue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    pageState.role = 'admin'
    statusState.core = 'ok'
    statusState.db = 'ok'
    statusState.ws = 'connected'
    statusState.mqtt = 'online'
    statusState.historyLogger = 'ok'
    statusState.automationEngine = 'fail'
    healthMock.mockReset()
    healthMock.mockResolvedValue({
      app: 'ok',
      db: 'ok',
      mqtt: 'ok',
      history_logger: 'ok',
      automation_engine: 'fail',
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('показывает заголовок «Здоровье системы»', async () => {
    const wrapper = mountPage('admin')
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Здоровье системы')
    wrapper.unmount()
  })

  it('для admin показывает сводку N из M по статусам карточек', async () => {
    const wrapper = mountPage('admin')
    await flushPromises()
    expect(healthMock).toHaveBeenCalled()
    expect(wrapper.get('[data-testid="health-summary"]').text()).toContain('5 из 6 в норме')
    wrapper.unmount()
  })

  it('для engineer показывает названия сервисов развёрнуто', async () => {
    const wrapper = mountPage('engineer')
    await flushPromises()
    expect(wrapper.find('[data-testid="health-summary"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Core API')
    expect(wrapper.text()).toContain('History Logger')
    expect(wrapper.text()).toContain('Automation Engine')
    wrapper.unmount()
  })

  it('в тексте пайплайнов есть history-logger и automation-engine', async () => {
    const wrapper = mountPage('engineer')
    await flushPromises()
    expect(wrapper.text()).toContain('history-logger')
    expect(wrapper.text()).toContain('automation-engine')
    wrapper.unmount()
  })

  it('не использует упрощённую цепь «БД → MQTT → WebSocket → UI» как канон', async () => {
    const wrapper = mountPage('engineer')
    await flushPromises()
    expect(wrapper.text()).not.toContain('БД → MQTT → WebSocket → UI')
    wrapper.unmount()
  })
})
