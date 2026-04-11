import { computed, reactive, ref, watch, type Ref } from 'vue'
import { router } from '@inertiajs/vue3'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { logger } from '@/utils/logger'
import { useRecipeEditor } from '@/composables/useRecipeEditor'
import { buildRecipePhasePayload } from '@/composables/recipeEditorShared'

export interface TaxonomyOption {
  id: string
  label: string
  uses_substrate?: boolean
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

export function usePlantCreateModal(options: UsePlantCreateModalOptions) {
  const { show, taxonomies, onClose, onCreated } = options
  const { showToast } = useToast()
  const recipeEditor = useRecipeEditor()

  const loading = ref(false)
  const errors = reactive<Record<string, string>>({})
  const currentStep = ref(1)
  const localTaxonomies = ref<Record<string, TaxonomyOption[]>>({})

  const taxonomyWizard = reactive<{ open: boolean; key: TaxonomyKey; title: string }>({
    open: false,
    key: 'substrate_type',
    title: '',
  })

  const form = reactive({
    name: '',
    species: '',
    variety: '',
    substrate_type: '',
    growing_system: '',
    photoperiod_preset: '',
    seasonality: '',
    description: '',
  })

  const taxonomyOptions = computed(() => ({
    substrate_type: localTaxonomies.value.substrate_type ?? [],
    growing_system: localTaxonomies.value.growing_system ?? [],
    photoperiod_preset: localTaxonomies.value.photoperiod_preset ?? [],
  }))

  const seasonOptions = computed(() => localTaxonomies.value.seasonality ?? defaultSeasonality)
  const taxonomyWizardItems = computed(() => localTaxonomies.value[taxonomyWizard.key] ?? [])

  const showSubstrateSelector = computed(() => {
    if (!form.growing_system) {
      return false
    }

    const selectedSystem = taxonomyOptions.value.growing_system.find((option) => option.id === form.growing_system)
    if (typeof selectedSystem?.uses_substrate === 'boolean') {
      return selectedSystem.uses_substrate
    }

    return false
  })

  const stepTitle = computed(() => (currentStep.value === 1 ? 'Данные растения' : 'Рецепт выращивания'))
  const primaryLabel = computed(() => (currentStep.value === 1 ? 'Далее' : 'Создать культуру и рецепт'))
  const isPrimaryDisabled = computed(() => {
    if (currentStep.value === 1) {
      return !form.name.trim() || !form.growing_system
    }

    return loading.value || !recipeEditor.form.name.trim() || recipeEditor.form.phases.length === 0
  })

  function resetForm(): void {
    form.name = ''
    form.species = ''
    form.variety = ''
    form.substrate_type = ''
    form.growing_system = ''
    form.photoperiod_preset = ''
    form.seasonality = ''
    form.description = ''
    currentStep.value = 1
    Object.keys(errors).forEach((key) => delete errors[key])
    recipeEditor.reset(null)
  }

  watch(
    show,
    (newValue) => {
      if (!newValue) {
        return
      }

      resetForm()
      void loadTaxonomiesFromApi()
      void recipeEditor.loadNutrientProducts()
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
      const payload = await api.plantTaxonomies.list()
      if (!payload || typeof payload !== 'object') {
        return
      }

      localTaxonomies.value = {
        ...localTaxonomies.value,
        substrate_type: (payload.substrate_type as TaxonomyOption[]) ?? localTaxonomies.value.substrate_type ?? [],
        growing_system: (payload.growing_system as TaxonomyOption[]) ?? localTaxonomies.value.growing_system ?? [],
        photoperiod_preset: (payload.photoperiod_preset as TaxonomyOption[]) ?? localTaxonomies.value.photoperiod_preset ?? [],
        seasonality: (payload.seasonality as TaxonomyOption[]) ?? localTaxonomies.value.seasonality ?? defaultSeasonality,
      }
    } catch (error) {
      logger.error('Failed to load plant taxonomies', { error })
    }
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

  function handleClose(): void {
    resetForm()
    onClose()
  }

  function goBack(): void {
    currentStep.value = 1
    errors.general = ''
    errors.growing_system = ''
  }

  async function onSubmit(): Promise<void> {
    if (currentStep.value === 1) {
      errors.growing_system = ''
      if (!form.name.trim()) {
        showToast('Введите название растения', 'error', TOAST_TIMEOUT.NORMAL)
        return
      }
      if (!form.growing_system) {
        errors.growing_system = 'Выберите систему выращивания'
        showToast('Выберите систему выращивания', 'error', TOAST_TIMEOUT.NORMAL)
        return
      }

      if (!recipeEditor.form.name.trim()) {
        recipeEditor.form.name = `${form.name.trim()} — полный цикл`
      }
      currentStep.value = 2
      return
    }

    loading.value = true
    errors.general = ''
    try {
      const payload = await api.plants.createWithRecipe({
        plant: {
          name: form.name.trim(),
          species: form.species.trim() || null,
          variety: form.variety.trim() || null,
          substrate_type: form.substrate_type || null,
          growing_system: form.growing_system || null,
          photoperiod_preset: form.photoperiod_preset || null,
          seasonality: form.seasonality || null,
          description: form.description.trim() || null,
        },
        recipe: {
          name: recipeEditor.form.name.trim(),
          description: recipeEditor.form.description.trim() || null,
          revision_description: 'Initial revision from plant wizard',
          phases: recipeEditor.form.phases.map((phase) => buildRecipePhasePayload(phase)),
        },
      })

      const plant = payload?.plant ?? null
      onCreated(plant)
      showToast('Растение и рецепт успешно созданы', 'success', TOAST_TIMEOUT.NORMAL)
      handleClose()
      router.reload({ only: ['plants'] })
    } catch (error: any) {
      logger.error('Failed to create plant with recipe', { error })
      if (error.response?.data?.errors) {
        Object.keys(error.response.data.errors).forEach((key) => {
          errors[key] = error.response.data.errors[key][0]
        })
      } else if (error.response?.data?.message) {
        errors.general = error.response.data.message
      } else {
        errors.general = 'Не удалось создать растение и рецепт'
      }
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    errors,
    currentStep,
    taxonomyOptions,
    seasonOptions,
    taxonomyWizard,
    taxonomyWizardItems,
    form,
    recipeForm: recipeEditor.form,
    npkProducts: recipeEditor.npkProducts,
    calciumProducts: recipeEditor.calciumProducts,
    magnesiumProducts: recipeEditor.magnesiumProducts,
    microProducts: recipeEditor.microProducts,
    showSubstrateSelector,
    addRecipePhase: recipeEditor.addPhase,
    removeRecipePhase: recipeEditor.removePhase,
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
