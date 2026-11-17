<template>
  <section class="ui-hero p-5">
    <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
      <div>
        <p class="text-[11px] uppercase tracking-[0.24em] text-[color:var(--text-dim)]">
          Текущие настройки
        </p>
        <h2 class="text-xl font-semibold mt-1 text-[color:var(--text-primary)]">
          Профиль зоны
        </h2>
        <div class="text-sm text-[color:var(--text-muted)] mt-1 max-w-3xl space-y-2">
          <p>Водный контур, полив, климат зоны и свет. Цели pH и EC действующего цикла берутся из рецепта.</p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Badge :variant="canConfigureAutomation ? 'success' : 'warning'">
          {{ canConfigureAutomation ? 'Можно редактировать' : 'Только просмотр' }}
        </Badge>
        <Badge variant="info">
          Телеметрия: {{ telemetryLabel }}
        </Badge>
        <Button
          v-if="canConfigureAutomation"
          size="sm"
          @click="$emit('edit')"
        >
          Редактировать в мастере запуска
        </Button>
      </div>
    </div>

    <div class="ui-kpi-grid md:grid-cols-2 xl:grid-cols-4 mt-4">
      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Климат зоны
        </div>
        <div class="ui-kpi-value !text-lg">
          {{ zoneClimateEnabled ? 'вкл.' : 'выкл.' }}
        </div>
        <div class="ui-kpi-hint">
          Климат теплицы настраивается на странице теплицы.
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Вода и полив
        </div>
        <div class="ui-kpi-value !text-lg">
          {{ waterForm.tanksCount }} бака · {{ systemTypeLabel }}
        </div>
        <div class="ui-kpi-hint">
          {{ waterTopologyLabel }} · {{ waterForm.diagnosticsEnabled ? `Диагностика каждые ${waterForm.diagnosticsIntervalMinutes} мин` : 'Диагностика выключена' }}
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Цели активной фазы рецепта
        </div>
        <div class="ui-kpi-value !text-lg">
          pH {{ phaseTargets?.ph?.toFixed(2) ?? '—' }} · EC {{ phaseTargets?.ec?.toFixed(2) ?? '—' }}
        </div>
        <div class="ui-kpi-hint">
          {{ phaseTargets ? (phaseTargets.phaseLabel ?? 'Текущая фаза') : 'Активная фаза не загружена. Откройте цикл и проверьте его рецепт.' }}
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Досветка
        </div>
        <div class="ui-kpi-value !text-lg">
          {{ lightingForm.enabled ? `${lightingForm.luxDay} лк` : 'Выключена' }}
        </div>
        <div class="ui-kpi-hint">
          {{ lightingForm.scheduleStart }}–{{ lightingForm.scheduleEnd }} · каждые {{ lightingForm.intervalMinutes }} мин
        </div>
      </article>
    </div>
    <p class="mt-3 text-xs text-[color:var(--text-muted)]">
      Условие полива: {{ irrigationStrategyLabel(waterForm.irrigationDecisionStrategy) }}.
      Проверка каждые {{ waterForm.intervalMinutes }} мин, подача до {{ waterForm.durationSeconds }} сек.
      {{ waterForm.correctionDuringIrrigation ? (waterForm.irrigationEcComponent === 'none' ? 'Во время полива корректируется только pH.' : 'Во время полива корректируются pH и выбранный компонент EC.') : 'Коррекция раствора во время полива выключена.' }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import { irrigationStrategyLabel } from '@/utils/irrigationDecisionView'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import type { LightingFormState, WaterFormState } from '@/composables/zoneAutomationTypes'

interface Props {
  canConfigureAutomation: boolean
  telemetryLabel: string
  waterTopologyLabel: string
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateEnabled?: boolean
  phaseTargets?: RecipePhasePidTargets | null
}

const props = defineProps<Props>()
const systemTypeLabel = computed(() => ({ drip: 'Капельный', substrate_trays: 'Лотки', nft: 'NFT' })[props.waterForm.systemType] ?? props.waterForm.systemType)

defineEmits<{
  (e: 'edit'): void
}>()

</script>
