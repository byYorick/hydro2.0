<template>
  <div :class="classes">
    <div
      v-for="i in lines"
      :key="i"
      class="animate-pulse bg-[color:var(--bg-elevated)]"
      :class="lineClass"
      :style="{
        height: lineHeight,
        width: i === lines ? tailWidth : '100%',
      }"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

interface Props {
  lines?: number
  lineHeight?: string
  tailWidth?: string
  containerClass?: string
  lineClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  lines: 3,
  lineHeight: '0.75rem',
  tailWidth: '60%',
  containerClass: '',
  lineClass: 'rounded',
})

const attrs = useAttrs()

const classes = computed(() => {
  const base = 'space-y-2'
  return [base, props.containerClass, attrs.class].filter(Boolean).join(' ')
})
</script>
