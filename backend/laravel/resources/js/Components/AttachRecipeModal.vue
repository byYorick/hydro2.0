<!--
  DEPRECATED: Этот компонент использует legacy модель recipeInstance.
  Используйте GrowCycles/Wizard.vue для создания циклов выращивания с рецептами.
-->
<template>
  <Modal :open="show" title="Привязать рецепт к зоне (Legacy)" @close="$emit('close')" data-testid="attach-recipe-modal">
    <div v-if="loading" class="text-sm text-[color:var(--text-muted)]">Загрузка...</div>
    <div v-else class="space-y-4">
      <div>
        <label for="attach-recipe-select" class="block text-xs text-[color:var(--text-muted)] mb-1">Выберите рецепт</label>
        <select
          id="attach-recipe-select"
          name="recipe_id"
          v-model="selectedRecipeId"
          class="input-select h-9 w-full"
          data-testid="attach-recipe-select"
        >
          <option :value="null">Выберите рецепт</option>
          <option
            v-for="recipe in recipes"
            :key="recipe.id"
            :value="recipe.id"
          >
            {{ recipe.name }} ({{ recipe.phases_count || 0 }} фаз)
          </option>
        </select>
      </div>
      
      <div v-if="selectedRecipeId">
        <label for="attach-recipe-start-at" class="block text-xs text-[color:var(--text-muted)] mb-1">Дата начала (опционально)</label>
        <input
          id="attach-recipe-start-at"
          name="start_at"
          v-model="startAt"
          type="datetime-local"
          class="input-field h-9 w-full"
          autocomplete="off"
        />
      </div>
      
      <div v-if="selectedRecipe && selectedRecipe.phases" class="text-xs text-[color:var(--text-muted)]">
        <div class="font-semibold mb-2">Фазы рецепта:</div>
        <div v-for="phase in selectedRecipe.phases" :key="phase.id" :data-testid="`recipe-phase-item-${phase.id || phase.phase_index}`" class="mb-1 pl-2 border-l-2 border-[color:var(--border-muted)]">
          {{ phase.phase_index + 1 }}. {{ phase.name }} — {{ phase.duration_hours }}ч
        </div>
      </div>
    </div>
    
    <template #footer>
      <Button size="sm" variant="secondary" @click="$emit('close')">Отмена</Button>
      <Button
        size="sm"
        @click="onAttach"
        :disabled="!selectedRecipeId || attaching"
      >
        {{ attaching ? 'Привязка...' : 'Привязать' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const { showToast } = useToast()
const { api } = useApi(showToast)

interface Props {
  show: boolean
  zoneId: number
}

interface Recipe {
  id: number
  name: string
  phases_count?: number
  phases?: Array<{
    id: number
    phase_index: number
    name: string
    duration_hours: number
  }>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  attached: [recipeId: number]
}>()

const loading = ref(false)
const attaching = ref(false)
const recipes = ref<Recipe[]>([])
const selectedRecipeId = ref<number | null>(null)
const startAt = ref<string>('')

const selectedRecipe = computed(() => {
  return recipes.value.find(r => r.id === selectedRecipeId.value)
})

watch(() => props.show, (show) => {
  if (show) {
    loadRecipes()
  }
})

onMounted(() => {
  if (props.show) {
    loadRecipes()
  }
})

async function loadRecipes(): Promise<void> {
  loading.value = true
  try {
    const response = await api.get<{ data?: Recipe[] } | Recipe[]>('/recipes')
    
    const data = (response.data as { data?: Recipe[] })?.data || (response.data as Recipe[])
    // Обрабатываем pagination response
    if (Array.isArray(data)) {
      recipes.value = data
    } else {
      recipes.value = []
    }
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to load recipes:', error)
  } finally {
    loading.value = false
  }
}

async function onAttach() {
  if (!selectedRecipeId.value) return
  
  attaching.value = true
  try {
    const payload: any = { recipe_id: selectedRecipeId.value }
    if (startAt.value) {
      payload.start_at = new Date(startAt.value).toISOString()
    }
    
    const response = await api.post(
      `/zones/${props.zoneId}/attach-recipe`,
      payload
    )
    
    // Проверяем успешный ответ
    logger.info('[AttachRecipeModal] Response received:', {
      data: response.data,
      recipeId: selectedRecipeId.value
    })
    
    if (response.data?.status === 'ok' || response.status === 200 || response.status === 201) {
      logger.info('[AttachRecipeModal] Recipe attached successfully, emitting event')
      
      // Эмитим событие для обновления UI и показа уведомления ПЕРЕД закрытием
      emit('attached', selectedRecipeId.value)
      
      // Небольшая задержка перед закрытием модального окна, чтобы дать время родителю обработать событие
      await new Promise(resolve => setTimeout(resolve, 50))
      
      emit('close')
    } else {
      throw new Error('Неожиданный ответ от сервера')
    }
  } catch (error: any) {
    logger.error('Failed to attach recipe:', error)
    // Не закрываем модальное окно при ошибке
    // emit('close') - убираем, чтобы пользователь мог попробовать снова
  } finally {
    attaching.value = false
  }
}
</script>
