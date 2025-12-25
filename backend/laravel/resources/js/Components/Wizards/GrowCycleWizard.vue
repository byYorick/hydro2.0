<template>
  <Modal :open="show" :title="'Создание цикла выращивания'" @close="handleClose" size="large">
    <WizardBase
      :wizardState="wizardState"
      submitLabel="Запустить цикл"
      :submitting="loading"
      @next="handleNext"
      @prev="handlePrev"
      @submit="handleSubmit"
    >
      <template #default="{ step, stepIndex }">
        <!-- Шаг 1: Выбор/создание теплицы -->
        <div v-if="stepIndex === 0" class="space-y-4">
          <p class="text-sm text-[color:var(--text-muted)]">
            TODO: Компонент WizardStepGreenhouse будет создан позже
          </p>
          <p class="text-sm text-[color:var(--text-muted)]">
            Greenhouse ID: {{ wizardState.formData.greenhouseId || 'не выбран' }}
          </p>
        </div>

        <!-- Шаг 2: Выбор/создание зоны -->
        <div v-if="stepIndex === 1" class="space-y-4">
          <p class="text-sm text-[color:var(--text-muted)]">
            TODO: Компонент WizardStepZone будет создан позже
          </p>
          <p class="text-sm text-[color:var(--text-muted)]">
            Zone ID: {{ wizardState.formData.zoneId || 'не выбрана' }}
          </p>
        </div>

        <!-- Шаг 3: Выбор/создание растения -->
        <div v-if="stepIndex === 2" class="space-y-4">
          <p class="text-sm text-[color:var(--text-muted)]">
            TODO: Компонент WizardStepPlant будет создан позже
          </p>
          <p class="text-sm text-[color:var(--text-muted)]">
            Plant ID: {{ wizardState.formData.plantId || 'не выбрано' }}
          </p>
        </div>

        <!-- Шаг 4: Выбор/создание рецепта -->
        <div v-if="stepIndex === 3" class="space-y-4">
          <p class="text-sm text-[color:var(--text-muted)]">
            TODO: Компонент WizardStepRecipe будет создан позже
          </p>
          <p class="text-sm text-[color:var(--text-muted)]">
            Recipe ID: {{ wizardState.formData.recipeId || 'не выбран' }}
          </p>
        </div>

        <!-- Шаг 5: Параметры запуска -->
        <div v-if="stepIndex === 4" class="space-y-4">
          <p class="text-sm text-[color:var(--text-muted)]">
            TODO: Компонент WizardStepStart будет создан позже
          </p>
          <div class="space-y-2">
            <label class="block text-sm font-medium">Дата посадки</label>
            <input
              v-model="wizardState.formData.plantingAt"
              type="datetime-local"
              class="input-field w-full"
            />
          </div>
        </div>
      </template>
    </WizardBase>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import WizardBase from './WizardBase.vue'
import { useWizardState, type WizardStep } from '@/composables/useWizardState'
import { useWizardValidation, type GrowCycleWizardData } from '@/composables/useWizardValidation'
import { useWizardApi } from '@/composables/useWizardApi'
import { useToast } from '@/composables/useToast'

// TODO: Создать компоненты шагов
// import WizardStepGreenhouse from './Steps/WizardStepGreenhouse.vue'
// import WizardStepZone from './Steps/WizardStepZone.vue'
// import WizardStepPlant from './Steps/WizardStepPlant.vue'
// import WizardStepRecipe from './Steps/WizardStepRecipe.vue'
// import WizardStepStart from './Steps/WizardStepStart.vue'

interface Props {
  show: boolean
  zoneId?: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  created: [cycle: any]
}>()

const { showToast } = useToast()
const { createCycleFromWizard } = useWizardApi()
const loading = ref(false)

// Определяем шаги визарда
const steps: WizardStep[] = [
  {
    id: 'greenhouse',
    title: 'Теплица',
    description: 'Выберите существующую теплицу или создайте новую',
  },
  {
    id: 'zone',
    title: 'Зона',
    description: 'Выберите зону в теплице или создайте новую',
  },
  {
    id: 'plant',
    title: 'Растение',
    description: 'Выберите растение или создайте новое',
  },
  {
    id: 'recipe',
    title: 'Рецепт',
    description: 'Выберите рецепт выращивания или создайте новый',
  },
  {
    id: 'start',
    title: 'Запуск',
    description: 'Укажите параметры запуска цикла',
  },
]

// Инициализируем состояние визарда
const initialData: GrowCycleWizardData = {
  zoneId: props.zoneId,
}

const wizardState = useWizardState<GrowCycleWizardData>(
  steps,
  initialData,
  async (data) => {
    await handleSubmit()
  }
)

// Валидация визарда
const { validateStep } = useWizardValidation(wizardState)

// Вычисляемые свойства
const selectedRecipe = computed(() => {
  // TODO: Получить рецепт по ID из API или из formData
  return null
})

// Обработчики событий
const handleNext = async () => {
  const isValid = await validateStep(wizardState.currentStep.value)
  if (!isValid) {
    showToast('Пожалуйста, заполните все обязательные поля', 'error')
  }
}

const handlePrev = () => {
  // Навигация обрабатывается автоматически через WizardBase
}

const handleSubmit = async () => {
  loading.value = true
  try {
    const cycle = await createCycleFromWizard(wizardState.formData.value)
    showToast('Цикл успешно создан', 'success')
    emit('created', cycle)
    handleClose()
  } catch (error: any) {
    showToast(error.message || 'Ошибка при создании цикла', 'error')
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  wizardState.reset()
  emit('close')
}

const onGreenhouseSelected = (greenhouse: any) => {
  wizardState.formData.value.greenhouseId = greenhouse.id
  wizardState.formData.value.greenhouse = greenhouse
}

const onZoneSelected = (zone: any) => {
  wizardState.formData.value.zoneId = zone.id
  wizardState.formData.value.zone = zone
}

const onPlantSelected = (plant: any) => {
  wizardState.formData.value.plantId = plant.id
  wizardState.formData.value.plant = plant
}

const onRecipeSelected = (recipe: any) => {
  wizardState.formData.value.recipeId = recipe.id
  wizardState.formData.value.recipe = recipe
}

// Валидация шагов при изменении данных
watch(
  () => wizardState.currentStep.value,
  async (newStep) => {
    // Автоматическая валидация при переходе на шаг
    await validateStep(newStep)
  }
)
</script>

