<template>
  <div
    class="surface-card border border-[color:var(--border-muted)] rounded-2xl flex flex-col gap-4 transition-all"
    :class="[
      dense ? 'p-3 gap-3' : 'p-4 gap-4',
      cardBorderClass,
    ]"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <div
            class="w-2 h-2 rounded-full shrink-0"
            :class="dotClass"
          ></div>
          <Link
            :href="`/zones/${zone.id}`"
            class="text-lg font-semibold truncate hover:underline text-[color:var(--text-primary)]"
          >
            {{ zone.name }}
          </Link>
          <Badge :variant="getZoneStatusVariant(zone.status)">
            {{ translateStatus(zone.status) }}
          </Badge>
          <Badge
            v-if="zone.cycle"
            :variant="getCycleStatusVariant(zone.cycle.status, 'center')"
          >
            {{ getCycleStatusLabel(zone.cycle.status, 'short') }}
          </Badge>
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1 flex flex-wrap items-center gap-2">
          <span v-if="zone.greenhouse">{{ zone.greenhouse.name }}</span>
          <span v-if="zone.crop">· {{ zone.crop }}</span>
          <span v-if="zone.devices.total">· Устр: {{ zone.devices.online }}/{{ zone.devices.total }}</span>
        </div>
      </div>
      <div
        v-if="zone.alerts_count > 0"
        class="status-chip status-chip--alarm shrink-0"
      >
        Алертов: {{ zone.alerts_count }}
      </div>
      <div
        v-else
        class="status-chip status-chip--running shrink-0"
      >
        ОК
      </div>
    </div>

    <div
      v-if="phaseStrip"
      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2 -mt-1"
    >
      <div class="flex items-center justify-between text-[10px] text-[color:var(--text-muted)] mb-1">
        <span>{{ phaseStrip.phaseName }}</span>
        <span class="tabular-nums">
          День {{ phaseStrip.dayElapsed }}/{{ phaseStrip.dayTotal }}
        </span>
      </div>
      <div class="w-full h-1 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
        <div
          class="h-full bg-[color:var(--accent-cyan)] rounded-full transition-all duration-500"
          :style="{ width: `${phaseStrip.progress}%` }"
        ></div>
      </div>
    </div>

    <div
      v-else-if="zone.cycle"
      class="space-y-2 -mt-1"
    >
      <div class="flex items-center justify-between text-xs text-[color:var(--text-muted)]">
        <span>Прогресс цикла</span>
        <span>{{ zone.cycle.progress?.overall_pct ?? 0 }}%</span>
      </div>
      <div class="h-2 rounded-full bg-[color:var(--border-muted)] overflow-hidden">
        <div
          class="h-full bg-[color:var(--accent-green)] transition-all"
          :style="{ width: `${zone.cycle.progress?.overall_pct ?? 0}%` }"
        ></div>
      </div>
    </div>

    <div
      v-else
      class="text-sm text-[color:var(--text-muted)]"
    >
      Активный цикл не запущен.
    </div>

    <div :class="dense ? 'px-0 py-0' : 'px-0 py-1'">
      <div class="flex items-start justify-around gap-1">
        <ZoneHealthGauge
          :value="zone.telemetry.ph"
          :target-min="resolveTarget('ph', 'min')"
          :target-max="resolveTarget('ph', 'max')"
          label="pH"
          :decimals="2"
        />
        <div class="w-px self-stretch bg-[color:var(--border-muted)]"></div>
        <ZoneHealthGauge
          :value="zone.telemetry.ec"
          :target-min="resolveTarget('ec', 'min')"
          :target-max="resolveTarget('ec', 'max')"
          label="EC"
          unit=" мСм"
          :decimals="2"
        />
        <div class="w-px self-stretch bg-[color:var(--border-muted)]"></div>
        <ZoneHealthGauge
          :value="zone.telemetry.temperature"
          :target-min="resolveTarget('temperature', 'min')"
          :target-max="resolveTarget('temperature', 'max')"
          :global-min="10"
          :global-max="40"
          label="T°C"
          :decimals="1"
        />
      </div>

      <div
        v-if="sparklineData?.length"
        :class="dense ? 'mt-2' : 'mt-3'"
      >
        <div class="text-[9px] text-[color:var(--text-dim)] mb-1 uppercase tracking-wider">
          pH · 24 часа
        </div>
        <Sparkline
          :data="sparklineData"
          :width="dense ? 200 : 240"
          :height="dense ? 24 : 28"
          :color="sparklineColor"
          :show-area="true"
          :stroke-width="1.5"
        />
      </div>

      <div :class="dense ? 'mt-2' : 'mt-2'">
        <ZoneAIPredictionHint
          :zone-id="zone.id"
          metric-type="PH"
          :target-min="resolveTarget('ph', 'min')"
          :target-max="resolveTarget('ph', 'max')"
          :horizon-minutes="90"
        />
      </div>
    </div>

    <div
      v-if="zone.alerts_preview.length"
      class="space-y-1 text-xs text-[color:var(--text-dim)]"
    >
      <div class="font-semibold text-[color:var(--text-primary)]">
        Последние алерты
      </div>
      <div
        v-for="alert in zone.alerts_preview"
        :key="alert.id"
        class="flex items-center justify-between gap-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2 py-1"
      >
        <span class="truncate">{{ alert.type }}</span>
        <span class="text-[10px] shrink-0">{{ formatTime(alert.created_at) }}</span>
      </div>
    </div>

    <div class="flex flex-wrap gap-2 pt-1 border-t border-[color:var(--border-muted)]">
      <template v-if="zone.cycle">
        <Button
          v-if="canManageCycle && zone.cycle.status === 'RUNNING'"
          size="sm"
          variant="secondary"
          :disabled="isActionLoading(zone.id, 'pause')"
          @click="$emit('pause', zone)"
        >
          {{ isActionLoading(zone.id, 'pause') ? 'Пауза...' : 'Пауза' }}
        </Button>
        <Button
          v-else-if="canManageCycle && zone.cycle.status === 'PAUSED'"
          size="sm"
          variant="secondary"
          :disabled="isActionLoading(zone.id, 'resume')"
          @click="$emit('resume', zone)"
        >
          {{ isActionLoading(zone.id, 'resume') ? 'Запуск...' : 'Возобновить' }}
        </Button>
        <Button
          v-if="canIssueCommands"
          size="sm"
          variant="secondary"
          @click="$emit('irrigate', zone)"
        >
          Полив
        </Button>
        <Button
          v-if="canIssueCommands"
          size="sm"
          variant="outline"
          @click="$emit('flush', zone)"
        >
          Промывка
        </Button>
        <Button
          v-if="canManageCycle"
          size="sm"
          variant="secondary"
          :disabled="isActionLoading(zone.id, 'harvest')"
          @click="$emit('harvest', zone)"
        >
          {{ isActionLoading(zone.id, 'harvest') ? 'Фиксация...' : 'Сбор' }}
        </Button>
        <Button
          v-if="canManageCycle"
          size="sm"
          variant="outline"
          :disabled="isActionLoading(zone.id, 'abort')"
          @click="$emit('abort', zone)"
        >
          Стоп
        </Button>
      </template>
      <template v-else-if="canManageCycle && !zone.cycle">
        <Button
          size="sm"
          @click="router.visit('/grow-cycle-wizard')"
        >
          Запустить цикл
        </Button>
      </template>
      <Button
        size="sm"
        variant="ghost"
        @click="router.visit(`/zones/${zone.id}`)"
      >
        Детали зоны
      </Button>
    </div>

    <div
      v-if="zone.telemetry.updated_at"
      class="text-[11px] text-[color:var(--text-dim)]"
    >
      Обновление: {{ formatTime(zone.telemetry.updated_at) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Sparkline from '@/Components/Sparkline.vue'
import ZoneHealthGauge from '@/Components/ZoneHealthGauge.vue'
import ZoneAIPredictionHint from '@/Components/ZoneAIPredictionHint.vue'
import { translateStatus } from '@/utils/i18n'
import { getCycleStatusLabel, getCycleStatusVariant } from '@/utils/growCycleStatus'
import type { UnifiedZone } from '@/composables/useUnifiedDashboard'
import type { GrowCycle } from '@/composables/useCycleCenterView'

interface PhaseStrip {
  phaseName: string
  dayElapsed: number
  dayTotal: number
  progress: number
}

const props = defineProps<{
  zone: UnifiedZone
  canManageCycle: boolean
  canIssueCommands: boolean
  sparklineData: number[] | null
  sparklineColor: string
  isActionLoading: (zoneId: number, action: string) => boolean
  dense?: boolean
}>()

defineEmits<{
  pause: [zone: UnifiedZone]
  resume: [zone: UnifiedZone]
  irrigate: [zone: UnifiedZone]
  flush: [zone: UnifiedZone]
  harvest: [zone: UnifiedZone]
  abort: [zone: UnifiedZone]
}>()

function getZoneStatusVariant(status: string): 'success' | 'info' | 'warning' | 'danger' | 'neutral' {
  switch (status) {
    case 'RUNNING':
      return 'success'
    case 'PAUSED':
      return 'info'
    case 'WARNING':
      return 'warning'
    case 'ALARM':
      return 'danger'
    default:
      return 'neutral'
  }
}

function resolveTarget(
  key: 'ph' | 'ec' | 'temperature',
  side: 'min' | 'max',
): number | null {
  const t = props.zone.targets[key]
  if (!t) {
    return null
  }
  return t[side]
}

const phaseStrip = computed((): PhaseStrip | null => {
  const cycle = props.zone.cycle as GrowCycle | null
  if (!cycle?.stages?.length) {
    return null
  }
  const active = cycle.stages.find(s => s.state === 'ACTIVE')
  if (!active?.from) {
    return null
  }
  const start = new Date(active.from)
  if (Number.isNaN(start.getTime())) {
    return null
  }
  const end = active.to ? new Date(active.to) : null
  const daysElapsed = Math.max(0, Math.floor((Date.now() - start.getTime()) / (1000 * 60 * 60 * 24)))
  let daysTotal = daysElapsed || 1
  if (end && !Number.isNaN(end.getTime())) {
    daysTotal = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)))
  }
  const progress = Math.min(100, Math.round((daysElapsed / daysTotal) * 100))
  const stageName = cycle.current_stage?.name ?? active.name ?? 'Фаза'
  return {
    phaseName: stageName,
    dayElapsed: daysElapsed,
    dayTotal: daysTotal,
    progress,
  }
})

const cardBorderClass = computed(() => {
  if (props.zone.status === 'ALARM') {
    return 'border-[color:var(--badge-danger-border)]'
  }
  if (props.zone.status === 'WARNING') {
    return 'border-[color:var(--badge-warning-border)]'
  }
  return 'border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)]'
})

const dotClass = computed(() => {
  const map: Record<string, string> = {
    RUNNING: 'bg-[color:var(--accent-green)] shadow-[0_0_6px_var(--accent-green)]',
    WARNING: 'bg-[color:var(--accent-amber)]',
    ALARM: 'bg-[color:var(--accent-red)] animate-pulse',
    PAUSED: 'bg-[color:var(--text-dim)]',
    IDLE: 'bg-[color:var(--text-dim)]',
    NEW: 'bg-[color:var(--text-dim)]',
  }
  return map[props.zone.status] ?? 'bg-[color:var(--text-dim)]'
})

function formatTime(value: string | null | undefined): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>
