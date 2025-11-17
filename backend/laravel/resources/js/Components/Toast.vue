<template>
  <Transition name="toast">
    <div
      v-if="show"
      :data-toast-id="message"
      :class="[
        'fixed top-4 right-4 z-[10000] min-w-[300px] max-w-md rounded-lg border p-4 shadow-2xl',
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
          <p class="text-sm font-medium">{{ message }}</p>
        </div>
        <button
          @click="show = false"
          class="flex-shrink-0 rounded-md p-1 hover:bg-black/20"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

<script setup>
import { ref, watch, onMounted } from 'vue'

const props = defineProps({
  message: { type: String, required: true },
  variant: { type: String, default: 'info' }, // success | error | info
  duration: { type: Number, default: 3000 },
})

const show = ref(true) // Start visible

const variantClasses = {
  success: 'bg-emerald-900/90 text-emerald-100 border-emerald-700',
  error: 'bg-red-900/90 text-red-100 border-red-700',
  info: 'bg-sky-900/90 text-sky-100 border-sky-700',
}

onMounted(() => {
  console.log('=== [Toast] Компонент смонтирован ===', { 
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
    const el = document.querySelector(`[data-toast-id="${props.message}"]`)
    console.log('[Toast] DOM элемент найден:', el)
    if (el) {
      console.log('[Toast] Стили элемента:', {
        display: window.getComputedStyle(el).display,
        visibility: window.getComputedStyle(el).visibility,
        opacity: window.getComputedStyle(el).opacity,
        zIndex: window.getComputedStyle(el).zIndex,
        position: window.getComputedStyle(el).position,
        top: window.getComputedStyle(el).top,
        right: window.getComputedStyle(el).right,
      })
    }
  }, 100)
  
  // Component starts visible, so we just need to set up auto-close
  if (props.duration > 0) {
    setTimeout(() => {
      console.log('[Toast] Автоматическое закрытие через', props.duration, 'мс')
      show.value = false
    }, props.duration)
  }
  console.log('[Toast] show.value после onMounted:', show.value)
})

// Emit close event when hidden
watch(show, (newVal) => {
  if (!newVal) {
    setTimeout(() => {
      emit('close')
    }, 300) // Wait for transition
  }
}, { immediate: false })

const emit = defineEmits(['close'])
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

