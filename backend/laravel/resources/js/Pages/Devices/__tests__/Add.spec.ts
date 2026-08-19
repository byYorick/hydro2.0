import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPatchMock = vi.hoisted(() => vi.fn())
const apiDeleteMock = vi.hoisted(() => vi.fn())

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'variant', 'disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', props: ['variant'], template: '<span><slot /></span>' },
}))

async function unwrapEnvelope(rawPromise: Promise<unknown>): Promise<unknown> {
  const raw = await rawPromise
  // Эмулируем apiGet из services/api/_client: axios выдаёт `response.data` (снимаем
  // первый `data` от mock-raw), затем extractData снимает ещё один уровень.
  if (!raw || typeof raw !== 'object') return raw
  const afterAxios = 'data' in (raw as Record<string, unknown>) ? (raw as { data: unknown }).data : raw
  // extractData logic
  if (afterAxios && typeof afterAxios === 'object' && 'data' in (afterAxios as Record<string, unknown>)) {
    const inner = (afterAxios as { data: unknown }).data
    if (inner && typeof inner === 'object' && 'data' in (inner as Record<string, unknown>)) {
      return (inner as { data: unknown }).data
    }
    return inner
  }
  return afterAxios
}

vi.mock('@/services/api', () => ({
  api: {
    nodes: {
      list: (params?: Record<string, unknown>) =>
        unwrapEnvelope(apiGetMock('/api/nodes', { params })),
      update: (nodeId: number, payload: Record<string, unknown>) =>
        unwrapEnvelope(apiPatchMock(`/api/nodes/${nodeId}`, payload, undefined)),
      delete: (nodeId: number) =>
        unwrapEnvelope(apiDeleteMock(`/api/nodes/${nodeId}`, undefined)),
    },
    greenhouses: {
      list: () => unwrapEnvelope(apiGetMock('/api/greenhouses', undefined)),
    },
    zones: {
      list: () => unwrapEnvelope(apiGetMock('/api/zones', undefined)),
    },
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/composables/useNodeLifecycle', () => ({
  useNodeLifecycle: () => ({
    canAssignToZone: vi.fn().mockResolvedValue(true),
    getStateLabel: vi.fn(() => 'Registered'),
    isAssignableLifecycleState: vi.fn(() => true),
    needsRebindConfirm: vi.fn(() => false),
    formatPendingBindAge: vi.fn(() => null),
  }),
}))

vi.mock('@/composables/useErrorHandler', () => ({
  useErrorHandler: () => ({
    handleError: vi.fn(),
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}))

const pageAuth = vi.hoisted(() => ({ role: 'engineer' }))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: {
        user: pageAuth,
      },
    },
  }),
  router: {
    visit: vi.fn(),
  },
}))

import DevicesAdd from '../Add.vue'

describe('Devices/Add.vue', () => {
  beforeEach(() => {
    pageAuth.role = 'engineer'
    vi.useFakeTimers()
    apiGetMock.mockReset()
    apiPatchMock.mockReset()
    apiDeleteMock.mockReset()

    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/nodes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [
                {
                  id: 1,
                  uid: 'nd-clim-1',
                  type: 'climate',
                  status: 'online',
                  fw_version: 'v1.2.3',
                },
              ],
            },
          },
        })
      }

      if (url === '/api/greenhouses') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [{ id: 10, name: 'Main GH' }],
            },
          },
        })
      }

      if (url === '/api/zones') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [{ id: 20, greenhouse_id: 10, name: 'Zone A' }],
            },
          },
        })
      }

      return Promise.resolve({
        data: {
          status: 'ok',
          data: {
            data: [],
          },
        },
      })
    })
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('renders new nodes from paginated API responses', async () => {
    const wrapper = mount(DevicesAdd)
    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/nodes', { params: { new_only: true } })
    expect(wrapper.text()).toContain('UID: nd-clim-1')
    expect(wrapper.text()).not.toContain('Новых нод не найдено')

    wrapper.unmount()
  })

  it('deletes a node after confirmation', async () => {
    apiDeleteMock.mockResolvedValue({ data: { status: 'ok' } })

    const wrapper = mount(DevicesAdd)
    await flushPromises()

    const deleteButton = wrapper.find('[data-test="delete-node-1"]')
    expect(deleteButton.exists()).toBe(true)

    await deleteButton.trigger('click')
    await flushPromises()

    expect(apiDeleteMock).not.toHaveBeenCalled()
    const confirmBtn = wrapper.findAll('button').find((btn) => btn.text() === 'Подтвердить')
    expect(confirmBtn).toBeTruthy()
    await confirmBtn!.trigger('click')
    await flushPromises()

    expect(apiDeleteMock).toHaveBeenCalledWith('/api/nodes/1', undefined)
    expect(wrapper.text()).not.toContain('UID: nd-clim-1')

    wrapper.unmount()
  })

  it('agronomist видит баннер и не может удалять узлы', async () => {
    pageAuth.role = 'agronomist'

    const wrapper = mount(DevicesAdd)
    await flushPromises()

    expect(wrapper.text()).toContain('Добавление устройств доступно инженеру или администратору.')
    const deleteButton = wrapper.find('[data-test="delete-node-1"]')
    expect(deleteButton.exists()).toBe(true)
    expect(deleteButton.attributes('disabled')).toBeDefined()

    await deleteButton.trigger('click')
    await flushPromises()
    expect(apiDeleteMock).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it.each(['engineer', 'admin'] as const)('%s может привязывать и удалять узлы', async (role) => {
    pageAuth.role = role

    const wrapper = mount(DevicesAdd)
    await flushPromises()

    expect(wrapper.text()).not.toContain('Добавление устройств доступно инженеру или администратору.')
    const deleteButton = wrapper.find('[data-test="delete-node-1"]')
    expect(deleteButton.exists()).toBe(true)
    expect(deleteButton.attributes('disabled')).toBeUndefined()

    wrapper.unmount()
  })
})
