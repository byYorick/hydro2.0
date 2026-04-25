<template>
  <div class="grid gap-3 lg:[grid-template-columns:1fr_320px] items-start">
    <div class="flex flex-col gap-3 min-w-0">
      <PidConfigForm
        :zone-id="zoneId"
        :phase-targets="phaseTargets"
        @saved="$emit('saved')"
      />
      <RelayAutotuneTrigger :zone-id="zoneId" />
    </div>
    <div class="flex flex-col gap-3">
      <ShellCard
        title="Зона регулирования"
        :pad="false"
      >
        <PidChart
          v-if="pidChartParams"
          :target="pidChartParams.target"
          :dead="pidChartParams.dead"
          :close="pidChartParams.close"
          :far="pidChartParams.far"
          axis-label="pH"
        />
        <div
          v-else
          class="px-3 py-3 text-xs text-[var(--text-dim)] text-center"
        >
          График появится после сохранения PID-конфигурации
        </div>
      </ShellCard>
      <Hint :show="showHints">
        Dead / close / far — пороговые отклонения от target. PID
        переключает коэффициенты (close/far) в зависимости от зоны
        измерения. Открывайте только после базовой калибровки насосов
        и сенсоров.
      </Hint>
    </div>
  </div>
</template>

<script setup lang="ts">
import PidConfigForm from '@/Components/PidConfigForm.vue'
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue'
import PidChart from '../PidChart.vue'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import { Hint } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'

interface PidChartParams {
  target: number
  dead: number
  close: number
  far: number
}

defineProps<{
  zoneId: number
  phaseTargets?: RecipePhasePidTargets | null
  pidChartParams?: PidChartParams | null
}>()

defineEmits<{ (e: 'saved'): void }>()

const { showHints } = useLaunchPreferences()
</script>
