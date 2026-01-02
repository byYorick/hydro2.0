<script setup lang="ts">
interface Props {
    value?: string
    for?: string
}

const props = defineProps<Props>()
</script>

<template>
  <label
    :for="props.for"
    class="block text-sm font-medium text-[color:var(--text-muted)]"
  >
    <span v-if="value">{{ value }}</span>
    <span v-else><slot></slot></span>
  </label>
</template>
