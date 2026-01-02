<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
    <div class="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
      <div class="space-y-2">
        <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
          Цикл выращивания
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Badge :variant="statusVariant">
            {{ statusLabel }}
          </Badge>
          <span class="text-xs text-[color:var(--text-dim)]">{{ phaseLabel }}</span>
          <span class="text-xs text-[color:var(--text-dim)]">·</span>
          <span class="text-xs text-[color:var(--text-dim)]">Сбор: {{ expectedHarvestLabel }}</span>
        </div>
      </div>
      <div class="flex flex-wrap gap-2">
        <template v-if="hasActiveGrowCycle && canManageCycle">
          <Button
            size="sm"
            variant="secondary"
            :disabled="loading.cyclePause || loading.cycleResume"
            @click="onPauseResume"
          >
            <template v-if="loading.cyclePause || loading.cycleResume">
              <LoadingState
                loading
                size="sm"
                :container-class="'inline-flex mr-2'"
              />
            </template>
            {{ pauseResumeLabel }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="loading.nextPhase"
            @click="$emit('next-phase')"
          >
            <template v-if="loading.nextPhase">
              <LoadingState
                loading
                size="sm"
                :container-class="'inline-flex mr-2'"
              />
            </template>
            Следующая фаза
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="loading.cycleHarvest"
            @click="$emit('harvest')"
          >
            <template v-if="loading.cycleHarvest">
              <LoadingState
                loading
                size="sm"
                :container-class="'inline-flex mr-2'"
              />
            </template>
            Сбор
          </Button>
          <Button
            size="sm"
            variant="danger"
            :disabled="loading.cycleAbort"
            @click="$emit('abort')"
          >
            <template v-if="loading.cycleAbort">
              <LoadingState
                loading
                size="sm"
                :container-class="'inline-flex mr-2'"
              />
            </template>
            Аварийная остановка
          </Button>
        </template>
        <div
          v-else-if="hasActiveGrowCycle"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Недостаточно прав для управления циклом
        </div>
        <div
          v-else
          class="text-xs text-[color:var(--text-dim)]"
        >
          Нет активного цикла для действий
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import LoadingState from '@/Components/LoadingState.vue'
import { formatTimeShort } from '@/utils/formatTime'

interface LoadingStateProps {
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  nextPhase: boolean
}

interface Props {
  statusLabel: string
  statusVariant: 'success' | 'neutral' | 'warning'
  activeGrowCycleStatus?: string | null
  currentPhase?: { phase_index?: number; name?: string } | null
  expectedHarvestAt?: string | null
  canManageCycle: boolean
  loading: LoadingStateProps
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'harvest'): void
  (e: 'abort'): void
  (e: 'next-phase'): void
}>()

const hasActiveGrowCycle = computed(() => Boolean(props.activeGrowCycleStatus))

const pauseResumeLabel = computed(() => {
  return props.activeGrowCycleStatus === 'PAUSED' ? 'Возобновить' : 'Пауза'
})

const phaseLabel = computed(() => {
  if (!props.currentPhase) return 'Фаза не определена'
  const index = typeof props.currentPhase.phase_index === 'number'
    ? `Фаза ${props.currentPhase.phase_index + 1}`
    : 'Фаза'
  const name = props.currentPhase.name ? ` — ${props.currentPhase.name}` : ''
  return `${index}${name}`
})

const expectedHarvestLabel = computed(() => {
  if (!props.expectedHarvestAt) return 'не указан'
  return formatTimeShort(new Date(props.expectedHarvestAt))
})

const onPauseResume = (): void => {
  if (props.activeGrowCycleStatus === 'PAUSED') {
    emit('resume')
  } else {
    emit('pause')
  }
}
</script>
