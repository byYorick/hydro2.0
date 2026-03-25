import { mount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import GrowthCycleWizard from '../GrowthCycleWizard.vue'

const fetchZoneDevicesMock = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const loadZoneReadinessMock = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const refreshDbCalibrationsMock = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const showToastMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn(() => Promise.resolve({ data: { status: 'ok' } })))

vi.mock('@/composables/useGrowthCycleWizard', () => ({
  useGrowthCycleWizard: () => ({
    currentStep: ref(5),
    recipeMode: ref('select'),
    loading: ref(false),
    error: ref(null),
    errorDetails: ref([]),
    validationErrors: ref([]),
    form: ref({
      zoneId: 7,
      startedAt: '2026-03-25T10:00',
      expectedHarvestAt: '',
    }),
    climateForm: ref({}),
    waterForm: ref({
      targetPh: 5.8,
      targetEc: 1.6,
      systemType: 'drip',
      intervalMinutes: 30,
      durationSeconds: 120,
      cleanTankFillL: 200,
      nutrientTankTargetL: 180,
      irrigationBatchL: 20,
      tanksCount: 2,
    }),
    lightingForm: ref({}),
    availableZones: ref([]),
    availablePlants: ref([]),
    availableRecipes: ref([]),
    selectedRecipe: ref(null),
    selectedRecipeId: ref(null),
    selectedRevisionId: ref(null),
    selectedPlantId: ref(null),
    availableRevisions: computed(() => []),
    selectedRevision: ref(null),
    steps: [
      { key: 'zone', label: 'Зона' },
      { key: 'plant', label: 'Растение' },
      { key: 'recipe', label: 'Рецепт' },
      { key: 'logic', label: 'Период' },
      { key: 'automation', label: 'Автоматика' },
      { key: 'calibration', label: 'Насосы' },
      { key: 'confirm', label: 'Запуск' },
    ],
    wizardTitle: computed(() => 'Запуск нового цикла выращивания'),
    minStartDate: computed(() => '2026-03-25T10:00'),
    totalDurationDays: computed(() => 0),
    tanksCount: computed(() => 2),
    canProceed: computed(() => true),
    canSubmit: computed(() => false),
    nextStepBlockedReason: computed(() => ''),
    zoneDevices: ref([{ id: 1, uid: 'node-1', type: 'unknown', status: 'unknown', channels: [] }]),
    isZoneDevicesLoading: ref(false),
    zoneDevicesLoaded: ref(true),
    zoneDevicesError: ref(null),
    zoneReadiness: ref(null),
    zoneReadinessLoading: ref(false),
    formatDateTime: (value: string) => value,
    formatDate: (value: string) => value,
    onZoneSelected: vi.fn(),
    onRecipeSelected: vi.fn(),
    onRecipeCreated: vi.fn(),
    fetchZoneDevices: fetchZoneDevicesMock,
    loadZoneReadiness: loadZoneReadinessMock,
    nextStep: vi.fn(),
    prevStep: vi.fn(),
    onSubmit: vi.fn(),
    handleClose: vi.fn(),
  }),
}))

vi.mock('@/composables/usePumpCalibration', () => ({
  usePumpCalibration: () => ({
    componentOptions: [
      { value: 'npk', label: 'NPK' },
      { value: 'calcium', label: 'Calcium' },
    ],
    pumpChannels: computed(() => [
      { id: 101, label: 'Node / pump_a', calibration: { ml_per_sec: 1.2 } },
      { id: 102, label: 'Node / pump_b', calibration: null },
    ]),
    calibratedChannels: computed(() => [
      { id: 101, label: 'Node / pump_a', calibration: { ml_per_sec: 1.2 } },
    ]),
    autoComponentMap: computed(() => ({
      npk: 101,
      calcium: 102,
    })),
    channelById: computed(() => new Map([
      [101, { id: 101, label: 'Node / pump_a', calibration: { ml_per_sec: 1.2 } }],
      [102, { id: 102, label: 'Node / pump_b', calibration: null }],
    ])),
    refreshDbCalibrations: refreshDbCalibrationsMock,
  }),
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      post: apiPostMock,
    },
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}))

vi.mock('@/composables/useZones', () => ({
  useZones: () => ({
    fetchZones: vi.fn(),
  }),
}))

vi.mock('@/Components/Modal.vue', () => ({
  default: {
    props: ['open', 'title'],
    template: '<div><slot /><slot name="footer" /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/ErrorBoundary.vue', () => ({
  default: {
    template: '<div><slot /></div>',
  },
}))

vi.mock('@/Components/GrowCycle/ReadinessChecklist.vue', () => ({
  default: {
    template: '<div data-test="readiness-checklist" />',
  },
}))

vi.mock('@/Components/PumpCalibrationModal.vue', () => ({
  default: {
    template: '<div data-test="pump-calibration-modal" />',
  },
}))

vi.mock('@/Components/RecipeCreateWizard.vue', () => ({
  default: {
    template: '<div data-test="recipe-create-wizard" />',
  },
}))

describe('GrowthCycleWizard', () => {
  it('показывает единый статус калибровки и открывает общую pump calibration modal', async () => {
    const wrapper = mount(GrowthCycleWizard, {
      props: {
        show: true,
        zoneId: 7,
        zoneName: 'Zone 7',
      },
    })

    expect(wrapper.text()).toContain('Используется тот же calibration flow')
    expect(wrapper.text()).toContain('NPK: готово')
    expect(wrapper.text()).toContain('Calcium: не сохранено')

    const openButton = wrapper.findAll('button').find((button) => button.text().includes('Открыть калибровку насосов'))
    expect(openButton).toBeDefined()
    await openButton!.trigger('click')

    expect(wrapper.find('[data-test="pump-calibration-modal"]').exists()).toBe(true)
    expect(fetchZoneDevicesMock).toHaveBeenCalled()
    expect(refreshDbCalibrationsMock).toHaveBeenCalled()
  })
})
