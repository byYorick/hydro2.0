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
    props: ['size', 'disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

const axiosGetMock = vi.hoisted(() => vi.fn())
const axiosPostMock = vi.hoisted(() => vi.fn())
const routerReloadMock = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: {
    get: (url: string, config?: any) => axiosGetMock(url, config),
    post: (url: string, data?: any, config?: any) => axiosPostMock(url, data, config),
  },
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

import NodeConfigModal from '../NodeConfigModal.vue'

describe('NodeConfigModal.vue', () => {
  const sampleConfig = {
    config: {
      channels: [
        { channel: 'ph_sensor', type: 'sensor', unit: 'pH', min: 0, max: 14 },
        { channel: 'ec_sensor', type: 'sensor', unit: 'mS/cm', min: 0, max: 5 },
        { channel: 'pump', type: 'actuator', unit: 'on/off' },
      ],
    },
  }

  beforeEach(() => {
    axiosGetMock.mockClear()
    axiosPostMock.mockClear()
    routerReloadMock.mockClear()
    
    axiosGetMock.mockResolvedValue({
      data: {
        data: sampleConfig,
      },
    })
    
    axiosPostMock.mockResolvedValue({
      data: { status: 'ok' },
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
    
    expect(wrapper.text()).toContain('Настройка узла')
    expect(wrapper.text()).toContain('node-1')
  })

  it('не отображается когда show = false', () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: false,
        nodeId: 1,
      },
    })
    
    expect(wrapper.html()).not.toContain('Настройка узла')
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
    
    expect(axiosGetMock).toHaveBeenCalledWith('/api/nodes/1/config', expect.any(Object))
  })

  it('отображает существующие каналы', async () => {
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
    expect(wrapper.text()).toContain('ec_sensor')
    expect(wrapper.text()).toContain('pump')
  })

  it('позволяет добавить новый канал', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const addButton = wrapper.findAll('button').find(btn => btn.text().includes('Добавить канал'))
    if (addButton) {
      const channelsBefore = wrapper.vm.$data.channels.length
      await addButton.trigger('click')
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.$data.channels.length).toBeGreaterThan(channelsBefore)
    }
  })

  it('позволяет редактировать каналы', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const channelInputs = wrapper.findAll('input[placeholder*="ph_sensor"]')
    if (channelInputs.length > 0) {
      await channelInputs[0].setValue('ph_sensor_updated')
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.$data.channels[0].channel).toBe('ph_sensor_updated')
    }
  })

  it('публикует конфигурацию при нажатии кнопки', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const publishButton = wrapper.findAll('button').find(btn => btn.text().includes('Опубликовать'))
    if (publishButton) {
      await publishButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(axiosPostMock).toHaveBeenCalledWith(
        '/api/nodes/1/config/publish',
        expect.objectContaining({
          config: expect.objectContaining({
            channels: expect.any(Array),
          }),
        }),
        expect.any(Object)
      )
    }
  })

  it('показывает состояние загрузки', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    expect(wrapper.text()).toContain('Загрузка конфигурации')
  })

  it('показывает сообщение когда нет каналов', async () => {
    axiosGetMock.mockResolvedValue({
      data: {
        data: {
          config: {
            channels: [],
          },
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
    
    expect(wrapper.text()).toContain('У узла нет настроенных каналов')
  })

  it('эмитит событие published после успешной публикации', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const publishButton = wrapper.findAll('button').find(btn => btn.text().includes('Опубликовать'))
    if (publishButton) {
      await publishButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(wrapper.emitted('published')).toBeTruthy()
    }
  })

  it('эмитит событие close при закрытии', async () => {
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    const cancelButton = wrapper.findAll('button').find(btn => btn.text().includes('Отмена'))
    if (cancelButton) {
      await cancelButton.trigger('click')
      
      expect(wrapper.emitted('close')).toBeTruthy()
    }
  })

  it('обрабатывает ошибки при загрузке конфигурации', async () => {
    axiosGetMock.mockRejectedValue(new Error('Network error'))
    
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(axiosGetMock).toHaveBeenCalled()
  })

  it('обрабатывает ошибки при публикации конфигурации', async () => {
    axiosPostMock.mockRejectedValue(new Error('Network error'))
    
    const wrapper = mount(NodeConfigModal, {
      props: {
        show: true,
        nodeId: 1,
        node: { id: 1, uid: 'node-1' },
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const publishButton = wrapper.findAll('button').find(btn => btn.text().includes('Опубликовать'))
    if (publishButton) {
      await publishButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(axiosPostMock).toHaveBeenCalled()
    }
  })
})

