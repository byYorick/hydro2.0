import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import {
  canSelectPlant,
  createSetupWizardPlantNodeCommands,
  resolveSelectedPlant,
} from '@/composables/setupWizardPlantNodeCommands'
import type { Plant, SetupWizardLoadingState } from '@/composables/setupWizardTypes'

const canAssignToZoneMock = vi.hoisted(() => vi.fn())
const getStateLabelMock = vi.hoisted(() => vi.fn())
const handleErrorMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useNodeLifecycle', () => ({
  useNodeLifecycle: () => ({
    canAssignToZone: canAssignToZoneMock,
    getStateLabel: getStateLabelMock,
  }),
}))

vi.mock('@/composables/useErrorHandler', () => ({
  useErrorHandler: () => ({
    handleError: handleErrorMock,
  }),
}))

function createLoadingState(): SetupWizardLoadingState {
  return {
    greenhouses: false,
    zones: false,
    plants: false,
    recipes: false,
    nodes: false,
    stepGreenhouse: false,
    stepZone: false,
    stepPlant: false,
    stepRecipe: false,
    stepDevices: false,
    stepAutomation: false,
    stepLaunch: false,
  }
}

describe('setupWizardPlantNodeCommands helpers', () => {
  it('canSelectPlant учитывает права и выбранный id', () => {
    expect(canSelectPlant(true, 1)).toBe(true)
    expect(canSelectPlant(false, 1)).toBe(false)
    expect(canSelectPlant(true, null)).toBe(false)
  })

  it('resolveSelectedPlant возвращает найденное растение или null', () => {
    const plants: Plant[] = [
      { id: 1, name: 'Tomato' },
      { id: 2, name: 'Basil' },
    ]

    expect(resolveSelectedPlant(plants, 2)).toEqual({ id: 2, name: 'Basil' })
    expect(resolveSelectedPlant(plants, 999)).toBeNull()
    expect(resolveSelectedPlant(plants, null)).toBeNull()
  })
})

describe('setupWizardPlantNodeCommands.selectPlant', () => {
  it('не выбирает растение без прав', () => {
    const showToast = vi.fn()

    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: vi.fn(),
        post: vi.fn(),
        patch: vi.fn(),
      },
      loading: createLoadingState(),
      canConfigure: computed(() => false),
      showToast,
      availableNodes: ref([]),
      availablePlants: ref([{ id: 1, name: 'Tomato' }]),
      selectedPlantId: ref(1),
      selectedZone: ref(null),
      selectedPlant: ref(null),
      selectedNodeIds: ref([]),
      attachedNodesCount: ref(0),
      plantForm: {
        name: '',
        species: '',
        variety: '',
      },
      loaders: {
        loadPlants: vi.fn(),
        loadAvailableNodes: vi.fn(),
      },
    })

    commands.selectPlant()

    expect(showToast).not.toHaveBeenCalled()
  })

  it('не выбирает растение если id отсутствует', () => {
    const showToast = vi.fn()

    const selectedPlant = ref<Plant | null>(null)
    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: vi.fn(),
        post: vi.fn(),
        patch: vi.fn(),
      },
      loading: createLoadingState(),
      canConfigure: computed(() => true),
      showToast,
      availableNodes: ref([]),
      availablePlants: ref([{ id: 1, name: 'Tomato' }]),
      selectedPlantId: ref(null),
      selectedZone: ref(null),
      selectedPlant,
      selectedNodeIds: ref([]),
      attachedNodesCount: ref(0),
      plantForm: {
        name: '',
        species: '',
        variety: '',
      },
      loaders: {
        loadPlants: vi.fn(),
        loadAvailableNodes: vi.fn(),
      },
    })

    commands.selectPlant()

    expect(selectedPlant.value).toBeNull()
    expect(showToast).not.toHaveBeenCalled()
  })

  it('не выбирает растение если id не найден', () => {
    const showToast = vi.fn()

    const selectedPlant = ref<Plant | null>(null)
    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: vi.fn(),
        post: vi.fn(),
        patch: vi.fn(),
      },
      loading: createLoadingState(),
      canConfigure: computed(() => true),
      showToast,
      availableNodes: ref([]),
      availablePlants: ref([{ id: 1, name: 'Tomato' }]),
      selectedPlantId: ref(2),
      selectedZone: ref(null),
      selectedPlant,
      selectedNodeIds: ref([]),
      attachedNodesCount: ref(0),
      plantForm: {
        name: '',
        species: '',
        variety: '',
      },
      loaders: {
        loadPlants: vi.fn(),
        loadAvailableNodes: vi.fn(),
      },
    })

    commands.selectPlant()

    expect(selectedPlant.value).toBeNull()
    expect(showToast).not.toHaveBeenCalled()
  })

  it('выбирает растение при валидных правах и id', () => {
    const showToast = vi.fn()

    const selectedPlant = ref<Plant | null>(null)
    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: vi.fn(),
        post: vi.fn(),
        patch: vi.fn(),
      },
      loading: createLoadingState(),
      canConfigure: computed(() => true),
      showToast,
      availableNodes: ref([]),
      availablePlants: ref([{ id: 1, name: 'Tomato' }]),
      selectedPlantId: ref(1),
      selectedZone: ref(null),
      selectedPlant,
      selectedNodeIds: ref([]),
      attachedNodesCount: ref(0),
      plantForm: {
        name: '',
        species: '',
        variety: '',
      },
      loaders: {
        loadPlants: vi.fn(),
        loadAvailableNodes: vi.fn(),
      },
    })

    commands.selectPlant()

    expect(selectedPlant.value?.id).toBe(1)
    expect(showToast).toHaveBeenCalledWith('Растение выбрано', 'success', expect.any(Number))
  })
})

describe('setupWizardPlantNodeCommands.attachNodesToZone', () => {
  it('считает привязку завершенной после подтверждения и применяет биндинги в массовом режиме', async () => {
    canAssignToZoneMock.mockResolvedValue(true)
    getStateLabelMock.mockReturnValue('Зарегистрирован')

    const showToast = vi.fn()
    const apiPost = vi.fn()
      .mockResolvedValueOnce({ data: { status: 'ok', data: { validated: true } } })
      .mockResolvedValueOnce({ data: { status: 'ok', data: { applied: true } } })
    const apiPatch = vi.fn()
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 101, zone_id: null, pending_zone_id: 20 },
        },
      })
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 102, zone_id: null, pending_zone_id: 20 },
        },
      })
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 103, zone_id: null, pending_zone_id: 20 },
        },
      })
    const apiGet = vi.fn().mockResolvedValue({
      data: {
        status: 'ok',
        data: [],
      },
    })
    const loadAvailableNodes = vi.fn().mockResolvedValue(undefined)
    const attachedNodesCount = ref(0)
    const selectedNodeIds = ref<number[]>([101, 102, 103])

    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: apiGet,
        post: apiPost,
        patch: apiPatch,
      },
      loading: createLoadingState(),
      canConfigure: computed(() => true),
      showToast,
      availableNodes: ref([
        { id: 101, uid: 'nd-test-101', lifecycle_state: 'REGISTERED_BACKEND' },
        { id: 102, uid: 'nd-test-102', lifecycle_state: 'REGISTERED_BACKEND' },
        { id: 103, uid: 'nd-test-103', lifecycle_state: 'REGISTERED_BACKEND' },
      ]),
      availablePlants: ref([]),
      selectedPlantId: ref(null),
      selectedZone: ref({ id: 20, name: 'Zone A', greenhouse_id: 10 }),
      selectedPlant: ref(null),
      selectedNodeIds,
      attachedNodesCount,
      plantForm: {
        name: '',
        species: '',
        variety: '',
      },
      loaders: {
        loadPlants: vi.fn(),
        loadAvailableNodes,
      },
    })

    await commands.attachNodesToZone({
      irrigation: 101,
      ph_correction: 102,
      ec_correction: 103,
      accumulation: null,
      climate: null,
      light: null,
    })

    expect(apiPost).toHaveBeenCalledWith(
      '/setup-wizard/validate-devices',
      expect.objectContaining({
        zone_id: 20,
        selected_node_ids: [101, 102, 103],
      })
    )
    expect(apiPost).toHaveBeenCalledWith(
      '/setup-wizard/validate-devices',
      expect.objectContaining({
        assignments: expect.objectContaining({
          irrigation: 101,
          ph_correction: 102,
          ec_correction: 103,
          accumulation: 101,
        }),
      })
    )
    expect(apiPost).toHaveBeenCalledWith(
      '/setup-wizard/apply-device-bindings',
      expect.objectContaining({
        zone_id: 20,
      })
    )
    expect(apiGet).toHaveBeenCalledWith('/nodes', { params: { unassigned: true } })
    expect(apiPatch).toHaveBeenCalledTimes(3)
    expect(attachedNodesCount.value).toBe(3)
    expect(loadAvailableNodes).toHaveBeenCalled()
  })

  it('блокирует привязку ноды с неподходящим lifecycle состоянием', async () => {
    canAssignToZoneMock.mockResolvedValue(true)
    getStateLabelMock.mockReturnValue('Активен')
    const showToast = vi.fn()
    const apiPatch = vi.fn()

    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: vi.fn(),
        post: vi.fn(),
        patch: apiPatch,
      },
      loading: createLoadingState(),
      canConfigure: computed(() => true),
      showToast,
      availableNodes: ref([{ id: 101, uid: 'nd-test-101', lifecycle_state: 'ACTIVE' }]),
      availablePlants: ref([]),
      selectedPlantId: ref(null),
      selectedZone: ref({ id: 20, name: 'Zone A', greenhouse_id: 10 }),
      selectedPlant: ref(null),
      selectedNodeIds: ref([101]),
      attachedNodesCount: ref(0),
      plantForm: {
        name: '',
        species: '',
        variety: '',
      },
      loaders: {
        loadPlants: vi.fn(),
        loadAvailableNodes: vi.fn(),
      },
    })

    await commands.attachNodesToZone()

    expect(apiPatch).not.toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining('Текущее состояние: Активен'),
      'error',
      6000
    )
  })

  it('для ноды без lifecycle проверяет доступность перехода через canAssignToZone', async () => {
    canAssignToZoneMock.mockResolvedValue(false)
    getStateLabelMock.mockReturnValue('Зарегистрирован')
    const showToast = vi.fn()
    const apiPatch = vi.fn()

    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: vi.fn(),
        post: vi.fn(),
        patch: apiPatch,
      },
      loading: createLoadingState(),
      canConfigure: computed(() => true),
      showToast,
      availableNodes: ref([{ id: 101, uid: 'nd-test-101' }]),
      availablePlants: ref([]),
      selectedPlantId: ref(null),
      selectedZone: ref({ id: 20, name: 'Zone A', greenhouse_id: 10 }),
      selectedPlant: ref(null),
      selectedNodeIds: ref([101]),
      attachedNodesCount: ref(0),
      plantForm: {
        name: '',
        species: '',
        variety: '',
      },
      loaders: {
        loadPlants: vi.fn(),
        loadAvailableNodes: vi.fn(),
      },
    })

    await commands.attachNodesToZone()

    expect(canAssignToZoneMock).toHaveBeenCalledWith(101)
    expect(apiPatch).not.toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining('должен быть зарегистрирован (REGISTERED_BACKEND)'),
      'error',
      6000
    )
  })
})
