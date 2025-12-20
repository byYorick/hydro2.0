<template>
  <div v-if="error" class="error-container min-h-screen flex items-center justify-center bg-[color:var(--bg-main)]">
    <Card class="max-w-md w-full">
      <div class="text-center">
        <div class="text-6xl mb-4">⚠️</div>
        <h2 class="text-xl font-bold mb-2 text-[color:var(--accent-red)]">Произошла ошибка</h2>
        <p class="text-sm text-[color:var(--text-muted)] mb-4">{{ error.message }}</p>
        
        <div v-if="isDev" class="text-left bg-[color:var(--bg-elevated)] p-3 rounded mb-4 overflow-auto max-h-40">
          <pre class="text-xs text-[color:var(--text-primary)]">{{ error.stack }}</pre>
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
import { ref, onErrorCaptured, computed, nextTick } from 'vue'
import { router } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import Card from './Card.vue'
import Button from './Button.vue'

const error = ref<Error | null>(null)
const isDev = computed(() => import.meta.env.DEV)
const isRetrying = ref(false)

onErrorCaptured((err: Error) => {
  // Предотвращаем повторный перехват ошибки во время retry
  if (isRetrying.value) {
    logger.debug('[ErrorBoundary] Ignoring error during retry', {})
    return false
  }
  
  try {
    error.value = err
    logger.error('[ErrorBoundary] Caught error:', err)
  } catch (e) {
    // Если установка error.value сама вызывает ошибку, логируем и игнорируем
    logger.error('[ErrorBoundary] Failed to set error state:', e)
  }
  return false // Prevent propagation
})

async function retry(): Promise<void> {
  // Предотвращаем множественные вызовы retry
  if (isRetrying.value) {
    logger.debug('[ErrorBoundary] Retry already in progress', {})
    return
  }
  
  isRetrying.value = true
  
  try {
    // Очищаем ошибку в следующем тике, чтобы избежать конфликтов с реактивностью
    await nextTick()
    error.value = null
    
    // Даем время Vue обновить DOM перед следующей попыткой
    await nextTick()
    
    logger.info('[ErrorBoundary] Error cleared, user can continue working', {})
  } catch (e) {
    logger.error('[ErrorBoundary] Error during retry:', e)
    // Если retry сам вызывает ошибку, оставляем состояние ошибки
    error.value = e instanceof Error ? e : new Error(String(e))
  } finally {
    // Сбрасываем флаг после небольшой задержки, чтобы дать время компонентам отрендериться
    setTimeout(() => {
      isRetrying.value = false
    }, 100)
  }
}

function goHome(): void {
  isRetrying.value = true
  error.value = null
  router.visit('/')
}
</script>
