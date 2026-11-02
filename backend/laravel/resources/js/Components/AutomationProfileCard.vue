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
          {{ waterTopologyLabel }} · Проверка каждые {{ waterForm.diagnosticsIntervalMinutes }} мин
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          pH и EC воды
        </div>
        <div class="ui-kpi-value !text-lg">
          pH {{ waterForm.targetPh.toFixed(2) }} · EC {{ waterForm.targetEc.toFixed(1) }}
        </div>
        <div class="ui-kpi-hint">
          Значения профиля: pH ±{{ phToleranceAbs.toFixed(2) }} ({{ phPct }}%), EC ±{{ ecToleranceAbs.toFixed(2) }} ({{ ecPct }}%).
          Для цикла действуют цели из рецепта.
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Досветка
        </div>
        <div class="ui-kpi-value !text-lg">
          {{ lightingForm.luxDay }} лк
        </div>
        <div class="ui-kpi-hint">
          {{ lightingForm.scheduleStart }}–{{ lightingForm.scheduleEnd }} · каждые {{ lightingForm.intervalMinutes }} мин
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
}

const props = defineProps<Props>()
const systemTypeLabel = computed(() => ({ drip: 'Капельный', substrate_trays: 'Лотки', nft: 'NFT' })[props.waterForm.systemType] ?? props.waterForm.systemType)

defineEmits<{
  (e: 'edit'): void
}>()

const phPct = computed(() => {
  const raw = Number(props.waterForm.phPct)
  return Number.isFinite(raw) && raw > 0 ? raw : 5
})

const ecPct = computed(() => {
  const raw = Number(props.waterForm.ecPct)
  return Number.isFinite(raw) && raw > 0 ? raw : 10
})

const phToleranceAbs = computed(() => {
  return props.waterForm.targetPh * phPct.value / 100
})

const ecToleranceAbs = computed(() => {
  return props.waterForm.targetEc * ecPct.value / 100
})
</script>
