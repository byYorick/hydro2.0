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
import { statusPillClass, type StatusTone } from '@/theme/statusTones'

export type { StatusTone }

interface Props {
  tone?: StatusTone
}

const props = withDefaults(defineProps<Props>(), {
  tone: 'neutral',
})

const toneClass = computed(() => statusPillClass(props.tone))
</script>
