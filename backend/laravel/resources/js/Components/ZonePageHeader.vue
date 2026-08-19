<template>
  <header
    class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"
    data-testid="zone-page-header"
  >
    <div class="min-w-0 space-y-1.5">
      <div class="flex flex-wrap items-center gap-2">
        <h1
          class="truncate text-lg font-bold text-[color:var(--text-primary)]"
          data-testid="zone-page-header-title"
        >
          {{ zoneName }}
        </h1>
        <Badge
          :variant="statusVariant"
          data-testid="zone-page-header-status"
        >
          {{ statusLabel }}
        </Badge>
      </div>
      <div
        v-if="cropLabel || phaseLabel || daysLabel"
        class="flex flex-wrap items-center gap-1.5 text-xs text-[color:var(--text-muted)]"
      >
        <span
          v-if="cropLabel"
          data-testid="zone-page-header-crop"
        >{{ cropLabel }}</span>
        <span
          v-if="cropLabel && phaseLabel"
          class="text-[color:var(--border-strong)]"
        >&middot;</span>
        <span
          v-if="phaseLabel"
          data-testid="zone-page-header-phase"
        >{{ phaseLabel }}</span>
        <span
          v-if="(cropLabel || phaseLabel) && daysLabel"
          class="text-[color:var(--border-strong)]"
        >&middot;</span>
        <span
          v-if="daysLabel"
          data-testid="zone-page-header-days"
        >{{ daysLabel }}</span>
      </div>
    </div>
    <div
      v-if="hasActions"
      class="flex flex-wrap items-center gap-1.5"
    >
      <Button
        v-if="showWater"
        size="sm"
        variant="primary"
        type="button"
        data-testid="zone-header-water"
        @click="$emit('water')"
      >
        Полить
      </Button>
      <Button
        v-if="showPause"
        size="sm"
        variant="outline"
        type="button"
        :disabled="pauseLoading"
        data-testid="zone-header-pause"
        @click="$emit('pause')"
      >
        Пауза
      </Button>
      <Button
        v-if="showNextPhase"
        size="sm"
        variant="outline"
        type="button"
        :disabled="nextPhaseLoading"
        data-testid="zone-header-next-phase"
        @click="$emit('next-phase')"
      >
        Следующая фаза
      </Button>
      <Button
        v-if="showActions"
        size="sm"
        variant="secondary"
        type="button"
        data-testid="zone-header-actions"
        @click="$emit('open-actions')"
      >
        Действия
      </Button>
      <Button
        v-if="showDiagnose"
        size="sm"
        variant="outline"
        type="button"
        data-testid="zone-header-diagnose"
        @click="$emit('diagnose')"
      >
        Диагностика
      </Button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import { useRole } from '@/composables/useRole'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { GrowCycleStatus } from '@/types/GrowCycle'

interface Props {
  zoneName: string
  cropLabel?: string | null
  phaseLabel?: string | null
  phaseDaysElapsed?: number | null
  phaseDaysTotal?: number | null
  statusLabel: string
  statusVariant: BadgeVariant
  cycleStatus?: GrowCycleStatus | string | null
  canOperateZone: boolean
  canManageCycle: boolean
  pauseLoading?: boolean
  nextPhaseLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  cropLabel: null,
  phaseLabel: null,
  phaseDaysElapsed: null,
  phaseDaysTotal: null,
  cycleStatus: null,
  pauseLoading: false,
  nextPhaseLoading: false,
})

defineEmits<{
  water: []
  pause: []
  'next-phase': []
  'open-actions': []
  diagnose: []
}>()

const { isOperator, isAgronomist, isEngineer, isAdmin, canOperateCycles } = useRole()

const daysLabel = computed(() => {
  if (props.phaseDaysElapsed == null && props.phaseDaysTotal == null) {
    return null
  }
  const elapsed = props.phaseDaysElapsed == null ? '—' : String(props.phaseDaysElapsed)
  const total = props.phaseDaysTotal == null ? '—' : String(props.phaseDaysTotal)
  return `День ${elapsed}/${total}`
})

const cycleIsRunning = computed(() => props.cycleStatus === 'RUNNING')
const cycleIsActive = computed(() =>
  props.cycleStatus === 'RUNNING' || props.cycleStatus === 'PAUSED',
)

const showWater = computed(() =>
  isOperator.value && props.canOperateZone && canOperateCycles.value,
)

const showPause = computed(() => {
  if (!cycleIsRunning.value) {
    return false
  }
  if (isOperator.value && props.canOperateZone && canOperateCycles.value) {
    return true
  }
  if ((isAgronomist.value || isAdmin.value) && props.canManageCycle) {
    return true
  }
  return false
})

const showNextPhase = computed(() =>
  isAgronomist.value && props.canManageCycle && cycleIsActive.value,
)

const showActions = computed(() =>
  isOperator.value && props.canOperateZone && canOperateCycles.value,
)

const showDiagnose = computed(() => isEngineer.value)

const hasActions = computed(() =>
  showWater.value
    || showPause.value
    || showNextPhase.value
    || showActions.value
    || showDiagnose.value,
)
</script>
