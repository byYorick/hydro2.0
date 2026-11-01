<template>
  <EmptyState
    variant="error"
    :title="title"
    :description="description"
    icon="!"
  >
    <template
      v-if="$slots.action"
      #action
    >
      <slot name="action"></slot>
    </template>
  </EmptyState>
</template>

<script setup lang="ts">
import EmptyState from '@/Components/EmptyState.vue'

interface Props {
  title: string
  description?: string
}

withDefaults(defineProps<Props>(), {
  description: '',
})
</script>
