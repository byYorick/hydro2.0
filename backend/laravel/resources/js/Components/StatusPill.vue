<template>
  <span
    class="status-chip"
    :class="toneClass"
    role="status"
  >
    <slot></slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type StatusTone = 'ok' | 'warning' | 'critical' | 'offline' | 'info' | 'neutral'

interface Props {
  tone?: StatusTone
}

const props = withDefaults(defineProps<Props>(), {
  tone: 'neutral',
})

const toneClass = computed(() => {
  switch (props.tone) {
    case 'ok':
      return 'status-chip--running'
    case 'warning':
      return 'status-chip--warning'
    case 'critical':
      return 'status-chip--alarm'
    case 'offline':
      return 'status-chip--offline'
    case 'info':
      return 'status-chip--paused'
    default:
      return 'badge--neutral'
  }
})
</script>
