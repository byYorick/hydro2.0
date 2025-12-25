<template>
  <Modal :open="show" :title="wizardTitle" @close="handleClose" size="large">
    <ErrorBoundary>
      <!-- Прогресс-бар шагов -->
      <div class="mb-6">
        <div class="flex items-center justify-between">
          <div
            v-for="(step, index) in steps"
            :key="index"
            class="flex items-center flex-1"
          >
            <div class="flex items-center">
              <div
                :class="[
                  'w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-all',
                  currentStep > index
                    ? 'bg-[color:var(--accent-green)] text-white'
                    : currentStep === index
                    ? 'bg-[color:var(--accent-cyan)] text-white ring-2 ring-[color:var(--accent-cyan)] ring-offset-2'
                    : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'
                ]"
              >
                <span v-if="currentStep > index">✓</span>
                <span v-else>{{ index + 1 }}</span>
              </div>
              <span
                :class="[
                  'ml-3 text-sm font-medium',
                  currentStep >= index ? 'text-[color:var(--text-primary)]' : 'text-[color:var(--text-muted)]'
                ]"
              >
                {{ step.title }}
              </span>
            </div>
            <div
              v-if="index < steps.length - 1"
              :class="[
                'flex-1 h-0.5 mx-4 transition-colors',
                currentStep > index ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--border-muted)]'
              ]"
            />
          </div>
        </div>
      </div>

      <!-- Шаг 1: Выбор зоны (если не передана) -->
      <div v-if="currentStep === 0" class="space-y-4">
        <div v-if="zoneId">
          <div class="p-4 rounded-lg bg-[color:var(--badge-success-bg)] border border-[color:var(--badge-success-border)]">
            <div class="text-sm font-medium text-[color:var(--badge-success-text)]">
              Зона выбрана: {{ zoneName || `Зона #${zoneId}` }}
            </div>
          </div>
        </div>
        <div v-else>
          <label class="block text-sm font-medium mb-2">Выберите зону</label>
          <select
            v-model="form.zoneId"
            class="input-select w-full"
            @change="onZoneSelected"
          >
            <option :value="null">Выберите зону</option>
            <option
              v-for="zone in availableZones"
              :key="zone.id"
              :value="zone.id"
            >
              {{ zone.name }} ({{ zone.greenhouse?.name || '' }})
            </option>
          </select>
        </div>
        <div class="text-xs text-[color:var(--text-muted)]">
          💡 Подсказка: Убедитесь, что зона имеет привязанный рецепт и устройства
        </div>
      </div>

      <!-- Шаг 2: Выбор рецепта -->
      <div v-if="currentStep === 1" class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-2">Выберите рецепт</label>
          <div class="flex gap-2 mb-3">
            <Button
              size="sm"
              :variant="recipeMode === 'select' ? 'primary' : 'secondary'"
              @click="recipeMode = 'select'"
            >
              Выбрать существующий
            </Button>
            <Button
              size="sm"
              :variant="recipeMode === 'create' ? 'primary' : 'secondary'"
              @click="recipeMode = 'create'"
            >
              Создать новый
            </Button>
          </div>

          <div v-if="recipeMode === 'select'">
            <select
              v-model="form.recipeId"
              class="input-select w-full"
              @change="onRecipeSelected"
            >
              <option :value="null">Выберите рецепт</option>
              <option
                v-for="recipe in availableRecipes"
                :key="recipe.id"
                :value="recipe.id"
              >
                {{ recipe.name }} ({{ recipe.phases?.length || 0 }} фаз)
              </option>
            </select>
          </div>

          <div v-else>
            <RecipeCreateWizard
              :show="recipeMode === 'create'"
              @close="recipeMode = 'select'"
              @created="onRecipeCreated"
            />
          </div>
        </div>

        <!-- Визуализация выбранного рецепта -->
        <div v-if="selectedRecipe" class="mt-4 p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
          <div class="text-sm font-semibold mb-2">{{ selectedRecipe.name }}</div>
          <div v-if="selectedRecipe.description" class="text-xs text-[color:var(--text-muted)] mb-3">
            {{ selectedRecipe.description }}
          </div>
          <div class="text-xs font-medium mb-2">Фазы рецепта:</div>
          <div class="space-y-2">
            <div
              v-for="(phase, index) in selectedRecipe.phases"
              :key="index"
              class="flex items-center justify-between p-2 rounded bg-[color:var(--bg-surface-strong)]"
            >
              <div>
                <div class="text-xs font-medium">{{ phase.name || `Фаза ${index + 1}` }}</div>
                <div class="text-xs text-[color:var(--text-dim)]">
                  {{ Math.round(phase.duration_hours / 24) }} дней
                </div>
              </div>
              <div class="text-xs text-[color:var(--text-muted)]">
                pH: {{ phase.targets?.ph?.min || '-' }}–{{ phase.targets?.ph?.max || '-' }}
                EC: {{ phase.targets?.ec?.min || '-' }}–{{ phase.targets?.ec?.max || '-' }}
              </div>
            </div>
          </div>
        </div>

        <div class="text-xs text-[color:var(--text-muted)]">
          💡 Подсказка: Рецепт определяет фазы роста и целевые параметры для каждой фазы
        </div>
      </div>

      <!-- Шаг 3: Параметры цикла -->
      <div v-if="currentStep === 2" class="space-y-4">
        <div>
          <h3 class="text-sm font-semibold mb-3">Параметры запуска цикла</h3>
          
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium mb-2">Дата начала</label>
              <input
                v-model="form.startedAt"
                type="datetime-local"
                class="input-field w-full"
                :min="minStartDate"
                required
              />
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                Цикл начнется с первой фазы выбранного рецепта
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium mb-2">Ожидаемая дата сбора (опционально)</label>
              <input
                v-model="form.expectedHarvestAt"
                type="date"
                class="input-field w-full"
                :min="form.startedAt"
              />
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                Используется для планирования и аналитики
              </div>
            </div>

            <!-- Предпросмотр длительности -->
            <div v-if="selectedRecipe" class="p-3 rounded-lg bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]">
              <div class="text-xs font-medium mb-1">Предполагаемая длительность цикла:</div>
              <div class="text-sm">
                {{ Math.round(totalDurationDays) }} дней
                <span class="text-xs text-[color:var(--text-muted)]">
                  ({{ selectedRecipe.phases?.length || 0 }} фаз)
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Шаг 4: Предпросмотр и подтверждение -->
      <div v-if="currentStep === 3" class="space-y-4">
        <div>
          <h3 class="text-sm font-semibold mb-3">Предпросмотр цикла выращивания</h3>
          
          <div class="space-y-3">
            <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Зона</div>
              <div class="text-sm font-medium">{{ zoneName || `Зона #${form.zoneId}` }}</div>
            </div>

            <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Рецепт</div>
              <div class="text-sm font-medium">{{ selectedRecipe?.name || 'Не выбран' }}</div>
            </div>

            <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Дата начала</div>
              <div class="text-sm font-medium">{{ formatDateTime(form.startedAt) }}</div>
            </div>

            <div v-if="form.expectedHarvestAt" class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Ожидаемая дата сбора</div>
              <div class="text-sm font-medium">{{ formatDate(form.expectedHarvestAt) }}</div>
            </div>

            <!-- Timeline фаз -->
            <div v-if="selectedRecipe" class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
              <div class="text-xs text-[color:var(--text-dim)] mb-2">План фаз:</div>
              <div class="space-y-2">
                <div
                  v-for="(phase, index) in selectedRecipe.phases"
                  :key="index"
                  class="flex items-center justify-between text-xs"
                >
                  <span class="font-medium">{{ phase.name || `Фаза ${index + 1}` }}</span>
                  <span class="text-[color:var(--text-muted)]">
                    {{ Math.round(phase.duration_hours / 24) }} дней
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="validationErrors.length > 0" class="p-3 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]">
          <div class="text-sm font-medium text-[color:var(--badge-danger-text)] mb-1">
            Ошибки валидации:
          </div>
          <ul class="text-xs text-[color:var(--badge-danger-text)] list-disc list-inside">
            <li v-for="error in validationErrors" :key="error">{{ error }}</li>
          </ul>
        </div>
      </div>

      <!-- Общие ошибки -->
      <div v-if="error" class="mt-4 p-3 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]">
        <div class="text-sm text-[color:var(--badge-danger-text)]">{{ error }}</div>
      </div>
    </ErrorBoundary>

    <template #footer>
      <div class="flex items-center justify-between w-full">
        <Button
          v-if="currentStep > 0"
          variant="secondary"
          @click="prevStep"
          :disabled="loading"
        >
          Назад
        </Button>
        <div v-else></div>
        
        <div class="flex gap-2">
          <Button
            variant="secondary"
            @click="handleClose"
            :disabled="loading"
          >
            Отмена
          </Button>
          <Button
            v-if="currentStep < steps.length - 1"
            @click="nextStep"
            :disabled="!canProceed || loading"
          >
            Далее
          </Button>
          <Button
            v-else
            @click="onSubmit"
            :disabled="!canSubmit || loading"
          >
            {{ loading ? 'Создание...' : 'Запустить цикл' }}
          </Button>
        </div>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useZones } from '@/composables/useZones'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import ErrorBoundary from '@/Components/ErrorBoundary.vue'
import RecipeCreateWizard from '@/Components/RecipeCreateWizard.vue'
import { logger } from '@/utils/logger'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

interface Props {
  show: boolean
  zoneId?: number
  zoneName?: string
  currentPhaseTargets?: any
  activeCycle?: any
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  zoneId: undefined,
  zoneName: '',
})

const emit = defineEmits<{
  close: []
  submit: [data: {
    zoneId: number
    recipeId: number
    startedAt: string
    expectedHarvestAt?: string
  }]
}>()

const { api } = useApi()
const { showToast } = useToast()
const { fetchZones } = useZones()

const currentStep = ref(0)
const recipeMode = ref<'select' | 'create'>('select')
const loading = ref(false)
const error = ref<string | null>(null)
const validationErrors = ref<string[]>([])

const form = ref({
  zoneId: props.zoneId || null,
  recipeId: null as number | null,
  startedAt: new Date().toISOString().slice(0, 16),
  expectedHarvestAt: '',
})

const availableZones = ref<any[]>([])
const availableRecipes = ref<any[]>([])
const selectedRecipe = ref<any | null>(null)

const steps = [
  { title: 'Зона', key: 'zone' },
  { title: 'Рецепт', key: 'recipe' },
  { title: 'Параметры', key: 'params' },
  { title: 'Подтверждение', key: 'confirm' },
]

const wizardTitle = computed(() => {
  return props.activeCycle 
    ? 'Корректировка цикла выращивания'
    : 'Запуск нового цикла выращивания'
})

const minStartDate = computed(() => {
  return new Date().toISOString().slice(0, 16)
})

const totalDurationDays = computed(() => {
  if (!selectedRecipe.value?.phases) return 0
  const totalHours = selectedRecipe.value.phases.reduce(
    (sum: number, phase: any) => sum + (phase.duration_hours || 0),
    0
  )
  return totalHours / 24
})

const canProceed = computed(() => {
  switch (currentStep.value) {
    case 0:
      return form.value.zoneId !== null
    case 1:
      return form.value.recipeId !== null && selectedRecipe.value !== null
    case 2:
      return form.value.startedAt !== ''
    default:
      return true
  }
})

const canSubmit = computed(() => {
  return canProceed.value && validationErrors.value.length === 0
})

function formatDateTime(dateString: string): string {
  if (!dateString) return ''
  try {
    const date = new Date(dateString)
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateString
  }
}

function formatDate(dateString: string): string {
  if (!dateString) return ''
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('ru-RU')
  } catch {
    return dateString
  }
}

async function loadZones(): Promise<void> {
  try {
    const zones = await fetchZones(true)
    availableZones.value = zones
  } catch (err) {
    logger.error('[GrowthCycleWizard] Failed to load zones', err)
  }
}

async function loadRecipes(): Promise<void> {
  try {
    const response = await api.get<{ data?: any[] } | any[]>('/api/recipes')
    const recipes = Array.isArray(response.data) 
      ? response.data 
      : (response.data as any)?.data || []
    availableRecipes.value = recipes
  } catch (err) {
    logger.error('[GrowthCycleWizard] Failed to load recipes', err)
    showToast('Не удалось загрузить список рецептов', 'error', TOAST_TIMEOUT.NORMAL)
  }
}

async function loadRecipeDetails(recipeId: number): Promise<void> {
  try {
    const response = await api.get(`/api/recipes/${recipeId}`)
    const recipe = (response.data as any)?.data || response.data
    selectedRecipe.value = recipe
  } catch (err) {
    logger.error('[GrowthCycleWizard] Failed to load recipe details', { recipeId, err })
    showToast('Не удалось загрузить детали рецепта', 'error', TOAST_TIMEOUT.NORMAL)
  }
}

function onZoneSelected(): void {
  // Можно добавить дополнительную логику при выборе зоны
}

function onRecipeSelected(): void {
  if (form.value.recipeId) {
    loadRecipeDetails(form.value.recipeId)
  } else {
    selectedRecipe.value = null
  }
}

function onRecipeCreated(recipe: any): void {
  form.value.recipeId = recipe.id
  selectedRecipe.value = recipe
  recipeMode.value = 'select'
  loadRecipes() // Обновляем список рецептов
}

function validateStep(step: number): boolean {
  validationErrors.value = []

  switch (step) {
    case 0:
      if (!form.value.zoneId) {
        validationErrors.value.push('Необходимо выбрать зону')
        return false
      }
      break
    case 1:
      if (!form.value.recipeId) {
        validationErrors.value.push('Необходимо выбрать рецепт')
        return false
      }
      if (!selectedRecipe.value) {
        validationErrors.value.push('Рецепт не загружен')
        return false
      }
      if (!selectedRecipe.value.phases || selectedRecipe.value.phases.length === 0) {
        validationErrors.value.push('Рецепт должен содержать хотя бы одну фазу')
        return false
      }
      break
    case 2:
      if (!form.value.startedAt) {
        validationErrors.value.push('Необходимо указать дату начала')
        return false
      }
      const startDate = new Date(form.value.startedAt)
      if (startDate < new Date()) {
        validationErrors.value.push('Дата начала не может быть в прошлом')
        return false
      }
      if (form.value.expectedHarvestAt) {
        const harvestDate = new Date(form.value.expectedHarvestAt)
        if (harvestDate <= startDate) {
          validationErrors.value.push('Дата сбора должна быть позже даты начала')
          return false
        }
      }
      break
  }

  return validationErrors.value.length === 0
}

function nextStep(): void {
  if (!validateStep(currentStep.value)) {
    return
  }

  if (currentStep.value < steps.length - 1) {
    currentStep.value++
    saveDraft()
  }
}

function prevStep(): void {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

function saveDraft(): void {
  try {
    const draft = {
      zoneId: form.value.zoneId,
      recipeId: form.value.recipeId,
      startedAt: form.value.startedAt,
      expectedHarvestAt: form.value.expectedHarvestAt,
      currentStep: currentStep.value,
    }
    localStorage.setItem('growthCycleWizardDraft', JSON.stringify(draft))
  } catch (err) {
    logger.warn('[GrowthCycleWizard] Failed to save draft', err)
  }
}

function loadDraft(): void {
  try {
    const draftStr = localStorage.getItem('growthCycleWizardDraft')
    if (draftStr) {
      const draft = JSON.parse(draftStr)
      if (draft.zoneId) form.value.zoneId = draft.zoneId
      if (draft.recipeId) {
        form.value.recipeId = draft.recipeId
        loadRecipeDetails(draft.recipeId)
      }
      if (draft.startedAt) form.value.startedAt = draft.startedAt
      if (draft.expectedHarvestAt) form.value.expectedHarvestAt = draft.expectedHarvestAt
      if (draft.currentStep !== undefined) currentStep.value = draft.currentStep
    }
  } catch (err) {
    logger.warn('[GrowthCycleWizard] Failed to load draft', err)
  }
}

function clearDraft(): void {
  try {
    localStorage.removeItem('growthCycleWizardDraft')
  } catch (err) {
    logger.warn('[GrowthCycleWizard] Failed to clear draft', err)
  }
}

async function onSubmit(): Promise<void> {
  if (!validateStep(currentStep.value)) {
    return
  }

  if (!form.value.zoneId || !form.value.recipeId || !form.value.startedAt) {
    error.value = 'Заполните все обязательные поля'
    return
  }

  loading.value = true
  error.value = null

  try {
    // Формируем данные для API
    const plantingAt = form.value.startedAt ? new Date(form.value.startedAt).toISOString() : undefined
    
    const response = await api.post(`/api/zones/${form.value.zoneId}/grow-cycles`, {
      recipe_id: form.value.recipeId,
      planting_at: plantingAt,
      start_immediately: true, // Запускаем цикл сразу после создания
      settings: {
        expected_harvest_at: form.value.expectedHarvestAt || undefined,
      },
    })

    if (response.data?.status === 'ok') {
      clearDraft()
      showToast('Цикл выращивания успешно запущен', 'success', TOAST_TIMEOUT.NORMAL)
      emit('close')
      
      // Эмитим событие для обновления данных на странице
      emit('submit', {
        zoneId: form.value.zoneId,
        recipeId: form.value.recipeId,
        startedAt: form.value.startedAt,
        expectedHarvestAt: form.value.expectedHarvestAt || undefined,
      })
    } else {
      throw new Error(response.data?.message || 'Не удалось создать цикл')
    }
  } catch (err: any) {
    const errorMessage = err?.response?.data?.message || err?.message || 'Ошибка при создании цикла'
    error.value = errorMessage
    logger.error('[GrowthCycleWizard] Failed to submit', err)
    showToast(errorMessage, 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    loading.value = false
  }
}

function handleClose(): void {
  if (!loading.value) {
    emit('close')
  }
}

function reset(): void {
  currentStep.value = 0
  recipeMode.value = 'select'
  error.value = null
  validationErrors.value = []
  form.value = {
    zoneId: props.zoneId || null,
    recipeId: null,
    startedAt: new Date().toISOString().slice(0, 16),
    expectedHarvestAt: '',
  }
  selectedRecipe.value = null
}

watch(() => props.show, (show) => {
  if (show) {
    reset()
    if (!props.zoneId) {
      loadZones()
    }
    loadRecipes()
    loadDraft()
  } else {
    clearDraft()
  }
})

watch(() => props.zoneId, (newZoneId) => {
  if (newZoneId) {
    form.value.zoneId = newZoneId
  }
})

onMounted(() => {
  if (props.show) {
    if (!props.zoneId) {
      loadZones()
    }
    loadRecipes()
    loadDraft()
  }
})

onUnmounted(() => {
  // Сохраняем черновик при закрытии
  if (props.show) {
    saveDraft()
  }
})
</script>

