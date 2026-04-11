<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]">
    <details
      open
      class="group"
    >
      <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
        <div>
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Раствор и коррекция
          </h4>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            Целевые параметры раствора и правила, по которым зона их удерживает.
          </p>
        </div>
        <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          Отдельный блок
        </span>
      </summary>

      <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('water.targetPh')"
          >
            Целевой pH (из рецепта)
            <input
              v-model.number="waterForm.targetPh"
              type="number"
              min="4"
              max="9"
              step="0.1"
              class="input-field mt-1 w-full"
              disabled
            />
          </label>
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('water.targetEc')"
          >
            Целевой EC (из рецепта)
            <input
              v-model.number="waterForm.targetEc"
              type="number"
              min="0.1"
              max="10"
              step="0.1"
              class="input-field mt-1 w-full"
              disabled
            />
          </label>
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs text-[color:var(--text-muted)] md:col-span-2">
            <div class="font-semibold text-[color:var(--text-primary)]">
              Recipe-derived chemistry summary
            </div>
            <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
              <div>pH window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.phMin ?? '—' }}..{{ recipeChemistrySummary.phMax ?? '—' }}</span></div>
              <div>EC window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.ecMin ?? '—' }}..{{ recipeChemistrySummary.ecMax ?? '—' }}</span></div>
              <div class="md:col-span-2">
                EC strategy: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.nutrientMode ?? 'ratio_ec_pid' }}</span>
              </div>
            </div>
          </div>
        </div>

        <details class="rounded-xl border border-[color:var(--border-muted)] p-3">
          <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
            Расширенные настройки
          </summary>

          <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('water.correctionMaxEcCorrectionAttempts')"
            >
              Лимит попыток EC-коррекции
              <input
                v-model.number="waterForm.correctionMaxEcCorrectionAttempts"
                type="number"
                min="1"
                max="50"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('water.correctionMaxPhCorrectionAttempts')"
            >
              Лимит попыток pH-коррекции
              <input
                v-model.number="waterForm.correctionMaxPhCorrectionAttempts"
                type="number"
                min="1"
                max="50"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('water.correctionPrepareRecirculationMaxAttempts')"
            >
              Лимит окон рециркуляции
              <input
                v-model.number="waterForm.correctionPrepareRecirculationMaxAttempts"
                type="number"
                min="1"
                max="50"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('water.correctionPrepareRecirculationMaxCorrectionAttempts')"
            >
              Лимит correction-шагов
              <input
                v-model.number="waterForm.correctionPrepareRecirculationMaxCorrectionAttempts"
                type="number"
                min="1"
                max="500"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
          </div>
        </details>

        <div
          v-if="showCorrectionCalibrationStack && zoneId && sensorCalibrationSettings"
          class="border-t border-[color:var(--border-muted)] pt-4"
        >
          <ZoneCorrectionCalibrationStack
            :zone-id="zoneId"
            :sensor-calibration-settings="sensorCalibrationSettings"
          />
        </div>

        <div
          v-if="ctx.showSectionSaveButtons.value"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          <span>Сохраняет изменения этой секции в общем профиле зоны.</span>
          <Button
            size="sm"
            :disabled="!saveAllowed"
            data-test="save-section-solution-correction"
            @click="ctx.emitSaveSection('solution_correction')"
          >
            {{ ctx.savingSection.value === 'solution_correction' ? 'Сохранение...' : 'Сохранить секцию' }}
          </Button>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import ZoneCorrectionCalibrationStack from '@/Components/ZoneCorrectionCalibrationStack.vue'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'

export interface RecipeChemistrySummary {
  phTarget: number | null
  phMin: number | null
  phMax: number | null
  ecTarget: number | null
  ecMin: number | null
  ecMax: number | null
  nutrientMode: string | null
}

defineProps<{
  recipeChemistrySummary: RecipeChemistrySummary
  saveAllowed: boolean
  showCorrectionCalibrationStack?: boolean
  zoneId?: number | null
  sensorCalibrationSettings?: SensorCalibrationSettings | null
}>()

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })

const ctx = useZoneAutomationSectionContext()
</script>
