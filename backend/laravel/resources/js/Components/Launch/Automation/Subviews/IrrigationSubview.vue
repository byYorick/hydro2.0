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
          По влажности субстрата
        </Button>
      </div>
    </div>

    <p
      data-testid="irrigation-strategy-caption"
      class="m-0 text-xs leading-snug text-[var(--text-muted)]"
    >
      {{ smart
        ? 'По расписанию система проверяет влажность всех активных датчиков. Полив разрешается ниже порога из рецепта; без свежих корректных измерений проверка заканчивается пропуском полива.'
        : 'Полив запускается по расписанию без проверки влажности субстрата. Аварийная остановка, ограничения уровня и температурная защита продолжают действовать.' }}
    </p>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 items-center">
      <Field
        :label="meta('intervalMinutes').label"
        :hint="meta('intervalMinutes').hint"
        required
      >
        <TextField
          v-bind="numAttrs"
          :title="meta('intervalMinutes').details"
          :model-value="waterForm.intervalMinutes"
          @input="upd('intervalMinutes', toInt($event))"
        />
      </Field>
      <Field
        :label="meta('durationSeconds').label"
        :hint="meta('durationSeconds').hint"
        required
      >
        <TextField
          v-bind="numAttrs"
          :title="meta('durationSeconds').details"
          :model-value="waterForm.durationSeconds"
          @input="upd('durationSeconds', toInt($event))"
        />
      </Field>
      <ToggleField
        :model-value="waterForm.correctionDuringIrrigation"
        :label="meta('correctionDuringIrrigation').label"
        :title="meta('correctionDuringIrrigation').details"
        @update:model-value="onCorrectionToggle"
      />
      <Field
        v-if="waterForm.correctionDuringIrrigation"
        :label="meta('irrigationEcComponent').label"
        :hint="meta('irrigationEcComponent').hint"
      >
        <SelectField
         
          :title="meta('irrigationEcComponent').details"
          :model-value="ecComponentSelectValue"
          @change="onEcComponentChange"
        >
          <option value="none">
            Только pH, без коррекции EC
          </option>
          <option value="calcium">
            pH и кальций
          </option>
          <option value="npk">
            pH и NPK
          </option>
        </SelectField>
      </Field>
    </div>

    <div
      v-if="smart"
      class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]"
    >
      Данные влажности для решения
    </div>
    <div
      v-if="smart"
      class="grid grid-cols-1 md:grid-cols-3 gap-2.5"
    >
      <Field
        :label="meta('irrigationDecisionLookbackSeconds').label"
        :hint="meta('irrigationDecisionLookbackSeconds').hint"
      >
        <TextField
          v-bind="numAttrs"
          data-testid="irrigation-decision-lookback"
          :title="meta('irrigationDecisionLookbackSeconds').details"
          :model-value="waterForm.irrigationDecisionLookbackSeconds ?? 0"
          @input="upd('irrigationDecisionLookbackSeconds', toInt($event))"
        />
      </Field>
      <Field
        :label="meta('irrigationDecisionStaleAfterSeconds').label"
        :hint="meta('irrigationDecisionStaleAfterSeconds').hint"
      >
        <TextField
          v-bind="numAttrs"
          data-testid="irrigation-decision-stale"
          :title="meta('irrigationDecisionStaleAfterSeconds').details"
          :model-value="waterForm.irrigationDecisionStaleAfterSeconds ?? 0"
          @input="upd('irrigationDecisionStaleAfterSeconds', toInt($event))"
        />
      </Field>
      <Field
        :label="meta('irrigationDecisionHysteresisPct').label"
        :hint="meta('irrigationDecisionHysteresisPct').hint"
      >
        <TextField
          v-bind="numAttrs"
          data-testid="irrigation-decision-hysteresis"
          :title="meta('irrigationDecisionHysteresisPct').details"
          :model-value="waterForm.irrigationDecisionHysteresisPct ?? 0"
          @input="upd('irrigationDecisionHysteresisPct', toNum($event))"
        />
      </Field>
    </div>
    <template v-if="smart">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        <Field
          :label="meta('irrigationDecisionMinSamples').label"
          :hint="meta('irrigationDecisionMinSamples').hint"
        >
          <TextField
            v-bind="numAttrs"
            :title="meta('irrigationDecisionMinSamples').details"
            :model-value="waterForm.irrigationDecisionMinSamples ?? 0"
            @input="upd('irrigationDecisionMinSamples', toInt($event))"
          />
        </Field>
        <Field
          :label="meta('irrigationDecisionSpreadAlertThresholdPct').label"
          :hint="meta('irrigationDecisionSpreadAlertThresholdPct').hint"
        >
          <TextField
            v-bind="numAttrs"
            :title="meta('irrigationDecisionSpreadAlertThresholdPct').details"
            :model-value="waterForm.irrigationDecisionSpreadAlertThresholdPct ?? 0"
            @input="upd('irrigationDecisionSpreadAlertThresholdPct', toNum($event))"
          />
        </Field>
      </div>
    </template>

    <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] pb-1 border-b border-dashed border-[var(--border-muted)]">
      Повтор полива после подготовки раствора
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 items-center">
      <Field
        :label="meta('irrigationMaxSetupReplays').label"
        :hint="meta('irrigationMaxSetupReplays').hint"
      >
        <TextField
          v-bind="numAttrs"
          :title="meta('irrigationMaxSetupReplays').details"
          :model-value="waterForm.irrigationMaxSetupReplays ?? 0"
          @input="upd('irrigationMaxSetupReplays', toInt($event))"
        />
      </Field>
      <ToggleField
        :model-value="!!waterForm.irrigationAutoReplayAfterSetup"
        :label="meta('irrigationAutoReplayAfterSetup').label"
        :title="meta('irrigationAutoReplayAfterSetup').details"
        @update:model-value="(v) => upd('irrigationAutoReplayAfterSetup', v)"
      />
    </div>

    <Hint :show="showHints">
      При включённой коррекции pH проверяется всегда. Коррекцию EC можно отключить или выбрать кальций либо NPK.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import SelectField from '@/Components/SelectField.vue'

import TextField from '@/Components/TextField.vue'

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

const ecComponentSelectValue = computed(() => {
  const raw = props.waterForm.irrigationEcComponent
  return raw === 'npk' || raw === 'calcium' ? raw : 'none'
})

const numAttrs = { type: 'number' }

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
    label: 'Коррекция раствора во время полива',
    hint: 'pH и, по выбору, EC',
    details: 'Контролировать pH во время полива. Коррекция EC включается отдельно выбором кальция или NPK.',
  },
  irrigationEcComponent: {
    label: 'EC-компонент на поливе',
    hint: 'Только pH, кальций или NPK',
    details: '«Только pH» сохраняет EC без коррекции. Для коррекции EC выберите кальций или NPK; pH проверяется в любом из этих режимов.',
  },
  irrigationAutoReplayAfterSetup: {
    label: 'Повторить полив после подготовки раствора',
    hint: 'Автовосстановление цикла',
    details: 'После восстановления уровня и подготовки раствора полив может повториться автоматически в пределах заданного числа повторов.',
  },
  irrigationDecisionLookbackSeconds: {
    label: 'История влажности, сек',
    hint: 'Глубина выборки датчиков',
    details: 'За какой период брать корректные измерения влажности перед решением о поливе.',
  },
  irrigationDecisionMinSamples: {
    label: 'Желаемое число измерений',
    hint: 'Порог качества данных',
    details: 'Если корректных свежих измерений меньше этого числа, решение всё равно принимается, но с предупреждением о пониженной достоверности. Это не запрет полива.',
  },
  irrigationDecisionStaleAfterSeconds: {
    label: 'Максимальный возраст измерения, сек',
    hint: 'Макс. возраст данных',
    details: 'Если у любого активного датчика нет свежих корректных данных, полив по влажности пропускается. Задача не считается аварийной.',
  },
  irrigationDecisionHysteresisPct: {
    label: 'Запас ниже нижней границы, п.п.',
    hint: 'Защита от дрожания решения',
    details: 'Полив разрешается ниже нижней границы влажности минус этот запас. Например: граница 40%, запас 2 п.п. — разрешение при влажности ниже 38%.',
  },
  irrigationDecisionSpreadAlertThresholdPct: {
    label: 'Допустимый разброс датчиков, п.п.',
    hint: 'Алерт на расхождение сенсоров',
    details: 'Если разница между средними показаниями датчиков выше порога, появляется предупреждение. Само предупреждение не запрещает полив.',
  },
  irrigationMaxSetupReplays: {
    label: 'Максимум повторов полива после подготовки',
    hint: 'Лимит перезапуска подготовки',
    details: 'Сколько раз автоматически повторять полив после восстановления уровня и подготовки раствора.',
  },
}
const meta = createMetaResolver<WaterFormState>(IRRIGATION_FIELD_META, {
  label: '',
  hint: 'Параметр режима полива',
  details: 'Параметр влияет на расписание, SMART-решение или повторы setup полива.',
})

function upd<K extends keyof WaterFormState>(key: K, value: WaterFormState[K]) {
  emit('update:waterForm', { ...props.waterForm, [key]: value })
}

function onCorrectionToggle(enabled: boolean) {
  const next: WaterFormState = {
    ...props.waterForm,
    correctionDuringIrrigation: enabled,
  }
  if (enabled && next.irrigationEcComponent !== 'npk' && next.irrigationEcComponent !== 'calcium') {
    next.irrigationEcComponent = 'none'
  }
  emit('update:waterForm', next)
}

function onEcComponentChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (value === 'none' || value === 'calcium' || value === 'npk') {
    upd('irrigationEcComponent', value)
  }
}
</script>
