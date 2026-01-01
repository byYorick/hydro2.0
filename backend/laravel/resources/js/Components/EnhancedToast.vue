<template>
  <TransitionGroup
    name="toast-group"
    tag="div"
    class="fixed z-[10000] pointer-events-none space-y-2 left-4 right-4 bottom-[calc(env(safe-area-inset-bottom,0px)+4.5rem)] sm:left-auto sm:right-4 sm:bottom-auto sm:top-4"
  >
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="pointer-events-auto"
      style="pointer-events: auto;"
    >
      <div
        :class="[
          'min-w-[300px] max-w-md rounded-lg border p-4 shadow-[var(--shadow-card)] backdrop-blur-sm',
          variantClasses[toast.variant ?? 'info'],
          toast.grouped && 'border-l-4'
        ]"
      >
        <div class="flex items-start gap-3">
          <!-- Иконка -->
          <div class="flex-shrink-0 mt-0.5">
            <!-- Success -->
            <svg
              v-if="toast.variant === 'success'"
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
            <!-- Error -->
            <svg
              v-else-if="toast.variant === 'error'"
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
            <!-- Warning -->
            <svg
              v-else-if="toast.variant === 'warning'"
              class="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <!-- Info -->
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
          
          <!-- Контент -->
          <div class="flex-1 min-w-0">
            <div v-if="toast.title" class="text-sm font-semibold mb-1">
              {{ toast.title }}
            </div>
            <p class="text-sm" :class="toast.title ? 'text-[color:var(--text-muted)]' : 'font-medium'">
              {{ toast.message }}
            </p>
            
            <!-- Действия -->
            <div v-if="toast.actions && toast.actions.length > 0" class="flex gap-2 mt-3">
              <button
                v-for="action in toast.actions"
                :key="action.label"
                @click="handleAction(toast.id, action)"
                class="text-xs px-2 py-1 rounded border transition-colors"
                :class="action.variant === 'primary' 
                  ? 'border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] hover:bg-[color:var(--bg-elevated)]' 
                  : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] hover:bg-[color:var(--bg-surface-strong)]'"
              >
                {{ action.label }}
              </button>
            </div>
          </div>
          
          <!-- Кнопка закрытия -->
          <button
            @click="handleClose(toast.id)"
            class="flex-shrink-0 rounded-md p-1 hover:bg-[color:var(--bg-elevated)] transition-colors"
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
        
        <!-- Прогресс-бар для автоскрытия -->
        <div
          v-if="(toast.duration ?? 0) > 0 && toast.showProgress"
          class="mt-3 h-1 bg-[color:var(--border-muted)] rounded-full overflow-hidden"
        >
          <div
            class="h-full transition-all duration-100 ease-linear"
            :class="progressBarColor(toast.variant)"
            :style="{ width: `${toast.progress}%` }"
          />
        </div>
      </div>
    </div>
  </TransitionGroup>
</template>

<script setup lang="ts">

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

export interface ToastAction {
  label: string
  variant?: 'primary' | 'secondary'
  handler: () => void
}

export interface Toast {
  id: number
  message: string
  variant?: ToastVariant
  duration?: number
  title?: string
  actions?: ToastAction[]
  grouped?: boolean
  showProgress?: boolean
  progress?: number
}

defineProps<{
  toasts: Toast[]
}>()

const emit = defineEmits<{
  close: [id: number]
  action: [id: number, action: ToastAction]
}>()

const variantClasses: Record<ToastVariant, string> = {
  success: 'bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)] border-[color:var(--badge-success-border)]',
  error: 'bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)] border-[color:var(--badge-danger-border)]',
  warning: 'bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)] border-[color:var(--badge-warning-border)]',
  info: 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]',
}

function progressBarColor(variant: ToastVariant = 'info'): string {
  const colors = {
    success: 'bg-[color:var(--accent-green)]',
    error: 'bg-[color:var(--accent-red)]',
    warning: 'bg-[color:var(--accent-amber)]',
    info: 'bg-[color:var(--accent-cyan)]',
  }
  return colors[variant]
}

function handleClose(id: number) {
  emit('close', id)
}

function handleAction(id: number, action: ToastAction) {
  emit('action', id, action)
  action.handler()
}
</script>

<style scoped>
.toast-group-enter-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toast-group-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toast-group-enter-from {
  opacity: 0;
  transform: translateX(100%) scale(0.95);
}

.toast-group-enter-to {
  opacity: 1;
  transform: translateX(0) scale(1);
}

.toast-group-leave-from {
  opacity: 1;
  transform: translateX(0) scale(1);
}

.toast-group-leave-to {
  opacity: 0;
  transform: translateX(100%) scale(0.95);
}

.toast-group-move {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
