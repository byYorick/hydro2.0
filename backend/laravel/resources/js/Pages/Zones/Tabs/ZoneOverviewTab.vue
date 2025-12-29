<template>
  <div class="space-y-4">
    <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-5">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div class="flex-1 min-w-0">
          <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">зона выращивания</p>
          <div class="flex items-center gap-3 mt-1">
            <div class="text-2xl font-semibold truncate">{{ zone.name }}</div>
            <Badge :variant="variant" class="shrink-0" data-testid="zone-status-badge">
              {{ translateStatus(zone.status) }}
            </Badge>
          </div>
          <div class="text-sm text-[color:var(--text-dim)] mt-1 space-y-1">
            <div v-if="zone.description" class="truncate">{{ zone.description }}</div>
            <div v-if="activeGrowCycle?.recipeRevision" class="flex items-center gap-2 text-xs uppercase tracking-[0.12em]">
              <span class="text-[color:var(--text-dim)]">Рецепт</span>
              <span class="text-[color:var(--accent-cyan)] font-semibold">
                {{ activeGrowCycle.recipeRevision.recipe.name }}
              </span>
              <span v-if="activeGrowCycle?.currentPhase" class="text-[color:var(--text-dim)]">
                фаза {{ activeGrowCycle.currentPhase.phase_index + 1 }}
              </span>
            </div>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 justify-end">
          <template v-if="canOperateZone">
            <Button
              size="sm"
              variant="secondary"
              @click="$emit('toggle')"
              :disabled="loading.toggle"
              class="flex-1 sm:flex-none min-w-[140px]"
              :data-testid="toggleStatus === 'PAUSED' ? 'zone-resume-btn' : 'zone-pause-btn'"
            >
              <template v-if="loading.toggle">
                <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
              </template>
              <span class="hidden sm:inline">{{ toggleStatus === 'PAUSED' ? 'Возобновить' : 'Приостановить' }}</span>
              <span class="sm:hidden">{{ toggleStatus === 'PAUSED' ? '▶' : '⏸' }}</span>
            </Button>
            <Button
              size="sm"
              variant="outline"
              @click="$emit('force-irrigation')"
              :disabled="loading.irrigate"
              class="flex-1 sm:flex-none"
              data-testid="force-irrigation-button"
            >
              <template v-if="loading.irrigate">
                <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
              </template>
              <span class="hidden sm:inline">Полить сейчас</span>
              <span class="sm:hidden">💧</span>
            </Button>
            <Button
              size="sm"
              @click="$emit('next-phase')"
              :disabled="loading.nextPhase"
              class="flex-1 sm:flex-none"
              data-testid="next-phase-button"
            >
              <template v-if="loading.nextPhase">
                <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
              </template>
              <span class="hidden sm:inline">Следующая фаза</span>
              <span class="sm:hidden">⏭</span>
            </Button>
            <Button
              v-if="!activeCycle"
              size="sm"
              class="flex-1 sm:flex-none"
              :disabled="loading.cycleConfig"
              @click="$emit('run-cycle')"
            >
              Запустить цикл выращивания
            </Button>
            <Button
              v-else
              size="sm"
              variant="outline"
              class="flex-1 sm:flex-none"
              :disabled="loading.cycleConfig"
              @click="$emit('run-cycle')"
            >
              Настройки цикла
            </Button>
            <div
              v-if="growthCycleCommandStatus"
              class="flex items-center gap-1 text-[10px] text-[color:var(--text-dim)] w-full"
            >
              <div
                class="w-1.5 h-1.5 rounded-full"
                :class="{
                  'bg-[color:var(--accent-amber)] animate-pulse': ['QUEUED', 'SENT', 'ACCEPTED', 'pending', 'executing'].includes(growthCycleCommandStatus || ''),
                  'bg-[color:var(--accent-green)]': ['DONE', 'completed', 'ack'].includes(growthCycleCommandStatus || ''),
                  'bg-[color:var(--accent-red)]': ['FAILED', 'TIMEOUT', 'SEND_FAILED', 'failed'].includes(growthCycleCommandStatus || '')
                }"
              ></div>
              <span>{{ getCommandStatusText(growthCycleCommandStatus) }}</span>
            </div>
          </template>
          <Button size="sm" variant="outline" @click="$emit('open-simulation')" class="flex-1 sm:flex-none">
            <span class="hidden sm:inline">Симуляция</span>
            <span class="sm:hidden">🧪</span>
          </Button>
        </div>
      </div>
    </section>

    <div class="space-y-4">
      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <ZoneTargets v-if="hasTargets" :telemetry="telemetry" :targets="targets" />
        <div v-else class="text-center py-6">
          <div class="text-4xl mb-2">🎯</div>
          <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
            Целевые значения не настроены
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            Настройте целевые значения для отслеживания параметров зоны
          </div>
        </div>
      </div>

      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <StageProgress
          v-if="activeGrowCycle"
          :grow-cycle="activeGrowCycle"
          :phase-progress="computedPhaseProgress"
          :phase-days-elapsed="computedPhaseDaysElapsed"
          :phase-days-total="computedPhaseDaysTotal"
          :started-at="activeGrowCycle.started_at"
        />
        <div v-else-if="activeGrowCycle || activeCycle || zone.status === 'RUNNING'" class="text-center py-6">
          <div class="text-4xl mb-2">🌱</div>
          <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
            Цикл выращивания активен
          </div>
          <div class="text-xs text-[color:var(--text-muted)] space-y-1">
            <div v-if="zone.status">
              Статус зоны: <span class="font-semibold">{{ translateStatus(zone.status) }}</span>
            </div>
            <div v-if="activeGrowCycle?.status">
              Статус цикла: <span class="font-semibold">{{ translateStatus(activeGrowCycle.status) }}</span>
            </div>
            <div v-if="activeGrowCycle?.started_at">
              Запущен: {{ formatTimeShort(new Date(activeGrowCycle.started_at)) }}
            </div>
            <div class="mt-2 text-[color:var(--text-dim)]">
              Привяжите рецепт для детального отслеживания прогресса фаз
            </div>
          </div>
        </div>
        <div v-else class="text-center py-6">
          <div class="text-4xl mb-2">🌱</div>
          <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
            Цикл выращивания не запущен
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            Привяжите рецепт и запустите цикл выращивания для отслеживания прогресса
          </div>
        </div>
      </div>

      <Card>
        <div class="flex items-center justify-between mb-2">
          <div class="text-sm font-semibold">События (последние {{ recentEvents.length }})</div>
        </div>
        <div v-if="recentEvents.length > 0" class="space-y-1 max-h-[280px] overflow-y-auto" data-testid="zone-events-list">
          <div
            v-for="e in recentEvents"
            :key="e.id"
            :data-testid="`zone-event-item-${e.id}`"
            class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-1 border-b border-[color:var(--border-muted)] last:border-0"
          >
            <Badge
              :variant="getEventVariant(e.kind)"
              class="text-xs shrink-0"
            >
              {{ translateEventKind(e.kind) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="text-xs text-[color:var(--text-dim)]">
                {{ new Date(e.occurred_at).toLocaleString('ru-RU') }}
              </div>
              <div class="text-sm">{{ e.message }}</div>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-[color:var(--text-dim)]">Нет событий</div>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import LoadingState from '@/Components/LoadingState.vue'
import StageProgress from '@/Components/StageProgress.vue'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import { translateEventKind, translateStatus } from '@/utils/i18n'
import { formatTimeShort } from '@/utils/formatTime'
import type { Zone, ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface OverviewLoadingState {
  toggle: boolean
  irrigate: boolean
  nextPhase: boolean
  cycleConfig: boolean
}

interface Props {
  zone: Zone
  variant: 'success' | 'neutral' | 'warning' | 'danger'
  activeGrowCycle?: any
  activeCycle?: any
  toggleStatus: string
  loading: OverviewLoadingState
  canOperateZone: boolean
  growthCycleCommandStatus: string | null
  targets: ZoneTargetsType
  telemetry: ZoneTelemetry
  computedPhaseProgress: number | null
  computedPhaseDaysElapsed: number | null
  computedPhaseDaysTotal: number | null
  events: ZoneEvent[]
}

defineEmits<{
  (e: 'toggle'): void
  (e: 'force-irrigation'): void
  (e: 'next-phase'): void
  (e: 'run-cycle'): void
  (e: 'open-simulation'): void
}>()

const props = defineProps<Props>()

const hasTargets = computed(() => {
  return Boolean(props.targets && (props.targets.ph || props.targets.ec || props.targets.temp || props.targets.humidity))
})

const recentEvents = computed(() => {
  return Array.isArray(props.events) ? props.events.slice(0, 5) : []
})

function getEventVariant(kind: string): 'danger' | 'warning' | 'info' | 'neutral' {
  if (kind === 'ALERT') return 'danger'
  if (kind === 'WARNING') return 'warning'
  if (kind === 'INFO') return 'info'
  return 'neutral'
}

function getCommandStatusText(status: string | null): string {
  if (!status) return ''
  const texts: Record<string, string> = {
    'QUEUED': 'В очереди',
    'SENT': 'Отправлено',
    'ACCEPTED': 'Принято',
    'DONE': 'Выполнено',
    'FAILED': 'Ошибка',
    'TIMEOUT': 'Таймаут',
    'SEND_FAILED': 'Ошибка отправки',
    'pending': 'Ожидание...',
    'executing': 'Выполняется...',
    'completed': 'Выполнено',
    'ack': 'Выполнено',
    'failed': 'Ошибка'
  }
  return texts[status] || status
}
</script>
