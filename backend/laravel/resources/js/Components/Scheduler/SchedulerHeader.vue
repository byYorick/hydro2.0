<template>
  <section class="scheduler-header ui-hero px-3 py-3 md:px-5 md:py-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span
            class="scheduler-header__glyph"
            aria-hidden="true"
          ></span>
          <div class="min-w-0">
            <p class="text-[10px] font-bold uppercase tracking-[0.22em] text-[color:var(--text-dim)]">
              Scheduler cockpit
            </p>
            <h3 class="font-headline text-lg font-bold tracking-tight text-[color:var(--text-primary)] md:text-xl">
              Планировщик зоны
              <span class="text-sm font-semibold text-[color:var(--text-muted)]">#{{ zoneId }}</span>
            </h3>
          </div>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-1.5">
          <Badge
            variant="info"
            size="sm"
          >
            <span class="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--accent-cyan)] shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent-cyan)_20%,transparent)]"></span>
            Live sync
          </Badge>
          <Badge
            :variant="statusVariant(hasActiveRun ? 'running' : 'accepted')"
            size="sm"
          >
            {{ controlModeLabel(controlMode) }}
          </Badge>
          <span class="text-[11px] text-[color:var(--text-dim)]">
            {{ hasActiveRun ? 'идёт активное исполнение' : 'ожидаем ближайшее окно' }}
          </span>
        </div>
      </div>

      <div class="flex items-center gap-1.5 rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/60 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur">
        <div class="inline-flex items-center rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-main)]/30 p-0.5">
          <Button
            size="sm"
            :variant="horizon === '24h' ? 'secondary' : 'ghost'"
            class="h-7 px-2.5 text-[11px]"
            @click="$emit('change-horizon', '24h')"
          >
            24h
          </Button>
          <Button
            size="sm"
            :variant="horizon === '7d' ? 'secondary' : 'ghost'"
            class="h-7 px-2.5 text-[11px]"
            @click="$emit('change-horizon', '7d')"
          >
            7d
          </Button>
        </div>
        <Button
          size="sm"
          variant="outline"
          class="h-8 px-2.5 text-[11px]"
          :disabled="loading"
          @click="$emit('refresh')"
        >
          <span class="md:hidden">{{ loading ? '...' : '↻' }}</span>
          <span class="hidden md:inline">{{ loading ? 'Обновляем...' : 'Обновить' }}</span>
        </Button>
      </div>
    </div>

    <SchedulerStatCounters
      class="mt-3"
      :active="counters.active"
      :completed-24h="counters.completed_24h"
      :failed-24h="counters.failed_24h"
      :executable-windows="executableWindowsCount"
    />

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

<style scoped>
.scheduler-header {
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    var(--shadow-card);
}

.scheduler-header__glyph {
  display: inline-block;
  width: 2.15rem;
  height: 2.15rem;
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--accent-cyan) 46%, transparent);
  border-radius: 0.95rem;
  background:
    radial-gradient(circle at 50% 50%, color-mix(in srgb, var(--accent-green) 72%, transparent) 0 2px, transparent 3px),
    conic-gradient(from 90deg, color-mix(in srgb, var(--accent-cyan) 65%, transparent), color-mix(in srgb, var(--accent-green) 50%, transparent), transparent, color-mix(in srgb, var(--accent-cyan) 65%, transparent));
  box-shadow: 0 14px 32px color-mix(in srgb, var(--accent-cyan) 18%, transparent);
}
</style>
