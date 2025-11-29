<template>
  <div class="flex flex-col gap-2">
    <div class="text-xs font-semibold text-neutral-300 mb-1">Управление Lifecycle</div>
    
    <div v-if="loading" class="text-xs text-neutral-400">Загрузка...</div>
    
    <div v-else-if="error" class="text-xs text-red-400">{{ error }}</div>
    
    <div v-else-if="allowedTransitions.length === 0" class="text-xs text-neutral-400">
      Нет доступных переходов
    </div>
    
    <div v-else class="flex items-center gap-2">
      <select
        v-model="selectedState"
        class="h-9 flex-1 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm text-neutral-200"
        :disabled="transitioning"
      >
        <option :value="null">Выберите состояние...</option>
        <option 
          v-for="state in allowedTransitions" 
          :key="state.value"
          :value="state.value"
        >
          {{ state.label }}
          <span v-if="state.is_active" class="text-emerald-400">(Активно)</span>
        </option>
      </select>
      
      <Button
        size="sm"
        :disabled="!selectedState || transitioning || selectedState === currentState?.value"
        @click="handleTransition"
      >
        <span v-if="transitioning">Переход...</span>
        <span v-else>Перейти</span>
      </Button>
    </div>
    
    <div v-if="currentState" class="text-xs text-neutral-500">
      Текущее состояние: <span class="text-neutral-300">{{ currentState.label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import Button from './Button.vue'
import { useNodeLifecycle, type AllowedTransition, type CurrentState } from '@/composables/useNodeLifecycle'
import { logger } from '@/utils/logger'
import type { NodeLifecycleState } from '@/types/Device'

// Простая обертка для toast (если useToast недоступен)
function showToast(message: string, variant: string = 'info', duration: number = 3000): void {
  logger.debug(`[Toast ${variant}]:`, message)
}

interface Props {
  nodeId: number
  currentLifecycleState?: NodeLifecycleState | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  transitioned: [data: { nodeId: number; fromState: NodeLifecycleState; toState: NodeLifecycleState }]
}>()

const { transitionNode, getAllowedTransitions, loading: lifecycleLoading } = useNodeLifecycle(showToast)

const loading = ref(false)
const error = ref<string | null>(null)
const transitioning = ref(false)
const selectedState = ref<NodeLifecycleState | null>(null)
const currentState = ref<CurrentState | null>(null)
const allowedTransitions = ref<AllowedTransition[]>([])

/**
 * Загрузить разрешенные переходы
 */
async function loadAllowedTransitions(): Promise<void> {
  loading.value = true
  error.value = null
  
  try {
    const data = await getAllowedTransitions(props.nodeId)
    
    if (data) {
      currentState.value = data.current_state
      allowedTransitions.value = data.allowed_transitions
      
      // Если текущее состояние из props, обновляем его
      if (props.currentLifecycleState && props.currentLifecycleState !== data.current_state.value) {
        // Состояние из props не совпадает с API - используем API данные
      }
    }
  } catch (err: any) {
    error.value = err.message || 'Ошибка загрузки разрешенных переходов'
    logger.error('[NodeLifecycleTransition] Failed to load transitions:', err)
  } finally {
    loading.value = false
  }
}

/**
 * Выполнить переход в выбранное состояние
 */
async function handleTransition(): Promise<void> {
  if (!selectedState.value || !currentState.value) return
  
  transitioning.value = true
  error.value = null
  
  try {
    const result = await transitionNode(
      props.nodeId,
      selectedState.value,
      'Переход выполнен через UI'
    )
    
    if (result) {
      const fromState = (currentState.value.value as NodeLifecycleState)
      const toState = selectedState.value
      
      // Обновляем текущее состояние
      currentState.value = allowedTransitions.value.find(s => s.value === toState) as CurrentState || null
      
      // Эмитим событие
      emit('transitioned', {
        nodeId: props.nodeId,
        fromState,
        toState,
      })
      
      // Сбрасываем выбор
      selectedState.value = null
      
      // Перезагружаем разрешенные переходы
      await loadAllowedTransitions()
    }
  } catch (err: any) {
    error.value = err.message || 'Ошибка перехода состояния'
  } finally {
    transitioning.value = false
  }
}

/**
 * Инициализация при монтировании
 */
onMounted(() => {
  loadAllowedTransitions()
})

/**
 * Реакция на изменение nodeId
 */
watch(() => props.nodeId, () => {
  loadAllowedTransitions()
})

/**
 * Реакция на изменение текущего состояния из props
 */
watch(() => props.currentLifecycleState, (newState) => {
  if (newState && currentState.value?.value !== newState) {
    // Обновляем текущее состояние, если оно изменилось
    loadAllowedTransitions()
  }
})

// Импорт logger
import { logger } from '@/utils/logger'
</script>

