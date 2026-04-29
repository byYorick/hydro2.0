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
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5">
      <Field :label="meta('targetPh').label" required :hint="meta('targetPh').hint">
        <div :class="lockedCls" :title="meta('targetPh').details">
          <Ic name="lock" size="sm" class="text-[var(--text-dim)]" />
          {{ waterForm.targetPh }}
        </div>
      </Field>
      <Field :label="meta('targetEc').label" required :hint="meta('targetEc').hint">
        <div :class="lockedCls" :title="meta('targetEc').details">
          <Ic name="lock" size="sm" class="text-[var(--text-dim)]" />
          {{ waterForm.targetEc }} <span class="text-[var(--text-dim)] text-xs ml-1">mS/cm</span>
        </div>
      </Field>
      <Field :label="meta('phPct').label" :hint="meta('phPct').hint">
        <input
          v-bind="numAttrs"
          :title="meta('phPct').details"
          :value="waterForm.phPct"
          @input="upd('phPct', toNum($event))"
        >
      </Field>
      <Field :label="meta('ecPct').label" :hint="meta('ecPct').hint">
        <input
          v-bind="numAttrs"
          :title="meta('ecPct').details"
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
import { createMetaResolver, toNum, type FieldMeta } from './sharedFormUtils'

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
  'block w-full h-8 rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none transition-[border-color,box-shadow,background-color] duration-150 focus:border-brand focus:ring-2 focus:ring-brand-soft focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand-soft'
const numAttrs = { class: inputCls, type: 'number' }

const lockedCls =
  'flex items-center h-8 px-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] text-sm font-mono text-[var(--text-primary)] gap-1.5'

const CORRECTION_FIELD_META: Partial<Record<keyof WaterFormState, FieldMeta>> = {
  targetPh: {
    label: 'Целевой pH',
    hint: 'Значение из активной фазы рецепта',
    details: 'Базовый целевой pH для зоны. Используется контроллером pH как опорная точка коррекции.',
  },
  targetEc: {
    label: 'Целевой EC',
    hint: 'Значение из активной фазы рецепта',
    details: 'Базовый целевой EC (mS/cm) для зоны. Используется контроллером EC как опорная точка коррекции.',
  },
  phPct: {
    label: 'Допуск pH, %',
    hint: 'Ширина окна корректировки',
    details: 'Процент допустимого отклонения pH от target до запуска коррекции.',
  },
  ecPct: {
    label: 'Допуск EC, %',
    hint: 'Ширина окна корректировки',
    details: 'Процент допустимого отклонения EC от target до запуска коррекции.',
  },
}
const meta = createMetaResolver<WaterFormState>(CORRECTION_FIELD_META, {
  label: '',
  hint: 'Параметр коррекции',
  details: 'Параметр влияет на логику и пороги коррекции pH/EC.',
})

function upd<K extends keyof WaterFormState>(key: K, value: WaterFormState[K]) {
  emit('update:waterForm', { ...props.waterForm, [key]: value })
}

function onPresetApply(patch: Partial<WaterFormState>) {
  emit('update:waterForm', { ...props.waterForm, ...patch })
}
</script>
