<template>
  <div v-if="error" class="error-container min-h-screen flex items-center justify-center bg-neutral-950">
    <Card class="max-w-md w-full">
      <div class="text-center">
        <div class="text-6xl mb-4">⚠️</div>
        <h2 class="text-xl font-bold mb-2 text-red-400">Произошла ошибка</h2>
        <p class="text-sm text-neutral-400 mb-4">{{ error.message }}</p>
        
        <div v-if="isDev" class="text-left bg-neutral-900 p-3 rounded mb-4 overflow-auto max-h-40">
          <pre class="text-xs text-neutral-300">{{ error.stack }}</pre>
        </div>
        
        <div class="flex gap-2 justify-center">
          <Button @click="retry" variant="primary">Попробовать снова</Button>
          <Button @click="goHome" variant="secondary">На главную</Button>
        </div>
      </div>
    </Card>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { ref, onErrorCaptured, computed } from 'vue'
import { router } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import Card from './Card.vue'
import Button from './Button.vue'

const error = ref<Error | null>(null)
const isDev = computed(() => import.meta.env.DEV)

onErrorCaptured((err: Error) => {
  error.value = err
  logger.error('[ErrorBoundary] Caught error:', err)
  return false // Prevent propagation
})

function retry(): void {
  // Не перезагружаем страницу автоматически
  // Просто очищаем ошибку и позволяем пользователю продолжить работу
  error.value = null
  // НЕ вызываем router.reload() автоматически - это может вызвать бесконечный цикл
  // Если нужно обновить данные, это должно быть явным действием пользователя
  logger.info('[ErrorBoundary] Error cleared, user can continue working', {})
}

function goHome(): void {
  error.value = null
  router.visit('/')
}
</script>

