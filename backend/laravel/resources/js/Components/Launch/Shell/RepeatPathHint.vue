<template>
  <div
    class="mb-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-muted)]"
    data-testid="launch-repeat-path-hint"
  >
    <p>
      Зона уже готова — калибровка и автоматика вынесены в сторону.
      Откройте их через быстрый переход, если нужно что-то поменять.
    </p>
    <div class="mt-2 flex flex-wrap gap-2">
      <Button
        v-if="showAutomation"
        size="sm"
        variant="secondary"
        @click="$emit('open-automation')"
      >
        Автоматика
      </Button>
      <Button
        v-if="showCalibration"
        size="sm"
        variant="secondary"
        @click="$emit('open-calibration')"
      >
        Калибровка
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'

defineProps<{
  showAutomation: boolean
  showCalibration: boolean
}>()

defineEmits<{
  (e: 'open-automation'): void
  (e: 'open-calibration'): void
}>()
</script>
