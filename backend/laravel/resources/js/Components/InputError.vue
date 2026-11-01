<script setup lang="ts">
interface Props {
    message?: string | null
}

defineProps<Props>()
</script>

<template>
  <div v-show="message">
    <p class="text-sm text-[color:var(--status-critical)]">
      {{ message }}
    </p>
  </div>
</template>
