import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import GreenhouseShow from '../Show.vue'

const sendZoneCommandMock = vi.hoisted(() => vi.fn())

const usePageMock = vi.hoisted(() => vi.fn(() => ({
  props: {
    auth: {
      user: {
        role: 'agronomist',
      },
    },
  },
})))

const usePageMockInstance = usePageMock()

vi.mock('@inertiajs/vue3', () => ({
  Link: { name: 'Link', props: ['href'], template: '<a><slot /></a>' },
  router: { reload: vi.fn() },
  usePage: () => usePageMockInstance,
}))

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', props: ['size', 'variant'], template: '<button><slot /></button>' },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', props: ['variant'], template: '<span><slot /></span>' },
}))

vi.mock('@/Components/MetricCard.vue', () => ({
  default: { name: 'MetricCard', props: ['label', 'value'], template: '<div class="metric">{{ label }}{{ value }}</div>' },
}))

vi.mock('@/Pages/Zones/ZoneCard.vue', () => ({
  default: { name: 'ZoneCard', props: ['zone'], template: '<div class="zone-card">{{ zone.name }}</div>' },
}))

vi.mock('@/Components/ZoneCreateWizard.vue', () => ({
  default: { name: 'ZoneCreateWizard', props: ['show'], template: '<div class="zone-create-wizard" />' },
}))

vi.mock('@/Components/ZoneActionModal.vue', () => ({
  default: { name: 'ZoneActionModal', props: ['show'], emits: ['submit', 'close'], template: '<div class="zone-action-modal" />' },
}))

vi.mock('@/Components/ConfirmModal.vue', () => ({
  default: { name: 'ConfirmModal', props: ['open'], template: '<div class="confirm-modal" />' },
}))

vi.mock('@/composables/useModal', () => ({
  useSimpleModal: () => ({
    isOpen: false,
    open: vi.fn(),
    close: vi.fn(),
  }),
}))

vi.mock('@/composables/useCommands', () => ({
  useCommands: () => ({
    sendZoneCommand: sendZoneCommandMock,
  }),
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      post: vi.fn().mockResolvedValue({ data: {} }),
    },
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

const baseGreenhouse = {
  id: 1,
  name: 'Main Greenhouse',
  description: null,
  type: 'greenhouse',
  timezone: 'UTC',
}

const baseZone = {
  id: 10,
  uid: 'zone-10',
  name: 'Zone A',
  status: 'RUNNING',
  greenhouse_id: 1,
  targets: {},
  telemetry: null,
  cycles: [],
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
}

const baseNodeSummary = {
  online: 0,
  offline: 0,
  total: 0,
}

function findButton(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll('button').find(btn => btn.text().includes(label))
}

describe('Greenhouses/Show.vue', () => {
  beforeEach(() => {
    usePageMockInstance.props.auth.user.role = 'agronomist'
    sendZoneCommandMock.mockReset()
    sendZoneCommandMock.mockResolvedValue({ id: 1 })
  })

  it('показывает активную кнопку управления климатом для агронома', () => {
    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    const button = findButton(wrapper, 'Управление климатом')
    expect(button).toBeDefined()
    expect(button?.attributes('disabled')).toBeUndefined()
  })

  it('блокирует управление климатом для не агронома', () => {
    usePageMockInstance.props.auth.user.role = 'viewer'

    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    const button = findButton(wrapper, 'Управление климатом')
    expect(button).toBeDefined()
    expect(button?.attributes('disabled')).toBeDefined()
  })

  it('учитывает только климат-узлы для обслуживания', () => {
    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [
          { id: 1, uid: 'node-1', type: 'sensor', status: 'online', lifecycle_state: 'ACTIVE' },
        ],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    const maintenanceButton = findButton(wrapper, 'В обслуживание')
    expect(maintenanceButton).toBeDefined()
    expect(maintenanceButton?.attributes('disabled')).toBeDefined()
  })

  it('разрешает обслуживание для климат-узлов', () => {
    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [
          { id: 2, uid: 'climate-1', type: 'climate', status: 'online', lifecycle_state: 'ACTIVE' },
        ],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    const maintenanceButton = findButton(wrapper, 'В обслуживание')
    expect(maintenanceButton).toBeDefined()
    expect(maintenanceButton?.attributes('disabled')).toBeUndefined()
  })

  it('показывает список ошибок применения климата', async () => {
    sendZoneCommandMock
      .mockResolvedValueOnce({ id: 1 })
      .mockRejectedValueOnce({ message: 'Нода недоступна' })

    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [
          baseZone,
          { ...baseZone, id: 11, uid: 'zone-11', name: 'Zone B' },
        ],
        nodes: [],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    const climateButton = findButton(wrapper, 'Управление климатом')
    expect(climateButton).toBeDefined()
    await climateButton?.trigger('click')

    const modal = wrapper.findComponent({ name: 'ZoneActionModal' })
    expect(modal.exists()).toBe(true)
    modal.vm.$emit('submit', { params: { target_temp: 22, target_humidity: 60 } })

    await flushPromises()

    const failureBlock = wrapper.find('[data-testid="climate-failures"]')
    expect(failureBlock.exists()).toBe(true)
    expect(failureBlock.text()).toContain('Zone B')
    expect(failureBlock.text()).toContain('Нода недоступна')
  })
})
