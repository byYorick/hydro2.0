<template>
  <div
    class="p-3 border border-brand bg-brand-soft rounded-md flex flex-col gap-2.5"
  >
    <div class="flex items-center gap-2.5 flex-wrap">
      <svg
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        class="text-brand shrink-0"
        aria-hidden="true"
      >
        <path
          d="M4 2h8v12l-4-3-4 3z"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linejoin="round"
        />
      </svg>
      <span class="text-xs font-semibold text-brand-ink">Профиль коррекции</span>
      <Chip
        v-if="isModified"
        tone="warn"
      >
        изменено
      </Chip>
    </div>

    <div class="flex gap-1.5 flex-wrap">
      <button
        v-for="(preset, key) in CORRECTION_PRESETS"
        :key="key"
        type="button"
        :class="[
          'px-3 py-2 border rounded-sm text-left flex flex-col items-start gap-0.5 min-w-[120px] cursor-pointer',
          modelValue === key
            ? 'bg-brand text-white border-brand font-semibold'
            : 'bg-[var(--bg-surface)] text-[var(--text-primary)] border-[var(--border-muted)] hover:border-brand',
        ]"
        @click="onPick(key)"
      >
        <span class="text-xs font-semibold">{{ preset.label }}</span>
        <span
          class="font-mono text-[10px]"
          :class="modelValue === key ? 'opacity-75' : 'text-[var(--text-dim)]'"
        >
          ±{{ preset.config.correctionDeadbandPh }}pH · {{ preset.config.correctionStepPhMl }}мл
        </span>
      </button>
    </div>

    <div
      v-if="currentPreset"
      class="text-[11px] text-[var(--text-muted)] leading-snug px-2.5 py-2 bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-sm"
    >
      {{ currentPreset.desc }}
    </div>

    <p
      v-if="currentPreset"
      class="text-[11px] text-[var(--text-dim)] leading-snug"
    >
      Применятся:
      <span class="font-mono">phPct {{ currentPreset.config.phPct }}%</span> ·
      <span class="font-mono">ecPct {{ currentPreset.config.ecPct }}%</span> ·
      <span class="font-mono">stabilization {{ currentPreset.config.correctionStabilizationSec }}с</span> ·
      <span class="font-mono">attempts {{ currentPreset.config.correctionMaxPhCorrectionAttempts }}/{{ currentPreset.config.correctionMaxEcCorrectionAttempts }}</span>.
      Остальные значения preset'а (deadband/step/maxDose/cooldown) — отдельный
      <span class="font-mono">zone.correction</span> doc на шаге «Калибровка».
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Chip from '@/Components/Shared/Primitives/Chip.vue'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import {
  CORRECTION_PRESETS,
  type CorrectionProfileKey,
} from './correctionPresets'

const props = defineProps<{
  modelValue?: CorrectionProfileKey | null
  waterForm: WaterFormState
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', key: CorrectionProfileKey | null): void
  (e: 'apply', patch: Partial<WaterFormState>): void
}>()

const currentPreset = computed(() =>
  props.modelValue ? CORRECTION_PRESETS[props.modelValue] : null,
)

// "Изменено" if any of the 5 fields we actually apply differs from preset.
const isModified = computed(() => {
  if (!currentPreset.value) return false
  const cfg = currentPreset.value.config
  return (
    props.waterForm.phPct !== cfg.phPct ||
    props.waterForm.ecPct !== cfg.ecPct ||
    (props.waterForm.correctionStabilizationSec ?? cfg.correctionStabilizationSec) !==
      cfg.correctionStabilizationSec ||
    (props.waterForm.correctionMaxPhCorrectionAttempts ??
      cfg.correctionMaxPhCorrectionAttempts) !== cfg.correctionMaxPhCorrectionAttempts ||
    (props.waterForm.correctionMaxEcCorrectionAttempts ??
      cfg.correctionMaxEcCorrectionAttempts) !== cfg.correctionMaxEcCorrectionAttempts
  )
})

function onPick(key: CorrectionProfileKey): void {
  emit('update:modelValue', key)
  // Apply only fields that exist in waterFormSchema (5 of 13).
  // Остальные поля preset'а — справочно для оператора, реально применяются
  // через CorrectionConfigForm на шаге «Калибровка» (zone.correction doc).
  const cfg = CORRECTION_PRESETS[key].config
  emit('apply', {
    phPct: cfg.phPct,
    ecPct: cfg.ecPct,
    correctionStabilizationSec: cfg.correctionStabilizationSec,
    correctionMaxPhCorrectionAttempts: cfg.correctionMaxPhCorrectionAttempts,
    correctionMaxEcCorrectionAttempts: cfg.correctionMaxEcCorrectionAttempts,
  })
}
</script>
