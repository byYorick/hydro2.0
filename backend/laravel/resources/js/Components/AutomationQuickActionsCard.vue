<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
      <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
        Операционные команды
      </h3>
      <div class="text-xs text-[color:var(--text-muted)]">
        Быстрые действия оператора
      </div>
    </div>

    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <Button
        size="sm"
        :disabled="!canOperateAutomation || quickActions.irrigation"
        @click="$emit('manual-irrigation')"
      >
        {{ quickActions.irrigation ? 'Отправка...' : 'Запустить полив' }}
      </Button>
      <Button
        size="sm"
        variant="secondary"
        :disabled="!canOperateAutomation || quickActions.climate"
        @click="$emit('manual-climate')"
      >
        {{ quickActions.climate ? 'Отправка...' : 'Применить климат' }}
      </Button>
      <Button
        size="sm"
        variant="secondary"
        :disabled="!canOperateAutomation || quickActions.lighting"
        @click="$emit('manual-lighting')"
      >
        {{ quickActions.lighting ? 'Отправка...' : 'Применить свет' }}
      </Button>
      <Button
        size="sm"
        variant="outline"
        :disabled="!canOperateAutomation || quickActions.ph"
        @click="$emit('manual-ph')"
      >
        {{ quickActions.ph ? 'Отправка...' : 'Дать target pH' }}
      </Button>
      <Button
        size="sm"
        variant="outline"
        :disabled="!canOperateAutomation || quickActions.ec"
        @click="$emit('manual-ec')"
      >
        {{ quickActions.ec ? 'Отправка...' : 'Дать target EC' }}
      </Button>
    </div>
  </section>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'

interface QuickActionsState {
  irrigation: boolean
  climate: boolean
  lighting: boolean
  ph: boolean
  ec: boolean
}

interface Props {
  canOperateAutomation: boolean
  quickActions: QuickActionsState
}

defineProps<Props>()

defineEmits<{
  (e: 'manual-irrigation'): void
  (e: 'manual-climate'): void
  (e: 'manual-lighting'): void
  (e: 'manual-ph'): void
  (e: 'manual-ec'): void
}>()
</script>
