<template>
  <span
    :class="[
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium leading-tight',
      toneClass,
    ]"
  >
    <span
      v-if="$slots.icon"
      class="flex items-center"
    >
      <slot name="icon"></slot>
    </span>
    <slot></slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { chipToneClass, type ChipTone } from '@/theme/statusTones'

export type { ChipTone }

const props = withDefaults(defineProps<{ tone?: ChipTone }>(), { tone: 'neutral' })

const toneClass = computed(() => chipToneClass(props.tone))
</script>
