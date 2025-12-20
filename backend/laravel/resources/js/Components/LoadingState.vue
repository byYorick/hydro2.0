<template>
  <div
    v-if="loading"
    :class="[
      'flex items-center justify-center',
      fullScreen ? 'fixed inset-0 z-50 bg-[color:var(--bg-main)] opacity-80 backdrop-blur-sm' : 'py-8',
      containerClass
    ]"
  >
    <div class="flex flex-col items-center gap-4">
      <!-- Spinner -->
      <div
        :class="[
          'animate-spin rounded-full border-2 border-t-transparent',
          sizeClasses[size]
        ]"
        :style="{
          borderColor: color,
          borderTopColor: 'transparent',
        }"
      />
      
      <!-- Message -->
      <p
        v-if="message"
        :class="[
          'text-sm font-medium',
          textColorClass
        ]"
      >
        {{ message }}
      </p>
    </div>
  </div>
  
  <!-- Skeleton loader для контента -->
  <div
    v-else-if="skeleton && !loading"
    :class="skeletonClass"
  >
    <div
      v-for="i in skeletonLines"
      :key="i"
      class="animate-pulse rounded bg-[color:var(--bg-elevated)]"
      :style="{
        height: skeletonHeight,
        width: i === skeletonLines ? '60%' : '100%',
        marginBottom: '0.5rem',
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  loading?: boolean
  message?: string
  size?: 'sm' | 'md' | 'lg'
  color?: string
  fullScreen?: boolean
  containerClass?: string
  skeleton?: boolean
  skeletonLines?: number
  skeletonHeight?: string
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  message: '',
  size: 'md',
  color: 'var(--accent-cyan)',
  fullScreen: false,
  containerClass: '',
  skeleton: false,
  skeletonLines: 3,
  skeletonHeight: '1rem',
})

const sizeClasses = {
  sm: 'h-4 w-4 border',
  md: 'h-8 w-8 border-2',
  lg: 'h-12 w-12 border-4',
}

const textColorClass = computed(() => {
  return props.fullScreen ? 'text-[color:var(--text-primary)]' : 'text-[color:var(--text-muted)]'
})

const skeletonClass = computed(() => {
  return props.containerClass || 'space-y-2'
})
</script>

<style scoped>
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.animate-spin {
  animation: spin 1s linear infinite;
}

.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>
