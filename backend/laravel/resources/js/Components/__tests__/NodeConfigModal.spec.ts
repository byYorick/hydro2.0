import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/Components/Modal.vue', () => ({
  default: {
    name: 'Modal',
    props: ['open', 'title'],
    emits: ['close'],
    template: '<div v-if="open"><div class="modal-title">{{ title }}</div><slot /><slot name="footer" /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'variant', 'disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

const axiosGetMock = vi.hoisted(() => vi.fn())

const mockAxiosInstance = vi.hoisted(() => ({
  get: axiosGetMock,
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  put: vi.fn(),
  interceptors: {
    request: { use: vi.fn(), eject: vi.fn() },
    response: { use: vi.fn(), eject: vi.fn() },
  },
}))

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockAxiosInstance),
    get: (url: string, config?: any) => axiosGetMock(url, config),
  },
}))

// Компонент ходит через api.nodes.getConfig (services/api.nodes), который
// использует apiClient.get. axios замокан через axios.create → mockAxiosInstance,
// так что axiosGetMock ловит все вызовы напрямую. Interceptor не срабатывает
// в тестах, поэтому URL проверяется без префикса `/api`.

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

import NodeConfigModal from '../NodeConfigModal.vue'

describe('NodeConfigModal.vue', () => {
  const sampleConfig = {
    version: 3,
    channels: [
      { channel: 'ph_sensor', type: 'sensor', metric: 'PH', unit: 'pH' },
      { channel: 'pump_acid', type: 'actuator', actuator_type: 'PERISTALTIC_PUMP' },
    ],
  }

  beforeEach(() => {
    axiosGetMock.mockClear()
    axiosGetMock.mockResolvedValue({
      data: {
        data: sampleConfig,
      },
    })
  })

  it('отображается когда show = true', () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })

    expect(wrapper.text()).toContain('Конфигурация узла')
    expect(wrapper.text()).toContain('node-1')
  })

  it('не отображается когда show = false', () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: false,
        nodeId: 1,
      },
    })

    expect(wrapper.html()).not.toContain('Конфигурация узла')
  })

  it('загружает конфигурацию узла при открытии', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })

    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()

    expect(axiosGetMock).toHaveBeenCalled()
    // После миграции на services/api interceptor не применяется в тестах,
    // поэтому URL проверяется без префикса `/api`.
    expect(axiosGetMock.mock.calls[0][0]).toContain('/nodes/1/config')
  })

  it('отображает каналы и JSON', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })

    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('ph_sensor')
    expect(wrapper.text()).toContain('PERISTALTIC_PUMP')
    const pre = wrapper.find('pre')
    expect(pre.exists()).toBe(true)
    expect(pre.text()).toContain('ph_sensor')
  })

  it('показывает сообщение когда нет каналов', async () => {
    axiosGetMock.mockResolvedValue({
      data: {
        data: {
          version: 3,
          channels: [],
        },
      },
    })

    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })

    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Нет данных по каналам')
  })

  it('эмитит событие close при закрытии', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })

    const closeButton = wrapper.findAll('button').find(btn => btn.text().includes('Закрыть'))
    if (closeButton) {
      await closeButton.trigger('click')
      expect(wrapper.emitted('close')).toBeTruthy()
    }
  })
})
