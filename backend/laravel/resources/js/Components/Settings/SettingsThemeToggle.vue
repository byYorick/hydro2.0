<template>
  <SettingsFieldCard
    label="Тема"
    description="Оформление интерфейса в этом браузере."
    :show-description="false"
    test-id="settings-theme-toggle"
  >
    <div
      class="flex gap-2"
      role="group"
      aria-label="Тема"
    >
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        class="px-3 py-1.5 text-sm font-semibold rounded-lg border transition-colors"
        :class="theme === option.value
          ? 'bg-[color:var(--bg-surface-strong)] text-[color:var(--text-primary)] border-[color:var(--border-strong)]'
          : 'text-[color:var(--text-dim)] border-[color:var(--border-muted)] hover:text-[color:var(--text-primary)]'"
        :aria-pressed="theme === option.value"
        :data-testid="`settings-theme-${option.value}`"
        @click="setTheme(option.value)"
      >
        {{ option.label }}
      </button>
    </div>
  </SettingsFieldCard>
</template>

<script setup lang="ts">
import SettingsFieldCard from '@/Components/Settings/SettingsFieldCard.vue'
import { useTheme } from '@/composables/useTheme'

const { theme, setTheme } = useTheme()

const options = [
  { value: 'light' as const, label: 'Светлая' },
  { value: 'dark' as const, label: 'Тёмная' },
]
</script>
