import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPatchMock = vi.hoisted(() => vi.fn())

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

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: (url: string, config?: any) => {
        const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
        return apiGetMock(finalUrl, config)
      },
      patch: (url: string, data?: any, config?: any) => {
        const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
        return apiPatchMock(finalUrl, data, config)
      },
    },
  }),
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

vi.mock('@inertiajs/vue3', () => ({
  router: {
    visit: vi.fn(),
  },
}))

import DevicesAdd from '../Add.vue'

describe('Devices/Add.vue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiGetMock.mockReset()
    apiPatchMock.mockReset()

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
  })

  it('renders new nodes from paginated API responses', async () => {
    const wrapper = mount(DevicesAdd)
    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/nodes', { params: { unassigned: true } })
    expect(wrapper.text()).toContain('UID: nd-clim-1')
    expect(wrapper.text()).not.toContain('Новых нод не найдено')

    wrapper.unmount()
  })
})
