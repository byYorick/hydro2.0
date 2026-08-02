import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import GreenhouseShow from '../Show.vue'

const sendZoneCommandMock = vi.hoisted(() => vi.fn())
const nodesListMock = vi.hoisted(() => vi.fn())
const nodesLifecycleTransitionMock = vi.hoisted(() => vi.fn())
const setupWizardValidateMock = vi.hoisted(() => vi.fn())
const setupWizardApplyMock = vi.hoisted(() => vi.fn())
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

vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', props: ['size', 'variant', 'disabled'], template: '<button :disabled="disabled"><slot /></button>' },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', props: ['variant'], template: '<span><slot /></span>' },
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
  default: { name: 'ConfirmModal', props: ['open'], template: '<div class="confirm-modal"><slot /></div>' },
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

vi.mock('@/services/api', () => ({
  api: {
    nodes: {
      list: nodesListMock,
      lifecycleTransition: nodesLifecycleTransitionMock,
    },
    setupWizard: {
      validateGreenhouseClimateDevices: setupWizardValidateMock,
      applyGreenhouseClimateBindings: setupWizardApplyMock,
    },
  },
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
    nodesListMock.mockReset()
    nodesLifecycleTransitionMock.mockReset()
    setupWizardValidateMock.mockReset()
    setupWizardApplyMock.mockReset()
    getDocumentMock.mockReset()
    updateDocumentMock.mockReset()
    showToastMock.mockReset()
    nodesListMock.mockResolvedValue([])
    nodesLifecycleTransitionMock.mockResolvedValue({})
    setupWizardValidateMock.mockResolvedValue({ status: 'ok' })
    setupWizardApplyMock.mockResolvedValue({ status: 'ok' })
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

  it('рендерит KPI целыми числами без десятичных', () => {
    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [],
        nodeSummary: { online: 1, offline: 2, total: 3 },
        activeAlerts: 13,
      },
    })

    expect(wrapper.get('[data-testid="greenhouse-kpi-zones"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="greenhouse-kpi-zones"]').text()).not.toContain('1.00')
    expect(wrapper.get('[data-testid="greenhouse-kpi-nodes"]').text()).toContain('1/3')
    expect(wrapper.get('[data-testid="greenhouse-kpi-alerts"]').text()).toContain('13')
    expect(wrapper.get('[data-testid="greenhouse-kpi-alerts"]').text()).toContain('Требуют внимания')
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

  it('не открывает обслуживание без подходящих lifecycle-состояний', async () => {
    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [
          { id: 1, uid: 'node-1', type: 'ph', status: 'online', lifecycle_state: 'REGISTERED_BACKEND' },
        ],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    const maintenanceButton = findButton(wrapper, 'В обслуживание')
    expect(maintenanceButton).toBeDefined()
    expect(maintenanceButton?.element.hasAttribute('disabled')).toBe(false)
    await maintenanceButton?.trigger('click')
    expect(showToastMock).toHaveBeenCalledWith(
      'Нет узлов в состояниях ASSIGNED_TO_ZONE / ACTIVE / DEGRADED.',
      'warning',
      expect.any(Number),
    )
  })

  it('разрешает обслуживание для узлов зон теплицы', () => {
    const wrapper = mount(GreenhouseShow, {
      props: {
        greenhouse: baseGreenhouse,
        zones: [baseZone],
        nodes: [
          { id: 2, uid: 'irrig-1', type: 'irrig', status: 'online', lifecycle_state: 'ASSIGNED_TO_ZONE' },
        ],
        nodeSummary: baseNodeSummary,
        activeAlerts: 0,
      },
    })

    const maintenanceButton = findButton(wrapper, 'В обслуживание')
    expect(maintenanceButton).toBeDefined()
    expect(maintenanceButton?.element.hasAttribute('disabled')).toBe(false)
  })

  it('сохраняет климат теплицы через unified authority', async () => {
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
    expect(setupWizardApplyMock).toHaveBeenCalledWith(expect.any(Object))
    expect(updateDocumentMock).toHaveBeenCalledWith('greenhouse', 1, 'greenhouse.logic_profile', expect.objectContaining({
      active_mode: 'setup',
      profiles: expect.any(Object),
    }))
    expect(showToastMock).toHaveBeenCalledWith('Климат теплицы сохранён.', 'success', expect.any(Number))
  })
})
