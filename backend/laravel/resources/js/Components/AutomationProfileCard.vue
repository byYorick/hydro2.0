<template>
  <section class="ui-hero p-5">
    <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
      <div>
        <p class="text-[11px] uppercase tracking-[0.24em] text-[color:var(--text-dim)]">
          Профиль автоматики зоны
        </p>
        <h2 class="text-xl font-semibold mt-1 text-[color:var(--text-primary)]">
          Вода, контур коррекции, zonal climate и досветка
        </h2>
        <div class="text-sm text-[color:var(--text-muted)] mt-1 max-w-3xl space-y-2">
          <p>
            Макроклимат теплицы настраивается на странице теплицы. Здесь — сводка authority-профиля зоны в БД
            (полив, досветка, опциональный zonal climate, параметры водного контура), без дублирования климатического профиля теплицы.
          </p>
          <p>
            Канонические целевые pH/EC <span class="text-[color:var(--text-primary)]">активной фазы рецепта</span>
            задаются в рецепте и в блоке «Коррекция и калибровка» / live edit фазы; цифры в карточке «контур pH/EC»
            — из профиля автоматики зоны и могут с ними не совпадать.
          </p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Badge :variant="canConfigureAutomation ? 'success' : 'warning'">
          {{ canConfigureAutomation ? 'Режим настройки (агроном)' : 'Режим оператора' }}
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
          Zonal climate
        </div>
        <div class="ui-kpi-value !text-lg">
          {{ zoneClimateEnabled ? 'вкл.' : 'выкл.' }}
        </div>
        <div class="ui-kpi-hint">
          Флаг подсистемы в профиле зоны; узлы CO₂ и прикорневой вентиляции привязываются в мастере. Не путать с климатом теплицы.
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Водный узел
        </div>
        <div class="ui-kpi-value !text-lg">
          {{ waterForm.tanksCount }} бака · {{ waterForm.systemType }}
        </div>
        <div class="ui-kpi-hint">
          Топология и диагностика из профиля зоны: {{ waterTopologyLabel }} · diag {{ waterForm.diagnosticsIntervalMinutes }} мин
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Контур pH / EC (профиль)
        </div>
        <div class="ui-kpi-value !text-lg">
          pH {{ waterForm.targetPh.toFixed(2) }} · EC {{ waterForm.targetEc.toFixed(1) }}
        </div>
        <div class="ui-kpi-hint">
          Ориентиры и допуски из профиля зоны: pH ±{{ phToleranceAbs.toFixed(2) }} ({{ phPct }}%)
          · EC ±{{ ecToleranceAbs.toFixed(2) }} ({{ ecPct }}%). Сетпоинты цикла — из фазы рецепта.
        </div>
      </article>

      <article class="ui-kpi-card">
        <div class="ui-kpi-label">
          Досветка
        </div>
        <div class="ui-kpi-value !text-lg">
          {{ lightingForm.luxDay }} lux
        </div>
        <div class="ui-kpi-hint">
          Расписание из профиля зоны: {{ lightingForm.scheduleStart }}–{{ lightingForm.scheduleEnd }} · каждые {{ lightingForm.intervalMinutes }} мин
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
