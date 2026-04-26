<template>
  <div class="flex flex-col gap-3.5">
    <CorrectionProfileChooser
      v-model="profileKey"
      :water-form="waterForm"
      @apply="onPresetApply"
    />

    <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]">
      Целевые значения <span class="text-[10px] text-brand normal-case ml-1.5">← из рецепта, read-only</span>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5">
      <Field label="targetPh" required hint="из рецепта">
        <div :class="lockedCls">
          <Ic name="lock" size="sm" class="text-[var(--text-dim)]" />
          {{ waterForm.targetPh }}
        </div>
      </Field>
      <Field label="targetEc" required hint="из рецепта">
        <div :class="lockedCls">
          <Ic name="lock" size="sm" class="text-[var(--text-dim)]" />
          {{ waterForm.targetEc }} <span class="text-[var(--text-dim)] text-xs ml-1">mS/cm</span>
        </div>
      </Field>
      <Field label="phPct" hint="допуск">
        <input
          v-bind="numAttrs"
          :value="waterForm.phPct"
          @input="upd('phPct', toNum($event))"
        >
      </Field>
      <Field label="ecPct" hint="допуск">
        <input
          v-bind="numAttrs"
          :value="waterForm.ecPct"
          @input="upd('ecPct', toNum($event))"
        >
      </Field>
    </div>

    <Hint :show="showHints">
      Полный стек коррекции (deadband / step / maxDose / cooldown / гистерезис /
      аварийные стопы / recovery / per-контурные authority overrides) живёт
      в <span class="font-mono">automation_configs/zone.correction</span> и
      редактируется на шаге «Калибровка» через CorrectionConfigForm.
      Здесь — лишь quick-presets и read-only target из активной фазы рецепта.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Field, Hint } from '@/Components/Shared/Primitives'
import Ic from '@/Components/Icons/Ic.vue'
import CorrectionProfileChooser from '../CorrectionProfileChooser.vue'
import type { CorrectionProfileKey } from '../correctionPresets'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'

const props = defineProps<{ waterForm: WaterFormState }>()
const emit = defineEmits<{ (e: 'update:waterForm', next: WaterFormState): void }>()

const { showHints } = useLaunchPreferences()

const profileKey = ref<CorrectionProfileKey | null>(null)

watch(
  () => props.waterForm,
  () => {
    /* keep profileKey local; reset on form-mismatch handled by chooser. */
  },
)

const inputCls =
  'block w-full h-8 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none focus-visible:ring-2 focus-visible:ring-brand'
const numAttrs = { class: inputCls, type: 'number' }

const lockedCls =
  'flex items-center h-8 px-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] text-sm font-mono text-[var(--text-primary)] gap-1.5'

function upd<K extends keyof WaterFormState>(key: K, value: WaterFormState[K]) {
  emit('update:waterForm', { ...props.waterForm, [key]: value })
}
function toNum(e: Event) {
  const n = Number((e.target as HTMLInputElement).value)
  return Number.isFinite(n) ? n : 0
}

function onPresetApply(patch: Partial<WaterFormState>) {
  emit('update:waterForm', { ...props.waterForm, ...patch })
}
</script>
