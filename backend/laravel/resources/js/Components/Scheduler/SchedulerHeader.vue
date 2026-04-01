<template>
  <section class="ui-hero p-4 md:p-5">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
            Scheduler Workspace · зона #{{ zoneId }}
          </span>
          <Badge variant="info">
            Live sync
          </Badge>
          <Badge :variant="statusVariant(hasActiveRun ? 'running' : 'accepted')">
            {{ controlModeLabel(controlMode) }}
          </Badge>
          <Badge variant="secondary">
            {{ horizon.toUpperCase() }}
          </Badge>
        </div>
        <h3 class="mt-2 font-headline text-2xl font-bold tracking-tight text-[color:var(--text-primary)]">
          Планировщик зоны
        </h3>
        <p class="mt-1 text-sm text-[color:var(--text-dim)]">
          Краткая операторская сводка: что происходит сейчас, что требует внимания и какие окна реально исполнимы.
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <div class="inline-flex items-center rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-1 backdrop-blur">
          <Button
            size="sm"
            :variant="horizon === '24h' ? 'secondary' : 'ghost'"
            @click="$emit('change-horizon', '24h')"
          >
            24h
          </Button>
          <Button
            size="sm"
            :variant="horizon === '7d' ? 'secondary' : 'ghost'"
            @click="$emit('change-horizon', '7d')"
          >
            7d
          </Button>
        </div>
        <Button
          size="sm"
          variant="outline"
          :disabled="loading"
          @click="$emit('refresh')"
        >
          {{ loading ? 'Обновляем...' : 'Обновить' }}
        </Button>
      </div>
    </div>

    <SchedulerStatCounters
      class="mt-4"
      :active="counters.active"
      :completed-24h="counters.completed_24h"
      :failed-24h="counters.failed_24h"
      :executable-windows="executableWindowsCount"
    />

    <p
      v-if="error"
      class="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
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

