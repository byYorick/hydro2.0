<template>
  <Modal
    :open="show"
    title="Создать новый рецепт"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-6">
      <!-- Шаг 1: Основная информация -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">
          Основная информация
        </h3>
        <div class="space-y-3">
          <div>
            <label
              for="recipe-name"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Название рецепта</label>
            <input
              id="recipe-name"
              v-model="form.name"
              name="name"
              type="text"
              placeholder="Например: Рецепт для салата"
              class="input-field h-9 w-full"
              autocomplete="off"
              required
            />
          </div>
          <div>
            <label
              for="recipe-description"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Описание (опционально)</label>
            <textarea
              id="recipe-description"
              v-model="form.description"
              name="description"
              placeholder="Описание рецепта..."
              class="input-field w-full min-h-[60px] py-2 h-auto"
              autocomplete="off"
            ></textarea>
          </div>
          <div>
            <label
              for="recipe-plant"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Культура</label>
            <select
              id="recipe-plant"
              v-model.number="form.plant_id"
              name="plant_id"
              class="input-field h-9 w-full"
              :disabled="plantsLoading"
            >
              <option
                :value="null"
                disabled
              >
                Выберите культуру
              </option>
              <option
                v-for="plant in plants"
                :key="plant.id"
                :value="plant.id"
              >
                {{ plant.name }}
              </option>
            </select>
            <div
              v-if="!plantsLoading && plants.length === 0"
              class="text-xs text-[color:var(--text-dim)] mt-1"
            >
              Нет доступных культур — добавьте культуру в справочнике.
            </div>
          </div>
        </div>
      </div>

      <!-- Шаг 2: Фазы рецепта -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Фазы рецепта
          </h3>
          <Button
            size="sm"
            variant="secondary"
            @click="addPhase"
          >
            + Добавить фазу
          </Button>
        </div>
        <div class="space-y-3 max-h-[400px] overflow-y-auto">
          <div
            v-for="(phase, index) in form.phases"
            :key="index"
            class="p-3 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] space-y-2"
          >
            <div class="flex items-center justify-between">
              <div class="text-xs font-semibold text-[color:var(--text-primary)]">
                Фаза {{ index + 1 }}
              </div>
              <Button
                v-if="form.phases.length > 1"
                size="sm"
                variant="danger"
                @click="removePhase(index)"
              >
                Удалить
              </Button>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label
                  :for="`phase-name-${index}`"
                  class="block text-xs text-[color:var(--text-muted)] mb-1"
                >Название</label>
                <input
                  :id="`phase-name-${index}`"
                  v-model="phase.name"
                  type="text"
                  placeholder="Например: Проращивание"
                  class="input-field h-8 w-full text-xs"
                  autocomplete="off"
                />
              </div>
              <div>
                <label
                  :for="`phase-duration-${index}`"
                  class="block text-xs text-[color:var(--text-muted)] mb-1"
                >Длительность (часов)</label>
                <input
                  :id="`phase-duration-${index}`"
                  v-model.number="phase.duration_hours"
                  type="number"
                  min="1"
                  class="input-field h-8 w-full text-xs"
                  autocomplete="off"
                />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 mt-2">
              <div>
                <label
                  :for="`phase-ph-min-${index}`"
                  class="block text-xs text-[color:var(--text-muted)] mb-1"
                >pH мин</label>
                <input
                  :id="`phase-ph-min-${index}`"
                  v-model.number="phase.targets.ph.min"
                  type="number"
                  step="0.1"
                  min="0"
                  max="14"
                  class="input-field h-8 w-full text-xs"
                  autocomplete="off"
                />
              </div>
              <div>
                <label
                  :for="`phase-ph-max-${index}`"
                  class="block text-xs text-[color:var(--text-muted)] mb-1"
                >pH макс</label>
                <input
                  :id="`phase-ph-max-${index}`"
                  v-model.number="phase.targets.ph.max"
                  type="number"
                  step="0.1"
                  min="0"
                  max="14"
                  class="input-field h-8 w-full text-xs"
                  autocomplete="off"
                />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label
                  :for="`phase-ec-min-${index}`"
                  class="block text-xs text-[color:var(--text-muted)] mb-1"
                >EC мин</label>
                <input
                  :id="`phase-ec-min-${index}`"
                  v-model.number="phase.targets.ec.min"
                  type="number"
                  step="0.1"
                  min="0"
                  class="input-field h-8 w-full text-xs"
                  autocomplete="off"
                />
              </div>
              <div>
                <label
                  :for="`phase-ec-max-${index}`"
                  class="block text-xs text-[color:var(--text-muted)] mb-1"
                >EC макс</label>
                <input
                  :id="`phase-ec-max-${index}`"
                  v-model.number="phase.targets.ec.max"
                  type="number"
                  step="0.1"
                  min="0"
                  class="input-field h-8 w-full text-xs"
                  autocomplete="off"
                />
              </div>
            </div>
          </div>
        </div>
        <div
          v-if="form.phases.length === 0"
          class="text-xs text-[color:var(--text-dim)] text-center py-4"
        >
          Нет фаз. Добавьте хотя бы одну фазу.
        </div>
      </div>

      <!-- Сообщение об успехе -->
      <div
        v-if="createdRecipe"
        class="p-3 rounded-md bg-[color:var(--badge-success-bg)] border border-[color:var(--badge-success-border)]"
      >
        <div class="text-sm text-[color:var(--badge-success-text)]">
          ✓ Рецепт "{{ createdRecipe.name }}" успешно создан!
        </div>
      </div>

      <!-- Ошибка -->
      <div
        v-if="error"
        class="p-3 rounded-md bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
      >
        <div class="text-sm text-[color:var(--badge-danger-text)]">
          {{ error }}
        </div>
      </div>
    </div>

    <template #footer>
      <Button
        size="sm"
        variant="secondary"
        @click="$emit('close')"
      >
        Отмена
      </Button>
      <Button
        size="sm"
        :disabled="!form.name || !form.plant_id || form.phases.length === 0 || creating"
        @click="onCreate"
      >
        {{ creating ? 'Создание...' : 'Создать рецепт' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive, watch } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { router } from '@inertiajs/vue3'

interface Props {
  show: boolean
}

interface Recipe {
  id: number
  name: string
  description?: string
}

interface Phase {
  phase_index: number
  name: string
  duration_hours: number
  targets: {
    ph: { min: number; max: number }
    ec: { min: number; max: number }
  }
}

interface PlantOption {
  id: number
  name: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  created: [recipe: Recipe]
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const form = reactive({
  name: '',
  description: '',
  plant_id: null as number | null,
  phases: [
    {
      phase_index: 0,
      name: '',
      duration_hours: 24,
      targets: {
        ph: { min: 5.6, max: 6.0 },
        ec: { min: 1.2, max: 1.6 }
      }
    }
  ] as Phase[]
})

const creating = ref(false)
const createdRecipe = ref<Recipe | null>(null)
const error = ref<string | null>(null)
const plants = ref<PlantOption[]>([])
const plantsLoading = ref(false)

watch(() => props.show, (show) => {
  if (show) {
    // Сброс формы при открытии
    form.name = ''
    form.description = ''
    form.plant_id = null
    form.phases = [
      {
        phase_index: 0,
        name: '',
        duration_hours: 24,
        targets: {
          ph: { min: 5.6, max: 6.0 },
          ec: { min: 1.2, max: 1.6 }
        }
      }
    ]
    createdRecipe.value = null
    error.value = null

    if (!plants.value.length) {
      loadPlants()
    }
  }
})

const loadPlants = async (): Promise<void> => {
  try {
    plantsLoading.value = true
    const response = await api.get('/plants')
    const data = response.data?.data || []
    plants.value = Array.isArray(data)
      ? data.map((plant: any) => ({ id: plant.id, name: plant.name }))
      : []

    if (!form.plant_id && plants.value.length === 1) {
      form.plant_id = plants.value[0].id
    }
  } catch (err) {
    logger.error('Failed to load plants:', err)
    showToast('Не удалось загрузить список культур', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    plantsLoading.value = false
  }
}

onMounted(() => {
  loadPlants()
})

function addPhase(): void {
  const maxIndex = form.phases.length > 0
    ? Math.max(...form.phases.map(p => p.phase_index))
    : -1
  form.phases.push({
    phase_index: maxIndex + 1,
    name: '',
    duration_hours: 24,
    targets: {
      ph: { min: 5.6, max: 6.0 },
      ec: { min: 1.2, max: 1.6 }
    }
  })
}

function removePhase(index: number): void {
  form.phases.splice(index, 1)
  // Переиндексируем фазы
  form.phases.forEach((phase, i) => {
    phase.phase_index = i
  })
}

async function onCreate(): Promise<void> {
  if (!form.name.trim()) {
    error.value = 'Название рецепта обязательно'
    return
  }

  if (!form.plant_id) {
    error.value = 'Выберите культуру для рецепта'
    return
  }

  if (form.phases.length === 0) {
    error.value = 'Добавьте хотя бы одну фазу'
    return
  }

  // Проверяем, что все фазы имеют названия
  const invalidPhases = form.phases.filter(p => !p.name.trim())
  if (invalidPhases.length > 0) {
    error.value = 'Все фазы должны иметь названия'
    return
  }

  creating.value = true
  error.value = null

  try {
    // 1. Создать рецепт
    const recipeResponse = await api.post<{ data?: Recipe } | Recipe>(
      '/recipes',
      {
        name: form.name.trim(),
        description: form.description.trim() || null,
        plant_id: form.plant_id,
      }
    )

    const recipe = (recipeResponse.data as { data?: Recipe })?.data || (recipeResponse.data as Recipe)
    const recipeId = recipe.id

    if (!recipeId) {
      throw new Error('Recipe ID not found in response')
    }

    // 2. Создать ревизию рецепта
    const revisionResponse = await api.post<{ data?: { id: number } } | { id: number }>(
      `/recipes/${recipeId}/revisions`,
      { description: 'Initial revision' }
    )
    const revision = (revisionResponse.data as { data?: { id: number } })?.data || (revisionResponse.data as { id: number })
    const revisionId = revision?.id
    if (!revisionId) {
      throw new Error('Recipe revision ID not found in response')
    }

    // 3. Создать фазы
    for (const phase of form.phases) {
      const phMin = phase.targets?.ph?.min ?? null
      const phMax = phase.targets?.ph?.max ?? null
      const phTarget = phMin !== null && phMax !== null ? (phMin + phMax) / 2 : (phMin ?? phMax)

      const ecMin = phase.targets?.ec?.min ?? null
      const ecMax = phase.targets?.ec?.max ?? null
      const ecTarget = ecMin !== null && ecMax !== null ? (ecMin + ecMax) / 2 : (ecMin ?? ecMax)

      await api.post(`/recipe-revisions/${revisionId}/phases`, {
        phase_index: phase.phase_index,
        name: phase.name.trim(),
        duration_hours: phase.duration_hours,
        ph_target: phTarget,
        ph_min: phMin,
        ph_max: phMax,
        ec_target: ecTarget,
        ec_min: ecMin,
        ec_max: ecMax,
      })
    }

    // 4. Опубликовать ревизию
    await api.post(`/recipe-revisions/${revisionId}/publish`)

    // 5. Загрузить полный рецепт с фазами
    const fullRecipeResponse = await api.get<{ data?: Recipe } | Recipe>(
      `/recipes/${recipeId}`
    )

    const fullRecipe = (fullRecipeResponse.data as { data?: Recipe })?.data || (fullRecipeResponse.data as Recipe)
    createdRecipe.value = fullRecipe

    logger.info('Recipe created:', fullRecipe)
    showToast('Рецепт успешно создан', 'success', TOAST_TIMEOUT.NORMAL)

    // Эмитим событие создания
    emit('created', fullRecipe)

    // Перенаправляем на страницу рецепта через небольшую задержку
    setTimeout(() => {
      emit('close')
      router.visit(`/recipes/${recipeId}`)
    }, 1000)
  } catch (err: any) {
    logger.error('Failed to create recipe:', err)
    error.value = err.response?.data?.message || err.message || 'Ошибка при создании рецепта'
  } finally {
    creating.value = false
  }
}
</script>
