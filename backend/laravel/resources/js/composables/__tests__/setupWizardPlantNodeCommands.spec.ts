import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import {
  canSelectPlant,
  createSetupWizardPlantNodeCommands,
  resolveSelectedPlant,
} from '@/composables/setupWizardPlantNodeCommands'
import type { Plant, SetupWizardLoadingState } from '@/composables/setupWizardTypes'

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
  it('считает привязку завершенной только после подтверждения ноды и применяет биндинги', async () => {
    const showToast = vi.fn()
    const apiPost = vi.fn()
      .mockResolvedValueOnce({ data: { status: 'ok', data: { validated: true } } })
      .mockResolvedValueOnce({ data: { status: 'ok', data: { applied: true } } })
    const apiPatch = vi.fn()
      .mockResolvedValue({
        data: {
          status: 'ok',
          data: { id: 101, zone_id: null, pending_zone_id: 20 },
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
    const selectedNodeIds = ref<number[]>([101])

    const commands = createSetupWizardPlantNodeCommands({
      api: {
        get: apiGet,
        post: apiPost,
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
      ph_correction: null,
      ec_correction: null,
      accumulation: null,
      climate: null,
      light: null,
    })

    expect(apiPost).toHaveBeenCalledWith(
      '/setup-wizard/validate-devices',
      expect.objectContaining({
        zone_id: 20,
        selected_node_ids: [101],
      })
    )
    expect(apiPost).toHaveBeenCalledWith(
      '/setup-wizard/apply-device-bindings',
      expect.objectContaining({
        zone_id: 20,
      })
    )
    expect(apiGet).toHaveBeenCalledWith('/nodes', { params: { unassigned: true } })
    expect(attachedNodesCount.value).toBe(1)
    expect(loadAvailableNodes).toHaveBeenCalled()
  })
})
