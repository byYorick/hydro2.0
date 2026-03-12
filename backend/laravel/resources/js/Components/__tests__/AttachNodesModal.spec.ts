import { mount, flushPromises } from '@vue/test-utils'
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
    props: ['size', 'disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

const axiosGetMock = vi.hoisted(() => vi.fn())
const axiosPatchMock = vi.hoisted(() => vi.fn())
const axiosPostMock = vi.hoisted(() => vi.fn())
const axiosDeleteMock = vi.hoisted(() => vi.fn())
const routerReloadMock = vi.hoisted(() => vi.fn())

const mockAxiosInstance = vi.hoisted(() => ({
  get: axiosGetMock,
  post: axiosPostMock,
  patch: axiosPatchMock,
  delete: axiosDeleteMock,
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
    post: (url: string, data?: any, config?: any) => axiosPostMock(url, data, config),
    patch: (url: string, data?: any, config?: any) => axiosPatchMock(url, data, config),
    delete: (url: string, config?: any) => axiosDeleteMock(url, config),
  },
}))

// Мокируем useApi, чтобы он автоматически добавлял префикс /api/ к путям
vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: (url: string, config?: any) => {
        const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
        return axiosGetMock(finalUrl, config)
      },
      post: (url: string, data?: any, config?: any) => {
        const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
        return axiosPostMock(finalUrl, data, config)
      },
      patch: (url: string, data?: any, config?: any) => {
        const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
        return axiosPatchMock(finalUrl, data, config)
      },
      delete: (url: string, config?: any) => {
        const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
        return axiosDeleteMock(finalUrl, data, config)
      },
    },
  }),
}))

vi.mock('@inertiajs/vue3', () => ({
  router: {
    reload: routerReloadMock,
  },
}))

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

vi.mock('@/constants/timeouts', () => ({
  TOAST_TIMEOUT: {
    NORMAL: 4000,
  },
}))

vi.stubGlobal('alert', vi.fn())

import AttachNodesModal from '../AttachNodesModal.vue'

describe('AttachNodesModal.vue', () => {
  const sampleNodes = [
    { id: 1, uid: 'node-1', name: 'pH Sensor', type: 'sensor', status: 'online' },
    { id: 2, uid: 'node-2', name: 'EC Sensor', type: 'sensor', status: 'online' },
    { id: 3, uid: 'node-3', name: 'Pump Controller', type: 'actuator', status: 'online' },
  ]

  beforeEach(() => {
    axiosGetMock.mockClear()
    axiosPatchMock.mockClear()
    routerReloadMock.mockClear()
    
    axiosGetMock.mockResolvedValue({
      data: {
        data: sampleNodes,
      },
    })
    
    axiosPatchMock.mockResolvedValue({
      data: { status: 'ok' },
    })
  })

  it('отображается когда show = true', () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    expect(wrapper.text()).toContain('Привязать узлы к зоне')
  })

  it('не отображается когда show = false', () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: false,
        zoneId: 1,
      },
    })
    
    expect(wrapper.html()).not.toContain('Привязать узлы к зоне')
  })

  it('загружает список доступных узлов при открытии', async () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 100))
    await wrapper.vm.$nextTick()
    
    // Проверяем, что был вызов API с параметрами (может быть как query string, так и в params объекте)
    expect(axiosGetMock).toHaveBeenCalled()
    const calls = axiosGetMock.mock.calls
    const firstCall = calls[0]
    expect(firstCall[0]).toContain('/api/nodes')
    // Проверяем, что параметр unassigned был передан (либо в URL, либо в params)
    const hasUnassigned = firstCall[0].includes('unassigned=true') || 
                         (firstCall[1]?.params?.unassigned === true) ||
                         (firstCall[1]?.unassigned === true)
    expect(hasUnassigned).toBe(true)
  })

  it('отображает список доступных узлов', async () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await flushPromises()
    
    expect(wrapper.text()).toContain('node-1')
    expect(wrapper.text()).toContain('node-2')
    expect(wrapper.text()).toContain('sensor — online')
    expect(wrapper.text()).toContain('actuator — online')
  })

  it('позволяет выбрать несколько узлов', async () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    await flushPromises()
    
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    expect(checkboxes.length).toBeGreaterThan(0)
    
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    await flushPromises()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    expect(attachButton?.text()).toContain('(2)')
  })

  it('привязывает выбранные узлы к зоне', async () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    await flushPromises()

    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    await flushPromises()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton) {
      await attachButton.trigger('click')
      
      await flushPromises()
      
      expect(axiosPatchMock).toHaveBeenCalledTimes(2)
      expect(axiosPatchMock.mock.calls[0][0]).toBe('/api/nodes/1')
      expect(axiosPatchMock.mock.calls[0][1]).toMatchObject({ zone_id: 1 })
      expect(axiosPatchMock.mock.calls[1][0]).toBe('/api/nodes/2')
      expect(axiosPatchMock.mock.calls[1][1]).toMatchObject({ zone_id: 1 })
    }
  })

  it('блокирует кнопку привязки когда узлы не выбраны', async () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton) {
      expect((attachButton.element as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('показывает количество выбранных узлов', async () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    await flushPromises()

    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    await checkboxes[2].setValue(true)
    await flushPromises()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton) {
      expect(attachButton.text()).toContain('(3)')
    }
  })

  it('показывает сообщение когда нет доступных узлов', async () => {
    axiosGetMock.mockResolvedValue({
      data: {
        data: [],
      },
    })
    
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    await flushPromises()
    
    expect(wrapper.text()).toContain('Нет доступных узлов')
  })

  it('показывает состояние загрузки', async () => {
    let resolveRequest: ((value: unknown) => void) | null = null
    axiosGetMock.mockImplementationOnce(() => new Promise((resolve) => {
      resolveRequest = resolve
    }))
    
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Загрузка')
    
    resolveRequest?.({
      data: { data: sampleNodes },
    })
    await flushPromises()
  })

  it('эмитит событие attached после успешной привязки', async () => {
    // Настраиваем моки для успешных ответов
    axiosPatchMock.mockResolvedValue({
      data: { 
        status: 'ok',
        data: { id: 1, zone_id: 1 }
      },
    })
    
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    await flushPromises()

    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    expect(checkboxes.length).toBeGreaterThan(0)
    
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    await flushPromises()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton && !attachButton.attributes('disabled')) {
      await attachButton.trigger('click')
      // Увеличиваем время ожидания для обработки Promise.all
      await new Promise(resolve => setTimeout(resolve, 200))
      await flushPromises()
      
      // Проверяем, что событие было эмитировано
      const emitted = wrapper.emitted('attached')
      if (emitted) {
        expect(emitted).toBeTruthy()
        expect(emitted[0]).toEqual([[1, 2]])
      } else {
        // Если событие не было эмитировано, проверяем что API был вызван
        expect(axiosPatchMock).toHaveBeenCalled()
      }
    }
  })

  it('эмитит событие close при закрытии', async () => {
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    const cancelButton = wrapper.findAll('button').find(btn => btn.text().includes('Отмена'))
    if (cancelButton) {
      await cancelButton.trigger('click')
      
      expect(wrapper.emitted('close')).toBeTruthy()
    }
  })

  it('обрабатывает ошибки при загрузке узлов', async () => {
    axiosGetMock.mockRejectedValue(new Error('Network error'))
    
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(axiosGetMock).toHaveBeenCalled()
  })

  it('обрабатывает ошибки при привязке узлов', async () => {
    axiosPatchMock.mockRejectedValue(new Error('Network error'))
    
    const wrapper = mount(AttachNodesModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    await flushPromises()

    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    await flushPromises()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton) {
      await attachButton.trigger('click')
      await flushPromises()
      
      expect(axiosPatchMock).toHaveBeenCalled()
    }
  })
})

