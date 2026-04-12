<template>
  <section class="ui-hero px-3 py-2 md:px-4 md:py-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <!-- Левая часть: заголовок + бейджи -->
      <div class="flex flex-wrap items-center gap-1.5 min-w-0">
        <h3 class="font-headline text-base font-bold tracking-tight text-[color:var(--text-primary)]">
          Планировщик
        </h3>
        <span class="text-xs text-[color:var(--text-dim)]">· зона #{{ zoneId }}</span>
        <Badge variant="info" size="sm">Live</Badge>
        <Badge :variant="statusVariant(hasActiveRun ? 'running' : 'accepted')" size="sm">
          {{ controlModeLabel(controlMode) }}
        </Badge>
      </div>

      <!-- Правая часть: горизонт + обновить -->
      <div class="flex items-center gap-1.5">
        <div class="inline-flex items-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-0.5 backdrop-blur">
          <Button
            size="sm"
            :variant="horizon === '24h' ? 'secondary' : 'ghost'"
            class="h-6 px-2 text-[11px]"
            @click="$emit('change-horizon', '24h')"
          >
            24h
          </Button>
          <Button
            size="sm"
            :variant="horizon === '7d' ? 'secondary' : 'ghost'"
            class="h-6 px-2 text-[11px]"
            @click="$emit('change-horizon', '7d')"
          >
            7d
          </Button>
        </div>
        <Button
          size="sm"
          variant="outline"
          class="h-6 px-2 text-[11px]"
          :disabled="loading"
          @click="$emit('refresh')"
        >
          {{ loading ? '...' : '↻' }}
        </Button>
      </div>
    </div>

    <!-- KPI счётчики -->
    <SchedulerStatCounters
      class="mt-2"
      :active="counters.active"
      :completed-24h="counters.completed_24h"
      :failed-24h="counters.failed_24h"
      :executable-windows="executableWindowsCount"
    />

    <!-- Ошибка загрузки -->
    <p
      v-if="error"
      class="mt-2 rounded-lg border border-red-200/60 bg-red-50/40 px-2.5 py-1.5 text-[11px] text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-400"
    >
      {{ error }}
    </p>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import SchedulerStatCounters from './SchedulerStatCounters.vue'

interface ExecutionCounters {
  active: number
  completed_24h: number
  failed_24h: number
}

defineProps<{
  zoneId: number | string
  horizon: '24h' | '7d'
  loading: boolean
  error: string | null
  counters: ExecutionCounters
  executableWindowsCount: number
  hasActiveRun: boolean
  controlMode: string | null | undefined
  controlModeLabel: (controlMode: string | null | undefined) => string
  statusVariant: (status: string) => any
}>()

defineEmits<{
  refresh: []
  'change-horizon': ['24h' | '7d']
}>()
</script>
