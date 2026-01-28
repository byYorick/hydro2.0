<template>
  <Transition name="toast">
    <div
      v-if="show"
      ref="toastElement"
      :data-toast-id="message"
      :data-testid="`toast-${variant}`"
      :class="[
        'fixed top-4 right-4 z-[10000] min-w-[300px] max-w-md rounded-lg border p-4 shadow-[var(--shadow-card)]',
        variantClasses[variant]
      ]"
      style="position: fixed !important; z-index: 10000 !important; display: block !important; visibility: visible !important; opacity: 1 !important;"
    >
      <div class="flex items-start gap-3">
        <div class="flex-shrink-0">
          <svg
            v-if="variant === 'success'"
            class="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <svg
            v-else-if="variant === 'error'"
            class="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <svg
            v-else
            class="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <div class="flex-1">
          <p
            class="text-sm font-medium"
            data-testid="toast-message"
          >
            {{ message }}
          </p>
        </div>
        <button
          class="flex-shrink-0 rounded-md p-1 hover:bg-[color:var(--bg-elevated)]"
          @click="show = false"
        >
          <svg
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import type { ToastVariant } from '@/composables/useToast'
import { logger } from '@/utils/logger'

interface Props {
  message: string
  variant?: ToastVariant
  duration?: number
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'info',
  duration: 3000
})

const emit = defineEmits<{
  close: []
}>()

const show = ref<boolean>(true) // Start visible
const toastElement = ref<HTMLElement | null>(null)

const variantClasses: Record<ToastVariant, string> = {
  success: 'bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)] border-[color:var(--badge-success-border)]',
  error: 'bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)] border-[color:var(--badge-danger-border)]',
  warning: 'bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)] border-[color:var(--badge-warning-border)]',
  info: 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]',
}

onMounted(() => {
  logger.debug('[Toast] Компонент смонтирован', { 
    message: props.message, 
    variant: props.variant,
    duration: props.duration,
    show: show.value,
    timestamp: new Date().toISOString()
  })
  
  // Force show to be true after mount to ensure visibility
  show.value = true
  
  // Log DOM element for debugging
  setTimeout(() => {
    try {
      // Используем ref вместо querySelector для надежного доступа к элементу
      const el = toastElement.value
      logger.debug('[Toast] DOM элемент найден', el)
      if (el) {
        logger.debug('[Toast] Стили элемента', {
          display: window.getComputedStyle(el).display,
          visibility: window.getComputedStyle(el).visibility,
          opacity: window.getComputedStyle(el).opacity,
          zIndex: window.getComputedStyle(el).zIndex,
          position: window.getComputedStyle(el).position,
          top: window.getComputedStyle(el).top,
          right: window.getComputedStyle(el).right,
        })
      }
    } catch (error) {
      // Игнорируем ошибки при отладке - это не критично
      logger.debug('[Toast] Не удалось найти DOM элемент для отладки', error)
    }
  }, 100)
  
  // Component starts visible, so we just need to set up auto-close
  if (props.duration > 0) {
    setTimeout(() => {
      logger.debug(`[Toast] Автоматическое закрытие через ${props.duration} мс`)
      show.value = false
    }, props.duration)
  }
  logger.debug('[Toast] show.value после onMounted', show.value)
})

// Emit close event when hidden
watch(show, (newVal) => {
  if (!newVal) {
    setTimeout(() => {
      emit('close')
    }, 300) // Wait for transition
  }
}, { immediate: false })
</script>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease;
}

.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-enter-to {
  opacity: 1;
  transform: translateX(0);
}

.toast-leave-from {
  opacity: 1;
  transform: translateX(0);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
