<template>
  <button
    class="btn btn-ghost h-9 px-3 text-xs"
    type="button"
    :aria-pressed="isDark"
    aria-label="Переключить тему"
    @click="toggleTheme"
  >
    <span class="flex items-center gap-2">
      <span
        class="h-2.5 w-2.5 rounded-full"
        :class="isDark ? 'bg-[color:var(--status-info)]' : 'bg-[color:var(--status-ok)]'"
      ></span>
      <span>{{ isDark ? 'Темная' : 'Светлая' }}</span>
    </span>
  </button>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { isDark, toggleTheme } = useTheme()
</script>
