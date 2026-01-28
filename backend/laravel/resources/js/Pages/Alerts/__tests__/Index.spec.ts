import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))
vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', template: '<button><slot /></button>' },
}))
vi.mock('@/Components/Modal.vue', () => ({
  default: { name: 'Modal', props: ['open'], template: '<div v-if="open"><slot /><slot name="footer" /></div>' },
}))

const itemsDataValue = vi.hoisted(() => [
  { 
    id: 1, 
    type: 'PH_HIGH', 
    zone: { id: 1, name: 'Zone A1' },
    zone_id: 1,
    created_at: '2025-01-01T10:00:00Z',
    status: 'active',
  },
  { 
    id: 2, 
    type: 'EC_LOW', 
    zone: { id: 2, name: 'Zone B2' },
    zone_id: 2,
    created_at: '2025-01-01T11:00:00Z',
    status: 'resolved',
  },
  { 
    id: 3, 
    type: 'TEMP_HIGH', 
    zone: { id: 1, name: 'Zone A1' },
    zone_id: 1,
    created_at: '2025-01-01T12:00:00Z',
    status: 'active',
  },
])

const axiosGetMock = vi.hoisted(() => vi.fn())
const axiosPatchMock = vi.hoisted(() => vi.fn())
const routerReloadMock = vi.hoisted(() => vi.fn())

vi.mock('axios', () => {
  const axiosInstance = {
    get: (...args: Parameters<typeof axiosGetMock>) => axiosGetMock(...args),
    patch: (url: string, data?: any, config?: any) => axiosPatchMock(url, data, config),
    interceptors: {
      request: {
        use: vi.fn(),
        eject: vi.fn(),
      },
      response: {
        use: vi.fn(),
        eject: vi.fn(),
      },
  },
  }

  return {
    default: {
      ...axiosInstance,
      create: () => axiosInstance,
    },
  }
})

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      alerts: itemsDataValue,
    },
  }),
  router: {
    reload: routerReloadMock,
  },
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

const subscribeAlertsMock = vi.hoisted(() => vi.fn(() => vi.fn()))

vi.mock('@/ws/subscriptions', () => ({
  subscribeAlerts: subscribeAlertsMock,
}))

import AlertsIndex from '../Index.vue'
import { config } from '@vue/test-utils'

config.global.components.RecycleScroller = {
  name: 'RecycleScroller',
  props: ['items', 'itemSize', 'keyField'],
  template: `
    <div>
      <slot
        v-for="(item, index) in items"
        :item="item"
        :index="index"
      />
    </div>
  `,
}

describe('Alerts/Index.vue', () => {
  const mountWithPinia = () => mount(AlertsIndex, {
    global: {
      plugins: [createPinia()],
    },
  })

  beforeEach(() => {
    setActivePinia(createPinia())
    axiosGetMock.mockReset()
    axiosPatchMock.mockClear()
    routerReloadMock.mockClear()
    subscribeAlertsMock.mockClear()
    axiosGetMock.mockResolvedValue({ data: { data: itemsDataValue } })
    axiosPatchMock.mockResolvedValue({ data: { status: 'ok' } })
  })

  const findRows = (wrapper: ReturnType<typeof mount>) => wrapper.findAll('[data-testid^="alert-row-"]')

  it('фильтрует только активные', async () => {
    const wrapper = mountWithPinia()
    // onlyActive=true по умолчанию -> исключает resolved
    await wrapper.vm.$nextTick()
    const rows = findRows(wrapper)
    expect(rows.length).toBeGreaterThan(0)
    rows.forEach(r => expect(r.text()).not.toContain('Решено'))
  })

  it('фильтрует по зоне', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()
    const select = wrapper.find('select[data-testid="alerts-filter-zone"]')
    await select.setValue('1')
    await wrapper.vm.$nextTick()
    const rows = findRows(wrapper)
    expect(rows.length).toBeGreaterThanOrEqual(1)
    rows.forEach(r => expect(r.text()).toMatch(/A1/))
  })

  it('подтверждение алерта вызывает API', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()
    
    // Эмулируем выбор алерта и подтверждение напрямую через метод
    // чтобы избежать сложной работы со слотами виртуализатора
    // @ts-ignore accessing component instance internals for testing
    wrapper.vm.confirm = { open: true, alertId: itemsDataValue[0].id, loading: false }

    // @ts-ignore
    await wrapper.vm.doResolve()
    await new Promise(resolve => setTimeout(resolve, 10))
            
    expect(axiosPatchMock).toHaveBeenCalled()
  })
})

