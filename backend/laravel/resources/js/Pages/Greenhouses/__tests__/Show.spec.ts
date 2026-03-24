import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import GreenhouseShow from '../Show.vue'

const sendZoneCommandMock = vi.hoisted(() => vi.fn())
const apiGetMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn())
const getDocumentMock = vi.hoisted(() => vi.fn())
const updateDocumentMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())

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
  default: { name: 'Button', props: ['size', 'variant', 'disabled'], template: '<button :disabled="disabled"><slot /></button>' },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', props: ['variant'], template: '<span><slot /></span>' },
}))

vi.mock('@/Components/MetricCard.vue', () => ({
  default: { name: 'MetricCard', props: ['label', 'value'], template: '<div class="metric">{{ label }}{{ value }}</div>' },
}))

vi.mock('@/Components/GreenhouseClimateConfiguration.vue', () => ({
  default: {
    name: 'GreenhouseClimateConfiguration',
    props: ['canConfigure', 'applying', 'applyLabel'],
    emits: ['apply', 'update:enabled'],
    template: `
      <div class="greenhouse-climate-configuration">
        <button
          class="greenhouse-climate-apply"
          :disabled="!canConfigure || applying"
          @click="$emit('apply')"
        >
          {{ applyLabel }}
        </button>
      </div>
    `,
  },
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
      get: apiGetMock,
      post: apiPostMock,
    },
  }),
}))

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    getDocument: getDocumentMock,
    updateDocument: updateDocumentMock,
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: showToastMock,
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
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    getDocumentMock.mockReset()
    updateDocumentMock.mockReset()
    showToastMock.mockReset()
    apiGetMock.mockResolvedValue({ data: { data: [] } })
    apiPostMock.mockResolvedValue({ data: { status: 'ok' } })
    getDocumentMock.mockResolvedValue({
      payload: {
        active_mode: null,
        profiles: {},
      },
      bindings: {
        climate_sensors: [],
        weather_station_sensors: [],
        vent_actuators: [],
        fan_actuators: [],
      },
    })
    updateDocumentMock.mockResolvedValue({
      payload: {
        active_mode: 'setup',
        profiles: {
          setup: {
            mode: 'setup',
            is_active: true,
            subsystems: { climate: { enabled: true, execution: {} } },
            updated_at: '2026-03-24T04:00:00Z',
          },
        },
      },
      bindings: {
        climate_sensors: [],
        weather_station_sensors: [],
        vent_actuators: [],
        fan_actuators: [],
      },
    })
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

    const button = findButton(wrapper, 'Сохранить климат теплицы')
    expect(button).toBeDefined()
    expect(button?.element.hasAttribute('disabled')).toBe(false)
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

    const button = findButton(wrapper, 'Сохранить климат теплицы')
    expect(button).toBeDefined()
    expect(button?.element.hasAttribute('disabled')).toBe(true)
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
    expect(maintenanceButton?.element.hasAttribute('disabled')).toBe(true)
  })

  it('разрешает обслуживание для климат-узлов', () => {
    apiGetMock.mockResolvedValue({
      data: {
        data: [
          { id: 2, uid: 'climate-1', type: 'climate', status: 'online', lifecycle_state: 'ACTIVE' },
        ],
      },
    })

    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    return flushPromises().then(() => {
      const maintenanceButton = findButton(wrapper, 'В обслуживание')
      expect(maintenanceButton).toBeDefined()
      expect(maintenanceButton?.element.hasAttribute('disabled')).toBe(false)
    })
  })

  it('сохраняет климат теплицы через unified authority', async () => {
    apiPostMock.mockResolvedValue({ data: { status: 'ok' } })

    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    await flushPromises()

    const maintenanceButton = findButton(wrapper, 'В обслуживание')
    const climateButton = findButton(wrapper, 'Сохранить климат теплицы')
    expect(climateButton).toBeDefined()
    await climateButton?.trigger('click')

    await flushPromises()
    expect(maintenanceButton).toBeDefined()
    expect(apiPostMock).toHaveBeenCalledWith('/setup-wizard/apply-greenhouse-climate-bindings', expect.any(Object))
    expect(updateDocumentMock).toHaveBeenCalledWith('greenhouse', 1, 'greenhouse.logic_profile', expect.objectContaining({
      active_mode: 'setup',
      profiles: expect.any(Object),
    }))
    expect(showToastMock).toHaveBeenCalledWith('Климат теплицы сохранён.', 'success', expect.any(Number))
  })
})
