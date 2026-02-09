import { computed, reactive, ref, watch, type Ref } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'

export interface TaxonomyOption {
  id: string
  label: string
  uses_substrate?: boolean
}

interface RecipePhaseDraft {
  name: string
  duration_days: number
  day_start_time: string
  light_hours: number
  ph_day: number
  ph_night: number
  ec_day: number
  ec_night: number
  temp_day: number
  temp_night: number
  humidity_day: number
  humidity_night: number
  irrigation_interval_sec: number
  irrigation_duration_sec: number
}

type TaxonomyKey = 'substrate_type' | 'growing_system' | 'seasonality'

interface UsePlantCreateModalOptions {
  show: Ref<boolean>
  taxonomies: Ref<Record<string, TaxonomyOption[]>>
  onClose: () => void
  onCreated: (plant: unknown) => void
}

const defaultSeasonality: TaxonomyOption[] = [
  { id: 'all_year', label: 'Круглый год' },
  { id: 'multi_cycle', label: 'Несколько циклов' },
  { id: 'seasonal', label: 'Сезонное выращивание' },
]

function createDefaultRecipePhases(): RecipePhaseDraft[] {
  return [
    {
      name: 'Рассада',
      duration_days: 10,
      day_start_time: '06:00:00',
      light_hours: 18,
      ph_day: 5.8,
      ph_night: 5.7,
      ec_day: 1.1,
      ec_night: 1.0,
      temp_day: 24,
      temp_night: 20,
      humidity_day: 70,
      humidity_night: 75,
      irrigation_interval_sec: 1200,
      irrigation_duration_sec: 20,
    },
    {
      name: 'Вегетация',
      duration_days: 18,
      day_start_time: '06:00:00',
      light_hours: 16,
      ph_day: 5.9,
      ph_night: 5.8,
      ec_day: 1.5,
      ec_night: 1.4,
      temp_day: 23,
      temp_night: 19,
      humidity_day: 65,
      humidity_night: 70,
      irrigation_interval_sec: 900,
      irrigation_duration_sec: 25,
    },
    {
      name: 'Цветение/плодоношение',
      duration_days: 24,
      day_start_time: '06:00:00',
      light_hours: 12,
      ph_day: 6.1,
      ph_night: 6.0,
      ec_day: 1.9,
      ec_night: 1.8,
      temp_day: 22,
      temp_night: 18,
      humidity_day: 58,
      humidity_night: 62,
      irrigation_interval_sec: 720,
      irrigation_duration_sec: 30,
    },
  ]
}

export function usePlantCreateModal(options: UsePlantCreateModalOptions) {
  const { show, taxonomies, onClose, onCreated } = options

  const { showToast } = useToast()
  const { api } = useApi(showToast)

  const loading = ref(false)
  const errors = reactive<Record<string, string>>({})
  const currentStep = ref(1)
  const createdPlantId = ref<number | null>(null)
  const createdPlantData = ref<unknown | null>(null)

  const localTaxonomies = ref<Record<string, TaxonomyOption[]>>({})

  const taxonomyOptions = computed(() => ({
    substrate_type: localTaxonomies.value.substrate_type ?? [],
    growing_system: localTaxonomies.value.growing_system ?? [],
    photoperiod_preset: localTaxonomies.value.photoperiod_preset ?? [],
  }))

  const seasonOptions = computed(() => localTaxonomies.value.seasonality ?? defaultSeasonality)

  const taxonomyWizard = reactive<{ open: boolean; key: TaxonomyKey; title: string }>({
    open: false,
    key: 'substrate_type',
    title: '',
  })

  const taxonomyWizardItems = computed(() => localTaxonomies.value[taxonomyWizard.key] ?? [])

  const form = reactive({
    name: '',
    species: '',
    variety: '',
    substrate_type: '',
    growing_system: '',
    photoperiod_preset: '',
    seasonality: '',
    description: '',
    recipe_name: '',
    recipe_description: '',
    recipe_phases: createDefaultRecipePhases() as RecipePhaseDraft[],
  })

  function resetForm() {
    form.name = ''
    form.species = ''
    form.variety = ''
    form.substrate_type = ''
    form.growing_system = ''
    form.photoperiod_preset = ''
    form.seasonality = ''
    form.description = ''
    form.recipe_name = ''
    form.recipe_description = ''
    form.recipe_phases = createDefaultRecipePhases()
    currentStep.value = 1
    createdPlantId.value = null
    createdPlantData.value = null
    Object.keys(errors).forEach((key) => delete errors[key])
  }

  const showSubstrateSelector = computed(() => {
    if (!form.growing_system) {
      return false
    }

    const selectedSystem = taxonomyOptions.value.growing_system.find(
      (option) => option.id === form.growing_system
    )

    if (typeof selectedSystem?.uses_substrate === 'boolean') {
      return selectedSystem.uses_substrate
    }
    return false
  })

  watch(
    show,
    (newVal: boolean) => {
      if (newVal) {
        resetForm()
        void loadTaxonomiesFromApi()
      }
    }
  )

  watch(
    taxonomies,
    (value) => {
      localTaxonomies.value = {
        substrate_type: value?.substrate_type ?? [],
        growing_system: value?.growing_system ?? [],
        photoperiod_preset: value?.photoperiod_preset ?? [],
        seasonality: value?.seasonality ?? defaultSeasonality,
      }
    },
    { immediate: true, deep: true }
  )

  watch(
    () => form.growing_system,
    () => {
      errors.growing_system = ''
      if (!showSubstrateSelector.value) {
        form.substrate_type = ''
      }
    }
  )

  async function loadTaxonomiesFromApi(): Promise<void> {
    try {
      const response = await api.get('/plant-taxonomies')
      const payload = extractData<Record<string, TaxonomyOption[]>>(response.data)
      if (!payload || typeof payload !== 'object') {
        return
      }

      localTaxonomies.value = {
        ...localTaxonomies.value,
        substrate_type: payload.substrate_type ?? localTaxonomies.value.substrate_type ?? [],
        growing_system: payload.growing_system ?? localTaxonomies.value.growing_system ?? [],
        photoperiod_preset: payload.photoperiod_preset ?? localTaxonomies.value.photoperiod_preset ?? [],
        seasonality: payload.seasonality ?? localTaxonomies.value.seasonality ?? defaultSeasonality,
      }
    } catch (error) {
      logger.error('Failed to load plant taxonomies', { error })
    }
  }

  function addRecipePhase(): void {
    form.recipe_phases.push({
      name: `Фаза ${form.recipe_phases.length + 1}`,
      duration_days: 14,
      day_start_time: '06:00:00',
      light_hours: 14,
      ph_day: 5.9,
      ph_night: 5.8,
      ec_day: 1.6,
      ec_night: 1.5,
      temp_day: 23,
      temp_night: 19,
      humidity_day: 62,
      humidity_night: 66,
      irrigation_interval_sec: 900,
      irrigation_duration_sec: 25,
    })
  }

  function removeRecipePhase(index: number): void {
    if (form.recipe_phases.length <= 1) {
      return
    }

    form.recipe_phases.splice(index, 1)
  }

  function openTaxonomyWizard(key: TaxonomyKey): void {
    taxonomyWizard.key = key
    taxonomyWizard.title = key === 'substrate_type'
      ? 'Справочник: субстрат'
      : key === 'growing_system'
        ? 'Справочник: система'
        : 'Справочник: сезонность'
    taxonomyWizard.open = true
  }

  function closeTaxonomyWizard(): void {
    taxonomyWizard.open = false
  }

  function handleTaxonomySaved(payload: { key: string; items: TaxonomyOption[] }): void {
    localTaxonomies.value = {
      ...localTaxonomies.value,
      [payload.key]: payload.items,
    }
  }

  function handleClose() {
    resetForm()
    onClose()
  }

  const stepTitle = computed(() => (currentStep.value === 1 ? 'Данные растения' : 'Рецепт выращивания'))
  const primaryLabel = computed(() => {
    if (currentStep.value === 1) {
      return 'Далее'
    }

    return 'Создать культуру и рецепт'
  })
  const isPrimaryDisabled = computed(() => {
    if (currentStep.value === 1) {
      return !form.name.trim() || !form.growing_system
    }

    return !form.recipe_name.trim() || form.recipe_phases.length === 0
  })

  function goBack() {
    currentStep.value = 1
    errors.general = ''
    errors.recipe_name = ''
    errors.growing_system = ''
  }

  async function createPlantIfNeeded(): Promise<boolean> {
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      species: form.species.trim() || null,
      variety: form.variety.trim() || null,
      substrate_type: form.substrate_type || null,
      growing_system: form.growing_system || null,
      photoperiod_preset: form.photoperiod_preset || null,
      seasonality: form.seasonality || null,
      description: form.description.trim() || null,
    }

    if (createdPlantId.value) {
      return true
    }

    try {
      const response = await api.post('/plants', payload)
      const plant = (response.data as any)?.data || response.data
      createdPlantId.value = plant?.id ?? null
      createdPlantData.value = plant
      logger.info('Plant created:', response.data)
      return true
    } catch (error: any) {
      logger.error('Failed to create plant:', error)
      if (error.response?.data?.errors) {
        Object.keys(error.response.data.errors).forEach((key) => {
          errors[key] = error.response.data.errors[key][0]
        })
      } else if (error.response?.data?.message) {
        errors.general = error.response.data.message
      }
      currentStep.value = 1
      return false
    }
  }

  async function createRecipeRevision(): Promise<number | null> {
    try {
      const recipeResponse = await api.post('/recipes', {
        name: form.recipe_name.trim(),
        description: form.recipe_description.trim() || null,
        plant_id: createdPlantId.value,
      })

      const recipePayload = extractData<Record<string, unknown>>(recipeResponse.data)
      const recipeId = typeof recipePayload?.id === 'number' ? recipePayload.id : null
      if (!recipeId) {
        throw new Error('Recipe ID missing')
      }

      const revisionResponse = await api.post(`/recipes/${recipeId}/revisions`, {
        description: 'Initial revision from plant wizard',
      })

      const revisionPayload = extractData<Record<string, unknown>>(revisionResponse.data)
      const revisionId = typeof revisionPayload?.id === 'number' ? revisionPayload.id : null
      if (!revisionId) {
        throw new Error('Recipe revision ID missing')
      }

      return revisionId
    } catch (error: any) {
      logger.error('Failed to create recipe:', error)
      if (error.response?.data?.errors) {
        Object.keys(error.response.data.errors).forEach((key) => {
          if (key === 'name') {
            errors.recipe_name = error.response.data.errors[key][0]
          } else {
            errors[key] = error.response.data.errors[key][0]
          }
        })
      } else if (error.response?.data?.message) {
        errors.general = error.response.data.message
      }
      return null
    }
  }

  async function createRecipePhases(revisionId: number): Promise<boolean> {
    try {
      const irrigationMode = showSubstrateSelector.value ? 'SUBSTRATE' : 'RECIRC'
      for (const [index, phase] of form.recipe_phases.entries()) {
        const phMin = Math.min(phase.ph_day, phase.ph_night)
        const phMax = Math.max(phase.ph_day, phase.ph_night)
        const ecMin = Math.min(phase.ec_day, phase.ec_night)
        const ecMax = Math.max(phase.ec_day, phase.ec_night)

        await api.post(`/recipe-revisions/${revisionId}/phases`, {
          phase_index: index,
          name: phase.name.trim() || `Фаза ${index + 1}`,
          duration_days: phase.duration_days,
          duration_hours: phase.duration_days * 24,
          ph_target: Number(((phase.ph_day + phase.ph_night) / 2).toFixed(2)),
          ph_min: Number(phMin.toFixed(2)),
          ph_max: Number(phMax.toFixed(2)),
          ec_target: Number(((phase.ec_day + phase.ec_night) / 2).toFixed(2)),
          ec_min: Number(ecMin.toFixed(2)),
          ec_max: Number(ecMax.toFixed(2)),
          temp_air_target: Number(phase.temp_day.toFixed(1)),
          humidity_target: Math.round(phase.humidity_day),
          lighting_photoperiod_hours: Math.round(phase.light_hours),
          lighting_start_time: phase.day_start_time,
          irrigation_mode: irrigationMode,
          irrigation_interval_sec: Math.round(phase.irrigation_interval_sec),
          irrigation_duration_sec: Math.round(phase.irrigation_duration_sec),
          extensions: {
            day_night: {
              ph: { day: phase.ph_day, night: phase.ph_night },
              ec: { day: phase.ec_day, night: phase.ec_night },
              temperature: { day: phase.temp_day, night: phase.temp_night },
              humidity: { day: phase.humidity_day, night: phase.humidity_night },
              lighting: { day_start_time: phase.day_start_time, day_hours: phase.light_hours },
            },
          },
        })
      }

      await api.post(`/recipe-revisions/${revisionId}/publish`)
      return true
    } catch (error: any) {
      logger.error('Failed to create recipe phases:', error)
      errors.general = error.response?.data?.message ?? 'Не удалось создать фазы рецепта'
      return false
    }
  }

  async function onSubmit() {
    if (currentStep.value === 1) {
      errors.growing_system = ''
      if (!form.name || !form.name.trim()) {
        showToast('Введите название растения', 'error', TOAST_TIMEOUT.NORMAL)
        return
      }
      if (!form.growing_system) {
        errors.growing_system = 'Выберите систему выращивания'
        showToast('Выберите систему выращивания', 'error', TOAST_TIMEOUT.NORMAL)
        return
      }

      if (!form.recipe_name.trim()) {
        form.recipe_name = `${form.name.trim()} — полный цикл`
      }

      currentStep.value = 2
      return
    }

    if (!form.recipe_name || !form.recipe_name.trim()) {
      showToast('Введите название рецепта', 'error', TOAST_TIMEOUT.NORMAL)
      return
    }

    if (!form.name || !form.name.trim()) {
      showToast('Введите название растения', 'error', TOAST_TIMEOUT.NORMAL)
      return
    }

    loading.value = true
    errors.name = ''
    errors.recipe_name = ''
    errors.growing_system = ''
    errors.general = ''

    try {
      const plantCreated = await createPlantIfNeeded()
      if (!plantCreated) {
        return
      }

      const revisionId = await createRecipeRevision()
      if (!revisionId) {
        return
      }

      const phasesCreated = await createRecipePhases(revisionId)
      if (!phasesCreated) {
        return
      }

      showToast('Растение и рецепт успешно созданы', 'success', TOAST_TIMEOUT.NORMAL)
      onCreated(createdPlantData.value)
      handleClose()
      router.reload({ only: ['plants'] })
    } catch (error: any) {
      logger.error('Failed to create plant:', error)

      if (error.response?.data?.errors) {
        Object.keys(error.response.data.errors).forEach((key) => {
          errors[key] = error.response.data.errors[key][0]
        })
      } else if (error.response?.data?.message) {
        errors.general = error.response.data.message
      }
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    errors,
    currentStep,
    createdPlantId,
    taxonomyOptions,
    seasonOptions,
    taxonomyWizard,
    taxonomyWizardItems,
    form,
    showSubstrateSelector,
    addRecipePhase,
    removeRecipePhase,
    openTaxonomyWizard,
    closeTaxonomyWizard,
    handleTaxonomySaved,
    handleClose,
    stepTitle,
    primaryLabel,
    isPrimaryDisabled,
    goBack,
    onSubmit,
  }
}
