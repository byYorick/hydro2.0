<template>
  <div class="flex flex-col gap-3.5">
    <div class="flex items-center justify-between gap-3 pb-1 border-b border-dashed border-[var(--border-muted)]">
      <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)]">
        Стратегия и расписание
      </div>
      <div class="flex gap-1.5">
        <Button
          size="sm"
          :variant="!smart ? 'primary' : 'secondary'"
          @click="upd('irrigationDecisionStrategy', 'task')"
        >
          По времени
        </Button>
        <Button
          size="sm"
          :variant="smart ? 'primary' : 'secondary'"
          @click="upd('irrigationDecisionStrategy', 'smart_soil_v1')"
        >
          SMART soil v1
        </Button>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 items-center">
      <Field
        :label="meta('intervalMinutes').label"
        :hint="meta('intervalMinutes').hint"
        required
      >
        <input
          v-bind="numAttrs"
          :title="meta('intervalMinutes').details"
          :value="waterForm.intervalMinutes"
          @input="upd('intervalMinutes', toInt($event))"
        />
      </Field>
      <Field
        :label="meta('durationSeconds').label"
        :hint="meta('durationSeconds').hint"
        required
      >
        <input
          v-bind="numAttrs"
          :title="meta('durationSeconds').details"
          :value="waterForm.durationSeconds"
          @input="upd('durationSeconds', toInt($event))"
        />
      </Field>
      <ToggleField
        :model-value="waterForm.correctionDuringIrrigation"
        :label="meta('correctionDuringIrrigation').label"
        :title="meta('correctionDuringIrrigation').details"
        @update:model-value="(v) => upd('correctionDuringIrrigation', v)"
      />
      <ToggleField
        :model-value="!!waterForm.irrigationAutoReplayAfterSetup"
        :label="meta('irrigationAutoReplayAfterSetup').label"
        :title="meta('irrigationAutoReplayAfterSetup').details"
        @update:model-value="(v) => upd('irrigationAutoReplayAfterSetup', v)"
      />
    </div>

    <template v-if="smart">
      <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]">
        SMART soil v1 — параметры решения
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        <Field
          :label="meta('irrigationDecisionLookbackSeconds').label"
          :hint="meta('irrigationDecisionLookbackSeconds').hint"
        >
          <input
            v-bind="numAttrs"
            :title="meta('irrigationDecisionLookbackSeconds').details"
            :value="waterForm.irrigationDecisionLookbackSeconds ?? 0"
            @input="upd('irrigationDecisionLookbackSeconds', toInt($event))"
          />
        </Field>
        <Field
          :label="meta('irrigationDecisionMinSamples').label"
          :hint="meta('irrigationDecisionMinSamples').hint"
        >
          <input
            v-bind="numAttrs"
            :title="meta('irrigationDecisionMinSamples').details"
            :value="waterForm.irrigationDecisionMinSamples ?? 0"
            @input="upd('irrigationDecisionMinSamples', toInt($event))"
          />
        </Field>
        <Field
          :label="meta('irrigationDecisionStaleAfterSeconds').label"
          :hint="meta('irrigationDecisionStaleAfterSeconds').hint"
        >
          <input
            v-bind="numAttrs"
            :title="meta('irrigationDecisionStaleAfterSeconds').details"
            :value="waterForm.irrigationDecisionStaleAfterSeconds ?? 0"
            @input="upd('irrigationDecisionStaleAfterSeconds', toInt($event))"
          />
        </Field>
        <Field
          :label="meta('irrigationDecisionHysteresisPct').label"
          :hint="meta('irrigationDecisionHysteresisPct').hint"
        >
          <input
            v-bind="numAttrs"
            :title="meta('irrigationDecisionHysteresisPct').details"
            :value="waterForm.irrigationDecisionHysteresisPct ?? 0"
            @input="upd('irrigationDecisionHysteresisPct', toNum($event))"
          />
        </Field>
        <Field
          :label="meta('irrigationDecisionSpreadAlertThresholdPct').label"
          :hint="meta('irrigationDecisionSpreadAlertThresholdPct').hint"
        >
          <input
            v-bind="numAttrs"
            :title="meta('irrigationDecisionSpreadAlertThresholdPct').details"
            :value="waterForm.irrigationDecisionSpreadAlertThresholdPct ?? 0"
            @input="upd('irrigationDecisionSpreadAlertThresholdPct', toNum($event))"
          />
        </Field>
      </div>
    </template>

    <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]">
      Recovery / повторы
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5">
      <Field
        :label="meta('irrigationRecoveryMaxContinueAttempts').label"
        :hint="meta('irrigationRecoveryMaxContinueAttempts').hint"
      >
        <input
          v-bind="numAttrs"
          :title="meta('irrigationRecoveryMaxContinueAttempts').details"
          :value="waterForm.irrigationRecoveryMaxContinueAttempts ?? 0"
          @input="upd('irrigationRecoveryMaxContinueAttempts', toInt($event))"
        />
      </Field>
      <Field
        :label="meta('irrigationRecoveryTimeoutSeconds').label"
        :hint="meta('irrigationRecoveryTimeoutSeconds').hint"
      >
        <input
          v-bind="numAttrs"
          :title="meta('irrigationRecoveryTimeoutSeconds').details"
          :value="waterForm.irrigationRecoveryTimeoutSeconds ?? 0"
          @input="upd('irrigationRecoveryTimeoutSeconds', toInt($event))"
        />
      </Field>
      <Field
        :label="meta('irrigationMaxSetupReplays').label"
        :hint="meta('irrigationMaxSetupReplays').hint"
      >
        <input
          v-bind="numAttrs"
          :title="meta('irrigationMaxSetupReplays').details"
          :value="waterForm.irrigationMaxSetupReplays ?? 0"
          @input="upd('irrigationMaxSetupReplays', toInt($event))"
        />
      </Field>
    </div>

    <Hint :show="showHints">
      SMART soil v1 принимает решение о поливе по выборке датчиков
      влажности. Без сенсора используйте <span class="font-mono">task</span>
      (по времени).
    </Hint>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import { Field, Hint, ToggleField } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import { createMetaResolver, toInt, toNum, type FieldMeta } from './sharedFormUtils'

const props = defineProps<{ waterForm: WaterFormState }>()
const emit = defineEmits<{ (e: 'update:waterForm', next: WaterFormState): void }>()

const { showHints } = useLaunchPreferences()

const smart = computed(
  () => props.waterForm.irrigationDecisionStrategy === 'smart_soil_v1',
)

const inputCls =
  'block w-full h-8 rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none transition-[border-color,box-shadow,background-color] duration-150 focus:border-brand focus:ring-2 focus:ring-brand-soft focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand-soft'
const numAttrs = { class: inputCls, type: 'number' }

const IRRIGATION_FIELD_META: Partial<Record<keyof WaterFormState, FieldMeta>> = {
  intervalMinutes: {
    label: 'Интервал полива, мин',
    hint: 'Период запуска полива',
    details: 'Определяет периодичность полива в стратегии "По времени".',
  },
  durationSeconds: {
    label: 'Длительность полива, сек',
    hint: 'Время одного полива',
    details: 'Сколько секунд длится один запуск полива.',
  },
  correctionDuringIrrigation: {
    label: 'Разрешить коррекцию во время полива',
    hint: 'Параллельная коррекция pH/EC',
    details: 'Если включено, корректировки pH/EC могут выполняться во время активного полива.',
  },
  irrigationAutoReplayAfterSetup: {
    label: 'Автоповтор полива после setup',
    hint: 'Автовосстановление цикла',
    details: 'После восстановления setup полив может автоматически повториться без ручного старта.',
  },
  irrigationDecisionLookbackSeconds: {
    label: 'Окно анализа SMART, сек',
    hint: 'Глубина выборки датчиков',
    details: 'За какой период SMART-algorithm анализирует данные влажности перед решением о поливе.',
  },
  irrigationDecisionMinSamples: {
    label: 'Минимум измерений SMART',
    hint: 'Порог качества данных',
    details: 'Минимальное число валидных samples для принятия SMART-решения.',
  },
  irrigationDecisionStaleAfterSeconds: {
    label: 'Устаревание данных SMART, сек',
    hint: 'Макс. возраст данных',
    details: 'После этого времени данные считаются устаревшими и SMART-решение блокируется.',
  },
  irrigationDecisionHysteresisPct: {
    label: 'Гистерезис SMART, %',
    hint: 'Защита от дрожания решения',
    details: 'Снижает частые переключения решения около порога влажности.',
  },
  irrigationDecisionSpreadAlertThresholdPct: {
    label: 'Порог разброса датчиков, %',
    hint: 'Алерт на расхождение сенсоров',
    details: 'Если разброс влажности между сенсорами выше порога, генерируется диагностический сигнал.',
  },
  irrigationRecoveryMaxContinueAttempts: {
    label: 'Макс. попыток recovery-continue',
    hint: 'Лимит повторов восстановления',
    details: 'Сколько раз runtime пробует продолжить полив после recovery before fail-closed.',
  },
  irrigationRecoveryTimeoutSeconds: {
    label: 'Таймаут recovery, сек',
    hint: 'Ожидание шага восстановления',
    details: 'Предельное время шага восстановления полива перед ошибкой.',
  },
  irrigationMaxSetupReplays: {
    label: 'Макс. повторов setup',
    hint: 'Лимит перезапуска подготовки',
    details: 'Ограничивает число повторных setup-проходов до блокировки сценария.',
  },
}
const meta = createMetaResolver<WaterFormState>(IRRIGATION_FIELD_META, {
  label: '',
  hint: 'Параметр режима полива',
  details: 'Параметр влияет на расписание, SMART-решение или recovery полива.',
})

function upd<K extends keyof WaterFormState>(key: K, value: WaterFormState[K]) {
  emit('update:waterForm', { ...props.waterForm, [key]: value })
}
</script>
