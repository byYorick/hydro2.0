<template>
  <Modal
    :open="show"
    title="Привязать рецепт к зоне"
    @close="$emit('close')"
  >
    <div
      v-if="loading"
      class="text-sm text-neutral-400"
    >
      Загрузка...
    </div>
    <div
      v-else
      class="space-y-4"
    >
      <div>
        <label
          for="attach-recipe-select"
          class="block text-xs text-neutral-400 mb-1"
        >Выберите рецепт</label>
        <select
          id="attach-recipe-select"
          v-model="selectedRecipeId"
          name="recipe_id"
          class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
        >
          <option :value="null">
            Выберите рецепт
          </option>
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
        <label
          for="attach-recipe-start-at"
          class="block text-xs text-neutral-400 mb-1"
        >Дата начала (опционально)</label>
        <input
          id="attach-recipe-start-at"
          v-model="startAt"
          name="start_at"
          type="datetime-local"
          class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
          autocomplete="off"
        />
      </div>
      
      <div
        v-if="selectedRecipe && selectedRecipe.phases"
        class="text-xs text-neutral-400"
      >
        <div class="font-semibold mb-2">
          Фазы рецепта:
        </div>
        <div
          v-for="phase in selectedRecipe.phases"
          :key="phase.id"
          class="mb-1 pl-2 border-l-2 border-neutral-700"
        >
          {{ phase.phase_index + 1 }}. {{ phase.name }} — {{ phase.duration_hours }}ч
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
        :disabled="!selectedRecipeId || attaching"
        @click="onAttach"
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
import { useToast } from '@/composables/useToast'
import { api } from '@/services/api'

const { showToast } = useToast()

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
    const data = await api.recipes.list()
    recipes.value = Array.isArray(data) ? data as Recipe[] : []
  } catch (error) {
    showToast('Не удалось загрузить список рецептов', 'error')
    logger.error('Failed to load recipes:', error)
  } finally {
    loading.value = false
  }
}

async function onAttach() {
  if (!selectedRecipeId.value) return
  
  attaching.value = true
  try {
    const payload: { recipe_id: number; start_at?: string } = {
      recipe_id: selectedRecipeId.value,
    }
    if (startAt.value) {
      payload.start_at = new Date(startAt.value).toISOString()
    }

    const data = await api.zones.attachRecipe<{ status?: string } & Record<string, unknown>>(
      props.zoneId,
      payload,
    )

    logger.info('[AttachRecipeModal] Response received:', {
      data,
      recipeId: selectedRecipeId.value,
    })

    if (data?.status === 'ok') {
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

