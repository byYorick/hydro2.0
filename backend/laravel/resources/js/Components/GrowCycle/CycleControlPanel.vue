<template>
  <div v-if="cycle" class="space-y-4">
    <!-- Информация о цикле и текущая стадия -->
    <Card>
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold">Управление циклом</div>
          <Badge :variant="getCycleStatusVariant(cycle.status)">
            {{ getCycleStatusLabel(cycle.status) }}
          </Badge>
        </div>

        <!-- Timeline стадий -->
        <StageProgress
          v-if="recipeInstance"
          :recipe-instance="recipeInstance"
          :phase-progress="phaseProgress"
          :phase-days-elapsed="phaseDaysElapsed"
          :phase-days-total="phaseDaysTotal"
          :started-at="cycle.started_at"
        />

        <!-- Информация о цикле -->
        <div class="grid grid-cols-2 gap-3 pt-3 border-t border-neutral-800 text-xs">
          <div>
            <div class="text-neutral-400 mb-1">Запущен</div>
            <div class="text-neutral-200">
              {{ cycle.started_at ? formatDateTime(cycle.started_at) : 'Не запущен' }}
            </div>
          </div>
          <div v-if="cycle.expected_harvest_at">
            <div class="text-neutral-400 mb-1">Ожидаемый сбор</div>
            <div class="text-neutral-200">
              {{ formatDateTime(cycle.expected_harvest_at) }}
            </div>
          </div>
          <div v-if="cycle.current_stage_code">
            <div class="text-neutral-400 mb-1">Текущая стадия</div>
            <div class="text-neutral-200">{{ cycle.current_stage_code }}</div>
          </div>
          <div v-if="cycle.batch_label">
            <div class="text-neutral-400 mb-1">Партия</div>
            <div class="text-neutral-200">{{ cycle.batch_label }}</div>
          </div>
        </div>
      </div>
    </Card>

    <!-- Кнопки управления -->
    <Card v-if="canManage">
      <div class="space-y-3">
        <div class="text-sm font-semibold mb-2">Действия</div>
        <div class="flex flex-wrap gap-2">
          <Button
            v-if="cycle.status === 'RUNNING'"
            size="sm"
            variant="secondary"
            @click="$emit('pause')"
            :disabled="loading"
          >
            <template v-if="loading">
              <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
            </template>
            Приостановить
          </Button>
          
          <Button
            v-if="cycle.status === 'PAUSED'"
            size="sm"
            variant="secondary"
            @click="$emit('resume')"
            :disabled="loading"
          >
            <template v-if="loading">
              <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
            </template>
            Возобновить
          </Button>

          <Button
            v-if="cycle.status === 'RUNNING' || cycle.status === 'PAUSED'"
            size="sm"
            variant="success"
            @click="$emit('harvest')"
            :disabled="loading"
          >
            <template v-if="loading">
              <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
            </template>
            Собрать урожай
          </Button>

          <Button
            v-if="cycle.status === 'RUNNING' || cycle.status === 'PAUSED'"
            size="sm"
            variant="danger"
            @click="$emit('abort')"
            :disabled="loading"
          >
            <template v-if="loading">
              <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
            </template>
            Аварийная остановка
          </Button>
        </div>
      </div>
    </Card>

    <!-- Журнал событий цикла -->
    <Card>
      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold">События цикла</div>
          <Button
            size="sm"
            variant="outline"
            @click="loadEvents"
            :disabled="loadingEvents"
          >
            <template v-if="loadingEvents">
              <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
            </template>
            Обновить
          </Button>
        </div>
        
        <div v-if="events.length > 0" class="space-y-1 max-h-[400px] overflow-y-auto">
          <div
            v-for="event in events"
            :key="event.id"
            class="text-sm text-neutral-300 flex items-start gap-2 py-2 px-2 rounded border border-neutral-800 hover:border-neutral-700 transition-colors"
          >
            <Badge
              :variant="getEventVariant(event.type)"
              class="text-xs shrink-0"
            >
              {{ getEventTypeLabel(event.type) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="text-xs text-neutral-400 mb-1">
                {{ formatDateTime(event.created_at || event.occurred_at) }}
              </div>
              <div class="text-sm">{{ getEventMessage(event) }}</div>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-neutral-400 text-center py-4">
          Нет событий цикла
        </div>
      </div>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch, ref } from 'vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import LoadingState from '@/Components/LoadingState.vue'
import StageProgress from '@/Components/StageProgress.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { logger } from '@/utils/logger'

interface GrowCycle {
  id: number
  zone_id: number
  status: string
  current_stage_code?: string | null
  current_stage_started_at?: string | null
  started_at?: string | null
  expected_harvest_at?: string | null
  actual_harvest_at?: string | null
  batch_label?: string | null
  notes?: string | null
}

interface ZoneEvent {
  id: number | string
  type: string
  details?: any
  payload?: any
  created_at?: string
  occurred_at?: string
}

interface RecipeInstance {
  current_phase_index?: number | null
  recipe?: {
    id: number
    name: string
    phases?: any[]
  } | null
}

interface Props {
  cycle: GrowCycle | null
  recipeInstance?: RecipeInstance | null
  phaseProgress?: number | null
  phaseDaysElapsed?: number | null
  phaseDaysTotal?: number | null
  canManage?: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  cycle: null,
  recipeInstance: null,
  phaseProgress: null,
  phaseDaysElapsed: null,
  phaseDaysTotal: null,
  canManage: false,
  loading: false,
})

const emit = defineEmits<{
  pause: []
  resume: []
  harvest: []
  abort: []
}>()

const { api } = useApi()
const { showToast } = useToast()
const events = ref<ZoneEvent[]>([])
const loadingEvents = ref(false)

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

function getCycleStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    PLANNED: 'Запланирован',
    RUNNING: 'Запущен',
    PAUSED: 'Приостановлен',
    HARVESTED: 'Собран',
    ABORTED: 'Прерван',
  }
  return labels[status] || status
}

function getCycleStatusVariant(status: string): 'success' | 'neutral' | 'warning' | 'danger' {
  const variants: Record<string, 'success' | 'neutral' | 'warning' | 'danger'> = {
    PLANNED: 'neutral',
    RUNNING: 'success',
    PAUSED: 'warning',
    HARVESTED: 'success',
    ABORTED: 'danger',
  }
  return variants[status] || 'neutral'
}

function getEventVariant(type: string): 'success' | 'neutral' | 'warning' | 'danger' {
  if (type.includes('HARVESTED') || type.includes('STARTED') || type.includes('RESUMED')) {
    return 'success'
  }
  if (type.includes('ABORTED') || type.includes('CRITICAL')) {
    return 'danger'
  }
  if (type.includes('PAUSED') || type.includes('WARNING')) {
    return 'warning'
  }
  return 'neutral'
}

function getEventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    CYCLE_CREATED: 'Создан цикл',
    CYCLE_STARTED: 'Запущен цикл',
    CYCLE_PAUSED: 'Приостановлен',
    CYCLE_RESUMED: 'Возобновлен',
    CYCLE_HARVESTED: 'Собран урожай',
    CYCLE_ABORTED: 'Прерван',
    CYCLE_RECIPE_REBASED: 'Рецепт изменен',
    PHASE_TRANSITION: 'Смена фазы',
    RECIPE_PHASE_CHANGED: 'Изменена фаза',
    ZONE_COMMAND: 'Ручное вмешательство',
    ALERT_CREATED: 'Критическое предупреждение',
  }
  return labels[type] || type
}

function getEventMessage(event: ZoneEvent): string {
  const details = event.details || event.payload || {}
  const type = event.type

  if (type === 'CYCLE_HARVESTED') {
    return `Урожай собран${details.batch_label ? ` (партия: ${details.batch_label})` : ''}`
  }
  if (type === 'CYCLE_ABORTED') {
    return `Цикл прерван${details.reason ? `: ${details.reason}` : ''}`
  }
  if (type === 'PHASE_TRANSITION' || type === 'RECIPE_PHASE_CHANGED') {
    return `Фаза ${details.from_phase ?? ''} → ${details.to_phase ?? ''}`
  }
  if (type === 'ZONE_COMMAND') {
    return `Ручное вмешательство: ${details.command_type || 'команда'}`
  }
  if (type === 'ALERT_CREATED') {
    return `Критическое предупреждение: ${details.message || details.code || 'alert'}`
  }

  return getEventTypeLabel(type)
}

async function loadEvents(): Promise<void> {
  if (!props.cycle?.zone_id) {
    events.value = []
    return
  }

  loadingEvents.value = true
  try {
    const response = await api.get(`/api/zones/${props.cycle.zone_id}/events`, {
      params: {
        cycle_only: true,
        entity_type: 'grow_cycle',
        entity_id: props.cycle.id,
        limit: 50,
      },
    })

    if (response.data?.status === 'ok' && Array.isArray(response.data.data)) {
      events.value = response.data.data.map((e: any) => ({
        id: e.event_id || e.id,
        type: e.type,
        details: e.details || e.payload_json ? JSON.parse(e.payload_json || '{}') : {},
        payload: e.payload || e.payload_json ? JSON.parse(e.payload_json || '{}') : {},
        created_at: e.created_at,
        occurred_at: e.created_at,
      })).reverse() // Показываем последние события первыми
    }
  } catch (err) {
    logger.error('Failed to load cycle events:', err)
    showToast('Ошибка загрузки событий цикла', 'error')
    events.value = []
  } finally {
    loadingEvents.value = false
  }
}

// Загружаем события при монтировании и при изменении цикла
onMounted(() => {
  if (props.cycle) {
    loadEvents()
  }
})

watch(() => props.cycle?.id, (newCycleId) => {
  if (newCycleId) {
    loadEvents()
  } else {
    events.value = []
  }
})
</script>

