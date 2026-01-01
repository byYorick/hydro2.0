<template>
  <Card class="hover:border-[color:var(--border-strong)] transition-all duration-200">
    <div class="space-y-4">
      <!-- Заголовок -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 flex-1 min-w-0">
          <h3 class="text-sm font-semibold truncate">{{ zone.name }}</h3>
          <Badge :variant="statusVariant">{{ translateStatus(zone.status) }}</Badge>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <!-- Индикатор узлов -->
          <div class="flex items-center gap-1 text-xs text-[color:var(--text-muted)]">
            <div class="w-2 h-2 rounded-full" :class="nodesOnline > 0 ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--text-dim)]'"></div>
            <span>{{ nodesOnline }}/{{ nodesTotal }}</span>
          </div>
        </div>
      </div>

      <!-- Стадия и прогресс -->
      <div v-if="zone.stage" class="space-y-3">
        <!-- Бейдж стадии -->
        <div class="flex items-center justify-between">
          <GrowCycleStageHeader :stage="zone.stage.id" />
          
          <!-- Прогресс цикла (кольцо) -->
          <GrowCycleProgressRing
            v-if="zone.cycle_progress !== null"
            :progress="zone.cycle_progress"
            :size="60"
            :stroke-width="6"
          />
        </div>

        <!-- Прогресс-бары -->
        <div v-if="zone.cycle_progress !== null" class="space-y-2">
          <!-- Общий прогресс -->
          <div>
            <div class="flex items-center justify-between text-xs mb-1">
              <span class="text-[color:var(--text-muted)]">Прогресс цикла</span>
              <span class="font-semibold text-[color:var(--accent-cyan)]">{{ Math.round(zone.cycle_progress ?? 0) }}%</span>
            </div>
            <div class="relative w-full h-2 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
              <div
                class="absolute inset-0 bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] rounded-full transition-all duration-500"
                :style="{ width: `${zone.cycle_progress}%` }"
              ></div>
            </div>
          </div>

          <!-- Прогресс текущей фазы -->
          <div v-if="zone.current_phase">
            <div class="flex items-center justify-between text-xs mb-1">
              <span class="text-[color:var(--text-muted)]">{{ zone.current_phase.name }}</span>
              <span class="font-medium text-[color:var(--text-primary)]">
                Фаза {{ zone.current_phase.index + 1 }}
              </span>
            </div>
            <div class="relative w-full h-1.5 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
              <div
                class="absolute inset-0 bg-[linear-gradient(90deg,var(--accent-green),var(--accent-cyan))] rounded-full transition-all duration-500"
                :style="{ width: `${Math.min(100, (zone.current_phase.progress / (zone.current_phase.progress + 1)) * 100)}%` }"
              ></div>
            </div>
          </div>
        </div>

        <!-- ETA -->
        <div v-if="zone.eta_to_next_stage || zone.eta_to_harvest" class="flex items-center gap-4 text-xs text-[color:var(--text-muted)]">
          <div v-if="zone.eta_to_next_stage" class="flex items-center gap-1">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>След. стадия: {{ formatEta(zone.eta_to_next_stage) }}</span>
          </div>
          <div v-if="zone.eta_to_harvest" class="flex items-center gap-1">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Сбор: {{ formatEta(zone.eta_to_harvest) }}</span>
          </div>
        </div>
      </div>

      <!-- Мини-метрики -->
      <div v-if="zone.telemetry" class="pt-2 border-t border-[color:var(--border-muted)]">
        <ZoneMiniMetrics
          :telemetry="zone.telemetry"
          :targets="zone.targets"
        />
      </div>

      <!-- Активные алерты (топ-2) -->
      <div v-if="zone.alerts && zone.alerts.length > 0" class="pt-2 border-t border-[color:var(--border-muted)]">
        <div class="flex items-center justify-between text-xs mb-2">
          <span class="font-semibold text-[color:var(--text-primary)]">Алерты</span>
          <span v-if="(zone.alerts_count ?? 0) > zone.alerts.length" class="text-[color:var(--text-dim)]">
            +{{ (zone.alerts_count ?? 0) - zone.alerts.length }} еще
          </span>
        </div>
        <div class="space-y-1.5">
          <div
            v-for="alert in zone.alerts"
            :key="alert.id"
            class="flex items-start gap-2 p-2 rounded bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
          >
            <svg class="w-4 h-4 text-[color:var(--accent-red)] shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
            <div class="flex-1 min-w-0">
              <div class="text-xs font-medium text-[color:var(--accent-red)]">{{ alert.type || 'Алерт' }}</div>
              <div v-if="alert.details" class="text-[10px] text-[color:var(--text-muted)] mt-0.5 truncate">
                {{ formatAlertDetails(alert.details) }}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="(zone.alerts_count ?? 0) > 0" class="pt-2 border-t border-[color:var(--border-muted)]">
        <div class="text-xs text-[color:var(--text-muted)]">{{ zone.alerts_count ?? 0 }} алерт(ов)</div>
      </div>

      <!-- Футер с рецептом -->
      <div v-if="zone.recipe" class="pt-2 border-t border-[color:var(--border-muted)] flex items-center justify-between">
        <div class="text-xs text-[color:var(--text-muted)]">
          Рецепт: <span class="text-[color:var(--text-primary)]">{{ zone.recipe.name }}</span>
        </div>
        <Link
          :href="`/zones/${zone.id}`"
          class="text-xs text-[color:var(--accent-cyan)] hover:text-[color:var(--accent-green)] transition-colors"
        >
          Подробнее →
        </Link>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from './Card.vue'
import Badge from './Badge.vue'
import GrowCycleStageHeader from './GrowCycleStageHeader.vue'
import GrowCycleProgressRing from './GrowCycleProgressRing.vue'
import ZoneMiniMetrics from './ZoneMiniMetrics.vue'
import { translateStatus } from '@/utils/i18n'
import type { GrowStage } from '@/utils/growStages'

interface ZoneAlert {
  id: number
  type: string
  code?: string
  details?: any
  created_at?: string
}

interface ZonePhase {
  index: number
  name: string
  progress: number
}

interface ZoneData {
  id: number
  name: string
  status: string
  telemetry?: {
    ph?: number | null
    ec?: number | null
    temperature?: number | null
    humidity?: number | null
    co2?: number | null
  } | null
  targets?: any
  stage?: {
    id: GrowStage
    label: string
  }
  cycle_progress?: number | null
  current_phase?: ZonePhase | null
  eta_to_next_stage?: string | null
  eta_to_harvest?: string | null
  alerts?: ZoneAlert[]
  alerts_count?: number
  nodes_online?: number
  nodes_total?: number
  recipe?: {
    id: number
    name: string
  } | null
}

interface Props {
  zone: ZoneData
}

const props = defineProps<Props>()

const statusVariant = computed<'success' | 'warning' | 'danger' | 'neutral' | 'info'>(() => {
  switch (props.zone.status) {
    case 'RUNNING': return 'success'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    case 'PAUSED': return 'neutral'
    default: return 'neutral'
  }
})

const nodesOnline = computed(() => props.zone.nodes_online ?? 0)
const nodesTotal = computed(() => props.zone.nodes_total ?? 0)

function formatEta(dateString: string | null | undefined): string {
  if (!dateString) return '—'
  
  try {
    const date = new Date(dateString)
    if (isNaN(date.getTime())) return '—'
    
    const now = new Date()
    const diffMs = date.getTime() - now.getTime()
    
    if (diffMs <= 0) return 'уже наступило'
    
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    
    if (diffDays > 0) {
      return `через ${diffDays} дн.`
    }
    if (diffHours > 0) {
      return `через ${diffHours} ч.`
    }
    
    const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
    return `через ${diffMinutes} мин.`
  } catch {
    return '—'
  }
}

function formatAlertDetails(details: any): string {
  if (typeof details === 'string') {
    return details
  }
  if (typeof details === 'object' && details !== null) {
    return JSON.stringify(details)
  }
  return String(details || '')
}
</script>
