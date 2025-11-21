<template>
  <Modal :open="show" title="Привязать рецепт к зоне" @close="$emit('close')">
    <div v-if="loading" class="text-sm text-neutral-400">Загрузка...</div>
    <div v-else class="space-y-4">
      <div>
        <label class="block text-xs text-neutral-400 mb-1">Выберите рецепт</label>
        <select
          v-model="selectedRecipeId"
          class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
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
        <label class="block text-xs text-neutral-400 mb-1">Дата начала (опционально)</label>
        <input
          v-model="startAt"
          type="datetime-local"
          class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
        />
      </div>
      
      <div v-if="selectedRecipe && selectedRecipe.phases" class="text-xs text-neutral-400">
        <div class="font-semibold mb-2">Фазы рецепта:</div>
        <div v-for="phase in selectedRecipe.phases" :key="phase.id" class="mb-1 pl-2 border-l-2 border-neutral-700">
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
import axios from 'axios'
import { logger } from '@/utils/logger'

// Безопасные обёртки для логирования
const logInfo = logger?.info || ((...args: unknown[]) => console.log('[INFO]', ...args))
const logError = logger?.error || ((...args: unknown[]) => console.error('[ERROR]', ...args))

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

async function loadRecipes() {
  loading.value = true
  try {
    const response = await axios.get('/api/recipes', {
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    
    const data = response.data?.data
    // Обрабатываем pagination response
    if (data?.data && Array.isArray(data.data)) {
      recipes.value = data.data
    } else if (Array.isArray(data)) {
      recipes.value = data
    } else {
      recipes.value = []
    }
  } catch (error) {
    logError('Failed to load recipes:', error)
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
    
    const response = await axios.post(`/api/zones/${props.zoneId}/attach-recipe`, payload, {
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    
    // Проверяем успешный ответ
    logInfo('[AttachRecipeModal] Response received:', {
      status: response.status,
      data: response.data,
      recipeId: selectedRecipeId.value
    })
    
    if (response.data?.status === 'ok' || response.status === 200 || response.status === 201) {
      logInfo('[AttachRecipeModal] Recipe attached successfully, emitting event')
      
      // Эмитим событие для обновления UI и показа уведомления ПЕРЕД закрытием
      emit('attached', selectedRecipeId.value)
      
      // Небольшая задержка перед закрытием модального окна, чтобы дать время родителю обработать событие
      await new Promise(resolve => setTimeout(resolve, 50))
      
      emit('close')
    } else {
      throw new Error('Неожиданный ответ от сервера')
    }
  } catch (error: any) {
    logError('Failed to attach recipe:', error)
    const errorMessage = error.response?.data?.message || 
                        error.response?.data?.error || 
                        error.message || 
                        'Ошибка при привязке рецепта'
    alert(errorMessage)
    // Не закрываем модальное окно при ошибке
    // emit('close') - убираем, чтобы пользователь мог попробовать снова
  } finally {
    attaching.value = false
  }
}
</script>

