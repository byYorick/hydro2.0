<template>
  <div
    v-if="cycle"
    class="space-y-4"
    data-testid="cycle-control-panel"
  >
    <!-- Информация о цикле и текущая стадия -->
    <Card>
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold">
            Управление циклом
          </div>
          <Badge
            :variant="getCycleStatusVariant(cycle.status)"
            data-testid="cycle-status-badge"
          >
            {{ getCycleStatusLabel(cycle.status) }}
          </Badge>
        </div>

        <!-- Timeline стадий -->
        <StageProgress
          v-if="growCycle || recipeInstance"
          :grow-cycle="growCycle"
          :recipe-instance="recipeInstance as any"
          :phase-progress="phaseProgress"
          :phase-days-elapsed="phaseDaysElapsed"
          :phase-days-total="phaseDaysTotal"
          :started-at="cycle.started_at"
        />

        <!-- Мета-информация о цикле -->
        <div class="grid grid-cols-2 gap-3 pt-3 border-t border-[color:var(--border-muted)] text-xs">
          <div>
            <div class="text-[color:var(--text-dim)] mb-1">
              Запущен
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ cycle.started_at ? formatDateTime(cycle.started_at) : 'Не запущен' }}
            </div>
          </div>
          <div v-if="cycle.expected_harvest_at">
            <div class="text-[color:var(--text-dim)] mb-1">
              Ожидаемый сбор
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ formatDateTime(cycle.expected_harvest_at) }}
            </div>
          </div>
          <div v-if="cycle.current_stage_code">
            <div class="text-[color:var(--text-dim)] mb-1">
              Текущая стадия
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ cycle.current_stage_code }}
            </div>
          </div>
          <div v-if="cycle.batch_label">
            <div class="text-[color:var(--text-dim)] mb-1">
              Партия
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ cycle.batch_label }}
            </div>
          </div>
        </div>
      </div>
    </Card>

    <!-- Кнопки управления -->
    <CycleActionsPanel
      v-if="canManage"
      :status="cycle.status"
      :loading="loading"
      :loading-next-phase="loadingNextPhase"
      @pause="$emit('pause')"
      @resume="$emit('resume')"
      @harvest="$emit('harvest')"
      @abort="$emit('abort')"
      @next-phase="$emit('next-phase')"
    />

    <!-- Журнал событий цикла -->
    <CycleEventLog
      :zone-id="cycle.zone_id"
      :phase-id="cycle.current_phase_id ?? cycle.currentPhase?.id"
    />
  </div>
</template>

<script setup lang="ts">
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import StageProgress from '@/Components/StageProgress.vue'
import CycleActionsPanel from './CycleActionsPanel.vue'
import CycleEventLog from './CycleEventLog.vue'
import { getCycleStatusLabel, getCycleStatusVariant } from '@/utils/growCycleStatus'
import type { GrowCycle, GrowCycleStatus } from '@/types/GrowCycle'

interface CycleInfo {
  id: number
  zone_id: number
  status: GrowCycleStatus
  current_phase_id?: number | null
  currentPhase?: { id?: number | null } | null
  current_stage_code?: string | null
  started_at?: string | null
  expected_harvest_at?: string | null
  batch_label?: string | null
}

interface RecipeInstance {
  current_phase_index?: number | null
  recipe?: {
    id: number
    name: string
    phases?: unknown[]
  } | null
}

interface Props {
  cycle: CycleInfo | null
  growCycle?: GrowCycle | null
  recipeInstance?: RecipeInstance | null
  phaseProgress?: number | null
  phaseDaysElapsed?: number | null
  phaseDaysTotal?: number | null
  canManage?: boolean
  loading?: boolean
  loadingNextPhase?: boolean
}

withDefaults(defineProps<Props>(), {
  growCycle: null,
  recipeInstance: null,
  phaseProgress: null,
  phaseDaysElapsed: null,
  phaseDaysTotal: null,
  canManage: false,
  loading: false,
  loadingNextPhase: false,
})

defineEmits<{
  pause: []
  resume: []
  harvest: []
  abort: []
  'next-phase': []
}>()

function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  try {
    return new Date(dateStr).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}
</script>
