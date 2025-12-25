<template>
  <div class="status-indicator-wrapper" :class="wrapperClass">
    <!-- Светодиодный индикатор -->
    <div
      class="status-indicator"
      :class="[
        `status-${statusVariant}`,
        { 'status-pulse': pulse },
        { 'status-large': size === 'large' },
        { 'status-small': size === 'small' }
      ]"
      :title="tooltip || statusText"
      :aria-label="`Статус: ${statusText}`"
    >
      <div class="status-indicator-inner"></div>
    </div>
    
    <!-- Текст статуса (опционально) -->
    <span v-if="showLabel" class="status-label ml-2 text-xs font-medium">
      {{ statusText }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { translateStatus } from '@/utils/i18n'

interface Props {
  status: string
  pulse?: boolean
  size?: 'small' | 'medium' | 'large'
  showLabel?: boolean
  tooltip?: string
  variant?: 'success' | 'warning' | 'danger' | 'neutral' | 'info'
}

const props = withDefaults(defineProps<Props>(), {
  pulse: false,
  size: 'medium',
  showLabel: false,
  tooltip: '',
  variant: undefined,
})

const statusVariant = computed(() => {
  if (props.variant) {
    return props.variant
  }
  
  const status = props.status.toUpperCase()
  
  // Определяем вариант по статусу
  if (['RUNNING', 'ONLINE', 'ACTIVE', 'SUCCESS'].includes(status)) {
    return 'success'
  }
  if (['PAUSED', 'NEUTRAL', 'IDLE'].includes(status)) {
    return 'neutral'
  }
  if (['WARNING', 'CAUTION'].includes(status)) {
    return 'warning'
  }
  if (['ALARM', 'OFFLINE', 'ERROR', 'FAILED', 'DANGER'].includes(status)) {
    return 'danger'
  }
  if (['INFO', 'INFO'].includes(status)) {
    return 'info'
  }
  
  return 'neutral'
})

const statusText = computed(() => {
  return translateStatus(props.status)
})

const wrapperClass = computed(() => {
  return {
    'flex items-center': props.showLabel,
    'inline-flex': !props.showLabel,
  }
})
</script>

<style scoped>
.status-indicator-wrapper {
  display: inline-flex;
  align-items: center;
}

.status-indicator {
  position: relative;
  display: inline-block;
  border-radius: 50%;
  background: var(--bg-elevated);
  border: 2px solid var(--border-muted);
  transition: all 0.2s ease;
}

.status-indicator-inner {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  transition: all 0.2s ease;
}

/* Размеры */
.status-indicator.status-small {
  width: 8px;
  height: 8px;
}

.status-indicator.status-small .status-indicator-inner {
  width: 4px;
  height: 4px;
}

.status-indicator.status-medium {
  width: 12px;
  height: 12px;
}

.status-indicator.status-medium .status-indicator-inner {
  width: 6px;
  height: 6px;
}

.status-indicator.status-large {
  width: 16px;
  height: 16px;
}

.status-indicator.status-large .status-indicator-inner {
  width: 8px;
  height: 8px;
}

/* Варианты статусов */
.status-indicator.status-success {
  border-color: var(--accent-green);
  background: var(--badge-success-bg);
}

.status-indicator.status-success .status-indicator-inner {
  background: var(--accent-green);
  box-shadow: 0 0 4px var(--accent-green);
}

.status-indicator.status-warning {
  border-color: var(--accent-amber);
  background: var(--badge-warning-bg);
}

.status-indicator.status-warning .status-indicator-inner {
  background: var(--accent-amber);
  box-shadow: 0 0 4px var(--accent-amber);
}

.status-indicator.status-danger {
  border-color: var(--accent-red);
  background: var(--badge-danger-bg);
}

.status-indicator.status-danger .status-indicator-inner {
  background: var(--accent-red);
  box-shadow: 0 0 4px var(--accent-red);
}

.status-indicator.status-neutral {
  border-color: var(--text-muted);
  background: var(--bg-elevated);
}

.status-indicator.status-neutral .status-indicator-inner {
  background: var(--text-muted);
}

.status-indicator.status-info {
  border-color: var(--accent-cyan);
  background: var(--badge-info-bg);
}

.status-indicator.status-info .status-indicator-inner {
  background: var(--accent-cyan);
  box-shadow: 0 0 4px var(--accent-cyan);
}

/* Пульсация для критичных статусов */
.status-indicator.status-pulse.status-success .status-indicator-inner {
  animation: pulse-green 2s ease-in-out infinite;
}

.status-indicator.status-pulse.status-warning .status-indicator-inner {
  animation: pulse-amber 2s ease-in-out infinite;
}

.status-indicator.status-pulse.status-danger .status-indicator-inner {
  animation: pulse-red 2s ease-in-out infinite;
}

.status-indicator.status-pulse.status-info .status-indicator-inner {
  animation: pulse-cyan 2s ease-in-out infinite;
}

@keyframes pulse-green {
  0%, 100% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    opacity: 0.7;
    transform: translate(-50%, -50%) scale(1.2);
  }
}

@keyframes pulse-amber {
  0%, 100% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    opacity: 0.7;
    transform: translate(-50%, -50%) scale(1.2);
  }
}

@keyframes pulse-red {
  0%, 100% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    opacity: 0.7;
    transform: translate(-50%, -50%) scale(1.2);
  }
}

@keyframes pulse-cyan {
  0%, 100% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    opacity: 0.7;
    transform: translate(-50%, -50%) scale(1.2);
  }
}

.status-label {
  color: var(--text-primary);
  user-select: none;
}
</style>

