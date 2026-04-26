<template>
  <component
    :is="useVertical ? VStepper : HStepper"
    :steps="steps"
    :active="active"
    :completion="completion"
    @select="(i: number) => $emit('select', i)"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import HStepper from './HStepper.vue'
import VStepper from './VStepper.vue'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { LaunchStep, StepCompletion } from './types'

defineProps<{
  steps: readonly LaunchStep[]
  active: number
  completion: readonly StepCompletion[]
}>()

defineEmits<{ (e: 'select', index: number): void }>()

const { stepper } = useLaunchPreferences()

// Vertical stepper только на ≥1280px (см. LAUNCH_REDESIGN.md §5.1, решение 4.14).
const wide = ref(false)
let mq: MediaQueryList | null = null

function syncMatch() {
  wide.value = mq?.matches ?? false
}

onMounted(() => {
  if (typeof window === 'undefined') return
  mq = window.matchMedia('(min-width: 1280px)')
  syncMatch()
  mq.addEventListener('change', syncMatch)
})

onUnmounted(() => {
  if (mq) mq.removeEventListener('change', syncMatch)
})

const useVertical = computed(() => stepper.value === 'vertical' && wide.value)
</script>
