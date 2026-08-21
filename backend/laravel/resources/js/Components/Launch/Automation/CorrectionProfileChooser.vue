<template>
  <div
    class="flex flex-col gap-2.5"
    data-testid="correction-profile-chooser"
  >
    <PresetPillStrip
      :items="pillItems"
      :model-value="modelValue ?? null"
      label="Профиль коррекции"
      :description="currentPreset?.desc ?? ''"
      test-id="correction-profile-preset-strip"
      @select="onSelect"
    >
      <template #actions>
        <Chip
          v-if="isModified"
          tone="warn"
        >
          изменено
        </Chip>
      </template>
    </PresetPillStrip>

    <p
      v-if="currentPreset"
      class="text-[11px] text-[var(--text-dim)] leading-snug px-1"
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
import PresetPillStrip, { type PresetPillItem, type PresetPillKey } from '@/Components/Shared/PresetPillStrip.vue'
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

const pillItems = computed<PresetPillItem[]>(() =>
  (Object.keys(CORRECTION_PRESETS) as CorrectionProfileKey[]).map((key) => {
    const preset = CORRECTION_PRESETS[key]
    return {
      key,
      label: preset.label,
      meta: `±${preset.config.correctionDeadbandPh}pH · ${preset.config.correctionStepPhMl}мл`,
      locked: true,
      title: preset.desc,
      testId: `correction-profile-preset-${key}`,
    }
  }),
)

const currentPreset = computed(() =>
  props.modelValue ? CORRECTION_PRESETS[props.modelValue] : null,
)

const isModified = computed(() => {
  if (!currentPreset.value) return false
  const cfg = currentPreset.value.config
  return (
    props.waterForm.phPct !== cfg.phPct
    || props.waterForm.ecPct !== cfg.ecPct
    || (props.waterForm.correctionStabilizationSec ?? cfg.correctionStabilizationSec)
      !== cfg.correctionStabilizationSec
    || (props.waterForm.correctionMaxPhCorrectionAttempts
      ?? cfg.correctionMaxPhCorrectionAttempts) !== cfg.correctionMaxPhCorrectionAttempts
    || (props.waterForm.correctionMaxEcCorrectionAttempts
      ?? cfg.correctionMaxEcCorrectionAttempts) !== cfg.correctionMaxEcCorrectionAttempts
  )
})

function onSelect(key: PresetPillKey): void {
  if (key === null) return
  const profileKey = String(key) as CorrectionProfileKey
  if (!(profileKey in CORRECTION_PRESETS)) return
  emit('update:modelValue', profileKey)
  const cfg = CORRECTION_PRESETS[profileKey].config
  emit('apply', {
    phPct: cfg.phPct,
    ecPct: cfg.ecPct,
    correctionStabilizationSec: cfg.correctionStabilizationSec,
    correctionMaxPhCorrectionAttempts: cfg.correctionMaxPhCorrectionAttempts,
    correctionMaxEcCorrectionAttempts: cfg.correctionMaxEcCorrectionAttempts,
  })
}
</script>
