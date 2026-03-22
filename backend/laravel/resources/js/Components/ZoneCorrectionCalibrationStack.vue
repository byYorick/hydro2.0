<template>
  <div class="space-y-4">
    <section class="space-y-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Порядок работы
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Шаг выстроен по зависимостям calibration-контура: от достоверности измерений и дозирования к process calibration, PID и финальной проверке runtime.
        </div>
      </div>

      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">1. Сенсоры</div>
          <div class="mt-1">Сначала приведите в порядок pH/EC sensor calibration, чтобы дальнейшие настройки опирались на корректные измерения.</div>
        </div>
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">2. Насосы и bounds</div>
          <div class="mt-1">После этого откалибруйте дозирующие насосы и при необходимости скорректируйте runtime bounds для planner.</div>
        </div>
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">3. Process и PID</div>
          <div class="mt-1">Только затем заполняйте process calibration, запускайте autotune и смотрите финальную correction runtime readiness.</div>
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
          3. Runtime bounds насосов
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Zone-level override системных порогов pump calibration для runtime planner. Этот блок меняйте после базовой калибровки насосов, если зоне нужны свои ограничения.
        </div>
      </div>

      <ZonePumpCalibrationSettingsCard :zone-id="zoneId" />
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          4. Калибровка процесса
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Настройка observe-window и process gain для фаз `solution_fill`, `tank_recirc`, `irrigation` и `generic`.
        </div>
      </div>

      <div id="zone-process-calibration-panel-shared">
        <ProcessCalibrationPanel :zone-id="zoneId" />
      </div>
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          5. PID и автотюнинг
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Тонкая настройка регуляторов после того, как уже известны реальные дозировки и отклик процесса.
        </div>
      </div>

      <section class="grid gap-4 xl:grid-cols-2">
        <PidConfigForm :zone-id="zoneId" />
        <RelayAutotuneTrigger :zone-id="zoneId" />
      </section>
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          6. Итоговая готовность correction runtime
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
  </div>
</template>

<script setup lang="ts">
import CorrectionRuntimeReadinessCard from '@/Components/CorrectionRuntimeReadinessCard.vue'
import PidConfigForm from '@/Components/PidConfigForm.vue'
import ProcessCalibrationPanel from '@/Components/ProcessCalibrationPanel.vue'
import PumpCalibrationsPanel from '@/Components/PumpCalibrationsPanel.vue'
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue'
import SensorCalibrationStatus from '@/Components/SensorCalibrationStatus.vue'
import ZonePumpCalibrationSettingsCard from '@/Components/ZonePumpCalibrationSettingsCard.vue'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

defineProps<{
  zoneId: number
  sensorCalibrationSettings: SensorCalibrationSettings
}>()

defineEmits<{
  (e: 'open-pump-calibration'): void
}>()

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
