<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]">
    <details
      open
      class="group"
    >
      <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
        <div>
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Полив
          </h4>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            Рабочий цикл полива, объёмы и эксплуатационные параметры водного узла.
          </p>
        </div>
        <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          Основной цикл
        </span>
      </summary>

      <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
        <IrrigationModeSelector
          v-model:water-form="waterForm"
          :recipe-irrigation-summary="recipeIrrigationSummary"
        />

        <IrrigationBasicFieldsGrid v-model:water-form="waterForm" />

        <details class="rounded-xl border border-[color:var(--border-muted)] p-3">
          <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
            Расширенные настройки
          </summary>

          <div class="mt-3 space-y-4">
            <SmartIrrigationControlsGroup
              v-model:water-form="waterForm"
              :recipe-soil-moisture-targets="recipeSoilMoistureTargets"
            />

            <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                Диагностика и refill
              </h5>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.diagnosticsEnabled')"
                >
                  Диагностика
                  <select
                    v-model="waterForm.diagnosticsEnabled"
                    class="input-select mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  >
                    <option :value="true">Включена</option>
                    <option :value="false">Выключена</option>
                  </select>
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.diagnosticsIntervalMinutes')"
                >
                  Интервал диагностики (мин)
                  <input
                    v-model.number="waterForm.diagnosticsIntervalMinutes"
                    type="number"
                    min="1"
                    max="1440"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.diagnosticsWorkflow')"
                >
                  Режим диагностики
                  <select
                    v-model="waterForm.diagnosticsWorkflow"
                    class="input-select mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  >
                    <option value="startup">startup</option>
                    <option
                      value="cycle_start"
                      :disabled="waterForm.tanksCount === 2"
                    >
                      cycle_start
                    </option>
                    <option value="diagnostics">diagnostics</option>
                  </select>
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.cleanTankFullThreshold')"
                >
                  Порог полного бака (0..1)
                  <input
                    v-model.number="waterForm.cleanTankFullThreshold"
                    type="number"
                    min="0.05"
                    max="1"
                    step="0.01"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.refillDurationSeconds')"
                >
                  Длительность refill (сек)
                  <input
                    v-model.number="waterForm.refillDurationSeconds"
                    type="number"
                    min="1"
                    max="3600"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.refillTimeoutSeconds')"
                >
                  Таймаут refill (сек)
                  <input
                    v-model.number="waterForm.refillTimeoutSeconds"
                    type="number"
                    min="30"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)] md:col-span-2"
                  :title="zoneAutomationFieldHelp('water.refillRequiredNodeTypes')"
                >
                  Обязательные типы нод для refill
                  <input
                    v-model="waterForm.refillRequiredNodeTypes"
                    type="text"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.refillPreferredChannel')"
                >
                  Канал refill
                  <input
                    v-model="waterForm.refillPreferredChannel"
                    type="text"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
              </div>
            </div>

            <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                Startup и recovery
              </h5>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.startupCleanFillTimeoutSeconds')"
                >
                  Таймаут набора чистой воды
                  <input
                    v-model.number="waterForm.startupCleanFillTimeoutSeconds"
                    type="number"
                    min="30"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.startupSolutionFillTimeoutSeconds')"
                >
                  Таймаут набора раствора
                  <input
                    v-model.number="waterForm.startupSolutionFillTimeoutSeconds"
                    type="number"
                    min="30"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.startupPrepareRecirculationTimeoutSeconds')"
                >
                  Таймаут подготовки рециркуляции
                  <input
                    v-model.number="waterForm.startupPrepareRecirculationTimeoutSeconds"
                    type="number"
                    min="30"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.startupCleanFillRetryCycles')"
                >
                  Повторы clean fill
                  <input
                    v-model.number="waterForm.startupCleanFillRetryCycles"
                    type="number"
                    min="0"
                    max="20"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.irrigationRecoveryMaxContinueAttempts')"
                >
                  Лимит recovery-continue
                  <input
                    v-model.number="waterForm.irrigationRecoveryMaxContinueAttempts"
                    type="number"
                    min="1"
                    max="30"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.irrigationRecoveryTimeoutSeconds')"
                >
                  Таймаут recovery
                  <input
                    v-model.number="waterForm.irrigationRecoveryTimeoutSeconds"
                    type="number"
                    min="30"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.manualIrrigationSeconds')"
                >
                  Ручной полив (сек)
                  <input
                    v-model.number="waterForm.manualIrrigationSeconds"
                    type="number"
                    min="1"
                    max="3600"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
              </div>
            </div>

            <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                Fail-safe guards
              </h5>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.cleanFillMinCheckDelayMs')"
                >
                  Clean fill: задержка проверки min (мс)
                  <input
                    v-model.number="waterForm.cleanFillMinCheckDelayMs"
                    type="number"
                    min="0"
                    max="3600000"
                    step="10"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.solutionFillCleanMinCheckDelayMs')"
                >
                  Solution fill: задержка clean_min (мс)
                  <input
                    v-model.number="waterForm.solutionFillCleanMinCheckDelayMs"
                    type="number"
                    min="0"
                    max="3600000"
                    step="10"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.solutionFillSolutionMinCheckDelayMs')"
                >
                  Solution fill: leak-check по solution_min (мс)
                  <input
                    v-model.number="waterForm.solutionFillSolutionMinCheckDelayMs"
                    type="number"
                    min="0"
                    max="3600000"
                    step="10"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.estopDebounceMs')"
                >
                  E-stop debounce (мс)
                  <input
                    v-model.number="waterForm.estopDebounceMs"
                    type="number"
                    min="20"
                    max="5000"
                    step="10"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)] md:col-span-2 xl:col-span-2"
                  :title="zoneAutomationFieldHelp('water.recirculationStopOnSolutionMin')"
                >
                  Recirculation: stop on solution min
                  <select
                    v-model="waterForm.recirculationStopOnSolutionMin"
                    class="input-select mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  >
                    <option :value="true">Fail-closed при low solution</option>
                    <option :value="false">Не останавливать recirculation</option>
                  </select>
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)] md:col-span-2 xl:col-span-2"
                  :title="zoneAutomationFieldHelp('water.stopOnSolutionMin')"
                >
                  Irrigation: stop on solution min
                  <select
                    v-model="waterForm.stopOnSolutionMin"
                    data-test="irrigation-stop-on-solution-min"
                    class="input-select mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  >
                    <option :value="true">Fail-closed при low solution</option>
                    <option :value="false">Не останавливать irrigation workflow</option>
                  </select>
                </label>
              </div>
            </div>

            <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                Плановая смена раствора
              </h5>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.solutionChangeEnabled')"
                >
                  Смена раствора
                  <select
                    v-model="waterForm.solutionChangeEnabled"
                    class="input-select mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  >
                    <option :value="true">Включена</option>
                    <option :value="false">Выключена</option>
                  </select>
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.solutionChangeIntervalMinutes')"
                >
                  Интервал смены (мин)
                  <input
                    v-model.number="waterForm.solutionChangeIntervalMinutes"
                    type="number"
                    min="1"
                    max="1440"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="zoneAutomationFieldHelp('water.solutionChangeDurationSeconds')"
                >
                  Длительность смены (сек)
                  <input
                    v-model.number="waterForm.solutionChangeDurationSeconds"
                    type="number"
                    min="1"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!ctx.canConfigure.value"
                  />
                </label>
              </div>
            </div>
          </div>
        </details>

        <div
          v-if="ctx.showSectionSaveButtons.value"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          <span>Сохраняет изменения этой секции в общем профиле зоны.</span>
          <Button
            size="sm"
            :disabled="!saveAllowed"
            data-test="save-section-irrigation"
            @click="ctx.emitSaveSection('irrigation')"
          >
            {{ ctx.savingSection.value === 'irrigation' ? 'Сохранение...' : 'Сохранить секцию' }}
          </Button>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import IrrigationBasicFieldsGrid from '@/Components/ZoneAutomation/IrrigationBasicFieldsGrid.vue'
import IrrigationModeSelector from '@/Components/ZoneAutomation/IrrigationModeSelector.vue'
import SmartIrrigationControlsGroup from '@/Components/ZoneAutomation/SmartIrrigationControlsGroup.vue'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'

export interface RecipeIrrigationSummary {
  mode: string | null
  intervalSec: number | null
  durationSec: number | null
}

export interface RecipeSoilMoistureTargets {
  day: number | null
  night: number | null
}

defineProps<{
  recipeIrrigationSummary: RecipeIrrigationSummary
  recipeSoilMoistureTargets: RecipeSoilMoistureTargets
  saveAllowed: boolean
}>()

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })

const ctx = useZoneAutomationSectionContext()
</script>
