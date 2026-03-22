<template>
  <div class="space-y-4">
    <section class="space-y-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Порядок работы
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          {{ stackIntroText }}
        </div>
      </div>

      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">1. Сенсоры</div>
          <div class="mt-1">Сначала приведите в порядок pH/EC sensor calibration, чтобы дальнейшие настройки опирались на корректные измерения.</div>
        </div>
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">2. Насосы</div>
          <div class="mt-1">После этого откалибруйте дозирующие насосы. Runtime bounds остаются в расширенных настройках pump calibration wizard и нужны только для нестандартных зон.</div>
        </div>
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">3. Process и PID</div>
          <div class="mt-1">{{ processAndPidHint }}</div>
        </div>
      </div>
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          1. Калибровка сенсоров
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Отдельный контур pH/EC sensor calibration и его история.
        </div>
      </div>

      <SensorCalibrationStatus
        :zone-id="zoneId"
        :settings="sensorCalibrationSettings"
      />
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          2. Калибровка дозирующих насосов
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Статус и история pump calibration для насосов, участвующих в in-flow correction.
        </div>
      </div>

      <PumpCalibrationsPanel
        :zone-id="zoneId"
        @open-pump-calibration="$emit('open-pump-calibration')"
      />
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          3. Калибровка процесса
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Настройка observe-window и process gain для фаз `solution_fill`, `tank_recirc`, `irrigation` и `generic`.
        </div>
      </div>

      <div id="zone-process-calibration-panel-shared">
        <ProcessCalibrationPanel :zone-id="zoneId" />
      </div>
    </section>

    <section
      v-if="showRuntimeReadiness"
      class="space-y-4 border-t border-[color:var(--border-muted)] pt-4"
    >
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          4. Итоговая готовность correction runtime
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Финальная проверка, что process calibration и pump calibration закрывают обязательные runtime-контракты.
        </div>
      </div>

      <CorrectionRuntimeReadinessCard
        :zone-id="zoneId"
        @focus-process-calibration="scrollToSection('zone-process-calibration-panel-shared')"
        @open-pump-calibration="$emit('open-pump-calibration')"
      />
    </section>

    <details class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
      <summary class="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-[color:var(--text-primary)]">
        Расширенная тонкая настройка PID и autotune
        <div class="mt-1 text-xs font-normal text-[color:var(--text-dim)]">
          Открывайте этот блок после базовой калибровки, если нужно довести correction loop, изменить zone PID override или запустить autotune.
        </div>
      </summary>

      <div class="border-t border-[color:var(--border-muted)] p-4">
        <section class="grid gap-4 xl:grid-cols-2">
          <PidConfigForm :zone-id="zoneId" />
          <RelayAutotuneTrigger :zone-id="zoneId" />
        </section>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import CorrectionRuntimeReadinessCard from '@/Components/CorrectionRuntimeReadinessCard.vue'
import PidConfigForm from '@/Components/PidConfigForm.vue'
import ProcessCalibrationPanel from '@/Components/ProcessCalibrationPanel.vue'
import PumpCalibrationsPanel from '@/Components/PumpCalibrationsPanel.vue'
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue'
import SensorCalibrationStatus from '@/Components/SensorCalibrationStatus.vue'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = withDefaults(defineProps<{
  zoneId: number
  sensorCalibrationSettings: SensorCalibrationSettings
  showRuntimeReadiness?: boolean
}>(), {
  showRuntimeReadiness: true,
})

defineEmits<{
  (e: 'open-pump-calibration'): void
}>()

const stackIntroText = computed(() => {
  if (props.showRuntimeReadiness) {
    return 'Шаг выстроен по зависимостям calibration-контура: от достоверности измерений и дозирования к process calibration и финальной проверке runtime. PID и autotune вынесены в расширенную тонкую настройку.'
  }

  return 'Шаг выстроен по зависимостям calibration-контура: от достоверности измерений и дозирования к process calibration. Финальная проверка correction runtime вынесена в следующий шаг запуска.'
})

const processAndPidHint = computed(() => {
  if (props.showRuntimeReadiness) {
    return 'Только затем заполняйте process calibration. PID и autotune открывайте только для тонкой доводки, если базовый контур уже стабилен.'
  }

  return 'Только затем заполняйте process calibration. PID и autotune открывайте только для тонкой доводки; итоговая readiness теперь проверяется уже в финальном шаге запуска.'
})

function scrollToSection(id: string): void {
  if (typeof document === 'undefined') {
    return
  }

  const element = document.getElementById(id)
  if (!element) {
    return
  }

  element.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>
