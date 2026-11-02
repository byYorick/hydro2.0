<template>
  <form
    class="flex flex-col gap-3"
    data-testid="pid-config-form"
    @submit.prevent="onSubmit"
  >
    <!-- ACTION BAR -->
    <div class="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
      <div class="flex flex-wrap items-center gap-1.5 min-w-0">
        <Chip
          v-if="isDirty"
          tone="brand"
        >
          <template #icon>
            <span class="inline-block w-1.5 h-1.5 rounded-full bg-brand"></span>
          </template>
          изменено
        </Chip>
        <Chip tone="brand">
          Контур <span class="font-mono ml-1">{{ selectedType.toUpperCase() }}</span>
        </Chip>
        <Chip tone="neutral">
          пресет: <span class="font-mono ml-1">{{ selectedPresetName }}</span>
        </Chip>
        <Chip
          v-if="phaseTargetAvailable"
          tone="growth"
        >
          цель: <span class="font-mono ml-1">{{ phaseTargetDisplay }}</span>
        </Chip>
        <Chip
          v-else
          tone="alert"
        >
          нет цели в рецепте
        </Chip>
        <span class="text-[11px] font-mono text-[var(--text-dim)] ml-1">
          pH {{ savedBadge('ph') }} · EC {{ savedBadge('ec') }}
        </span>
      </div>
      <div class="flex items-center gap-1.5 flex-wrap">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          data-testid="pid-config-toggle-advanced"
          :disabled="loading"
          @click="showAdvanced = !showAdvanced"
        >
          {{ showAdvanced ? 'Скрыть продвинутые' : 'Продвинутые настройки' }}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          :disabled="loading"
          @click="onReset"
        >
          ↺ Откатить
        </Button>
        <Button
          type="submit"
          size="sm"
          variant="primary"
          data-testid="pid-config-save"
          class="w-full sm:w-auto"
          :disabled="loading || disabled || !phaseTargetAvailable || Boolean(validationError)"
        >
          {{
            loading
              ? 'Сохранение…'
              : needsConfirmation && !confirmed
                ? 'Подтвердить'
                : `Сохранить ${selectedType.toUpperCase()}`
          }}
        </Button>
      </div>
    </div>

    <!-- PRESET STRIP -->
    <PresetPillStrip
      :items="presetPillItems"
      :model-value="selectedPresetKey"
      :description="selectedPresetDescription"
      :disabled="disabled || presetSwitching || loading"
      test-id="pid-config-preset-strip"
      @select="onPresetPillClick"
    />
    <p
      v-if="validationError"
      class="text-sm text-status-critical"
      role="alert"
      data-testid="pid-config-validation-error"
    >
      {{ validationError }}
    </p>

    <!-- LOOP TABS -->
    <div class="flex gap-0.5 border-b border-[var(--border-muted)]">
      <button
        type="button"
        data-testid="pid-config-type-ph"
        :class="tabClass('ph')"
        @click="selectType('ph')"
      >
        <span>Контур pH</span>
        <Chip
          v-if="pidConfigSavedState.ph"
          tone="growth"
        >
          сохранено
        </Chip>
        <Chip
          v-else
          tone="neutral"
        >
          нет переопределения
        </Chip>
      </button>
      <button
        type="button"
        data-testid="pid-config-type-ec"
        :class="tabClass('ec')"
        @click="selectType('ec')"
      >
        <span>Контур EC</span>
        <Chip
          v-if="pidConfigSavedState.ec"
          tone="growth"
        >
          сохранено
        </Chip>
        <Chip
          v-else
          tone="neutral"
        >
          нет переопределения
        </Chip>
      </button>
    </div>

    <!-- BANNERS -->
    <div
      v-if="!phaseTargetAvailable"
      class="rounded-md border border-alert bg-alert-soft/40 px-3 py-2 text-sm text-alert flex items-start gap-2"
      data-testid="pid-config-phase-target-missing"
    >
      <span class="font-mono shrink-0">!</span>
      <span>
        В активной фазе рецепта нет целевого значения
        <strong>{{ selectedType.toUpperCase() }}</strong>.
        PID-конфиг не может быть сохранён — runtime перейдёт в fail-closed.
      </span>
    </div>

    <div
      v-if="needsConfirmation"
      class="rounded-md border border-warn bg-warn-soft/40 px-3 py-2 text-sm text-warn flex items-start gap-2 break-words"
    >
      <span class="font-mono shrink-0">⚠</span>
      <span>
        Агрессивные настройки (<code class="font-mono">Kp &gt; 200</code>).
        <span v-if="!confirmed">Нажмите «Подтвердить» ещё раз.</span>
      </span>
    </div>

    <!-- SECTIONS -->
    <details
      class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] overflow-hidden"
      :open="openSections.has('zones')"
      @toggle="toggleSection('zones', $event)"
    >
      <summary :class="summaryCls">
        <span class="text-sm font-semibold">Зоны отклонения</span>
        <span class="text-[11px] text-[var(--text-dim)]">
          мёртвая / ближняя / дальняя · когда PID реагирует
        </span>
      </summary>
      <div class="p-3 grid grid-cols-1 md:grid-cols-4 gap-3">
        <Field
          compact
          label="Цель"
          :hint="phaseTargetAvailable ? phaseTargetSourceHint : 'runtime не подставит значения по умолчанию'"
        >
          <template #right>
            <span class="text-[10px] text-[var(--text-dim)] flex items-center gap-1">
              <Ic
                name="lock"
                size="sm"
              />
              из рецепта
            </span>
          </template>
          <TextField
            :disabled="disabled || loading"
            :value="phaseTargetDisplay"
            data-testid="pid-config-input-target"
            type="number"
            :step="0.01"
            :min="selectedType === 'ph' ? 4 : 0"
            :max="selectedType === 'ph' ? 9 : 10"
            :placeholder="`Цель ${selectedType.toUpperCase()} не задана`"
            readonly
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
        <Field
          compact
          label="Мёртвая зона"
          hint="0..2 · игнорируется мелкое отклонение"
        >
          <template
            v-if="isFieldDirty('dead_zone')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.dead_zone"
            :disabled="disabled || loading"
            type="number"
            step="0.01"
            min="0"
            max="2"
            :title="fieldHelp('dead_zone')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
        <Field
          compact
          label="Ближняя зона"
          hint="должна быть > мёртвой"
        >
          <template
            v-if="isFieldDirty('close_zone')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.close_zone"
            :disabled="disabled || loading"
            type="number"
            step="0.01"
            min="0"
            max="5"
            :title="fieldHelp('close_zone')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
        <Field
          compact
          label="Дальняя зона"
          hint="должна быть > ближней"
        >
          <template
            v-if="isFieldDirty('far_zone')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.far_zone"
            :disabled="disabled || loading"
            type="number"
            step="0.01"
            min="0"
            max="10"
            :title="fieldHelp('far_zone')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
      </div>
    </details>

    <details
      v-if="showAdvanced"
      class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] overflow-hidden"
      :open="openSections.has('close')"
      @toggle="toggleSection('close', $event)"
    >
      <summary :class="summaryCls">
        <span class="text-sm font-semibold">Коэффициенты ближней зоны</span>
        <span class="text-[11px] text-[var(--text-dim)]">мягкая коррекция около target</span>
      </summary>
      <div class="p-3 grid grid-cols-1 md:grid-cols-3 gap-3">
        <Field
          compact
          label="Kp"
        >
          <template
            v-if="isCoeffDirty('close', 'kp')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.zone_coeffs.close.kp"
            :disabled="disabled || loading"
            type="number"
            step="0.1"
            min="0"
            max="1000"
            :title="fieldHelp('close.kp')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
        <Field
          compact
          label="Ki"
        >
          <template
            v-if="isCoeffDirty('close', 'ki')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.zone_coeffs.close.ki"
            :disabled="disabled || loading"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :title="fieldHelp('close.ki')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
        <Field
          compact
          label="Kd"
        >
          <template
            v-if="isCoeffDirty('close', 'kd')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.zone_coeffs.close.kd"
            :disabled="disabled || loading"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :title="fieldHelp('close.kd')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
      </div>
    </details>

    <details
      v-if="showAdvanced"
      class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] overflow-hidden"
      :open="openSections.has('far')"
      @toggle="toggleSection('far', $event)"
    >
      <summary :class="summaryCls">
        <span class="text-sm font-semibold">Коэффициенты дальней зоны</span>
        <span class="text-[11px] text-[var(--text-dim)]">агрессивная коррекция при большом отклонении</span>
      </summary>
      <div class="p-3 grid grid-cols-1 md:grid-cols-3 gap-3">
        <Field
          compact
          label="Kp"
        >
          <template
            v-if="isCoeffDirty('far', 'kp')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.zone_coeffs.far.kp"
            :disabled="disabled || loading"
            type="number"
            step="0.1"
            min="0"
            max="1000"
            :title="fieldHelp('far.kp')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
        <Field
          compact
          label="Ki"
        >
          <template
            v-if="isCoeffDirty('far', 'ki')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.zone_coeffs.far.ki"
            :disabled="disabled || loading"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :title="fieldHelp('far.ki')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
        <Field
          compact
          label="Kd"
        >
          <template
            v-if="isCoeffDirty('far', 'kd')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.zone_coeffs.far.kd"
            :disabled="disabled || loading"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :title="fieldHelp('far.kd')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
      </div>
    </details>

    <details
      v-if="showAdvanced"
      class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] overflow-hidden"
      :open="openSections.has('integral')"
      @toggle="toggleSection('integral', $event)"
    >
      <summary :class="summaryCls">
        <span class="text-sm font-semibold">Предел интеграла</span>
        <span class="text-[11px] text-[var(--text-dim)]">защита от накопления ошибки</span>
      </summary>
      <div class="p-3 grid grid-cols-1 md:grid-cols-3 gap-3">
        <Field
          compact
          label="Предел интеграла"
          hint="pH обычно 12–20 · EC 20–100"
        >
          <template
            v-if="isFieldDirty('max_integral')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <TextField
            v-model.number="form.max_integral"
            :disabled="disabled || loading"
            type="number"
            step="1"
            min="1"
            max="500"
            :title="fieldHelp('max_integral')"
            input-class="font-mono"
            class="max-w-[8.5rem]"
          />
        </Field>
      </div>
    </details>

    <!-- PREVIEW -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
      <Stat
        label="Контур"
        :value="selectedType.toUpperCase()"
        mono
        tone="brand"
      />
      <Stat
        label="Цель"
        :value="phaseTargetAvailable ? phaseTargetDisplay : '—'"
        mono
      />
      <Stat
        label="мёртв · ближн · дальн"
        :value="`${form.dead_zone} · ${form.close_zone} · ${form.far_zone}`"
        mono
      />
      <Stat
        label="Предел интеграла"
        :value="form.max_integral"
        mono
      />
    </div>
  </form>
  <ConfirmModal
    :open="confirmOpen"
    :title="confirmTitle"
    :message="confirmMessage"
    confirm-variant="danger"
    @close="closeConfirm"
    @confirm="acceptConfirm"
  />
</template>

<script setup lang="ts">
import { DEFAULT_CONFIGS, cloneConfig, normalizeConfig, pidConfigError } from '@/utils/pidConfigDraft'
import { computed, onMounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { Chip, Field, Stat } from '@/Components/Shared/Primitives'
import PresetPillStrip, { type PresetPillItem, type PresetPillKey } from '@/Components/Shared/PresetPillStrip.vue'
import Ic from '@/Components/Icons/Ic.vue'
import { resolveRecipePhasePidTargets, type RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import { usePidConfig } from '@/composables/usePidConfig'
import { api } from '@/services/api'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import {
  normalizeRuntimeTuningBundleDocument,
  RUNTIME_TUNING_BUNDLE_NAMESPACE,
  selectedRuntimeTuningPreset,
  withPidOverride,
  type RuntimeTuningBundlePayload,
} from '@/composables/runtimeTuningBundle'
import { logger } from '@/utils/logger'
import type { PidConfig, PidConfigWithMeta } from '@/types/PidConfig'
import TextField from '@/Components/TextField.vue'

const props = withDefaults(
  defineProps<{
    zoneId: number
    phaseTargets?: RecipePhasePidTargets | null
    disabled?: boolean
  }>(),
  { phaseTargets: null, disabled: false },
)

const emit = defineEmits<{
  saved: [config: PidConfigWithMeta]
}>()

const summaryCls =
  'flex items-baseline gap-2 px-3 py-2 cursor-pointer bg-[var(--bg-elevated)] border-b border-[var(--border-muted)] hover:bg-[var(--bg-surface-strong)] [&::-webkit-details-marker]:hidden [&::marker]:content-none'

function tabClass(type: 'ph' | 'ec'): string {
  const active = selectedType.value === type
  return [
    'flex items-center gap-2 px-3 py-2 -mb-px text-sm font-medium border-b-2 transition-colors cursor-pointer',
    active
      ? 'border-brand text-brand'
      : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]',
  ].join(' ')
}

const FIELD_HELP: Record<string, string> = {
  target: 'Целевое значение PID-контура. Берётся только из актуальной recipe phase и не сохраняется в zone.pid.*.',
  dead_zone: 'Зона, в которой отклонение считается слишком малым для dosing-реакции. Помогает избежать дрожания регулятора.',
  close_zone: 'Окно умеренного отклонения рядом с target. В этой зоне обычно используются более мягкие коэффициенты PID.',
  far_zone: 'Окно крупного отклонения от target. В нём runtime может использовать более агрессивные коэффициенты.',
  'close.kp': 'Пропорциональный коэффициент для близкой зоны. Чем выше, тем сильнее реакция на текущую ошибку.',
  'close.ki': 'Интегральный коэффициент для близкой зоны. Компенсирует накопленную систематическую ошибку.',
  'close.kd': 'Дифференциальный коэффициент для близкой зоны. Смягчает перерегулирование по скорости изменения ошибки.',
  'far.kp': 'Пропорциональный коэффициент для дальней зоны, когда отклонение от target ещё велико.',
  'far.ki': 'Интегральный коэффициент для дальней зоны. Обычно требует осторожной настройки, чтобы не накопить лишнюю дозу.',
  'far.kd': 'Дифференциальный коэффициент для дальней зоны. Помогает стабилизировать aggressive-коррекцию.',
  max_integral: 'DEPRECATED для AE3: runtime читает controllers.*.max_integral из zone.correction. Поле zone.pid сохраняется для совместимости payload, на clamp интеграла не влияет.',
}

function fieldHelp(key: string): string {
  return FIELD_HELP[key] ?? 'Параметр PID-контура коррекции.'
}

const selectedType = ref<'ph' | 'ec'>('ph')
const { open: confirmOpen, title: confirmTitle, message: confirmMessage, ask, close: closeConfirm, confirm: acceptConfirm } = useConfirmDialog()
const confirmed = ref(false)
const showAdvanced = ref(false)
const presetSwitching = ref(false)
const resolvedPhaseTargets = ref<RecipePhasePidTargets | null>(props.phaseTargets)
const pidConfigSavedState = ref<Record<'ph' | 'ec', boolean>>({ ph: false, ec: false })
const automationConfig = useAutomationConfig()
const { getPidConfig, getAllPidConfigs, updatePidConfig, loading } = usePidConfig()
const runtimeTuningBundle = ref<RuntimeTuningBundlePayload | null>(null)
const selectedPresetKey = ref('system_default')

const form = ref<PidConfig>(cloneConfig(DEFAULT_CONFIGS.ph))
const validationError = computed(() => pidConfigError(form.value))
const lastSavedForm = ref<PidConfig>(cloneConfig(DEFAULT_CONFIGS.ph))
const openSections = ref<Set<string>>(new Set(['zones']))

const phaseTarget = computed(() => resolvedPhaseTargets.value?.[selectedType.value] ?? null)
const phaseTargetAvailable = computed(() => typeof phaseTarget.value === 'number' && Number.isFinite(phaseTarget.value))
const phaseTargetDisplay = computed(() => phaseTargetAvailable.value ? String(phaseTarget.value) : '')
const phaseTargetSourceHint = computed(() => {
  const phaseLabel = resolvedPhaseTargets.value?.phaseLabel
  const base = phaseLabel ? `Цель взята из фазы рецепта «${phaseLabel}».` : 'Цель взята из актуальной фазы рецепта.'
  return `${base} Ручное редактирование запрещено, в zone.pid.* значение не сохраняется.`
})
const selectedPreset = computed(() => selectedRuntimeTuningPreset(runtimeTuningBundle.value))
const presetOptions = computed(() => runtimeTuningBundle.value?.presets ?? [])
const selectedPresetName = computed(() => selectedPreset.value?.name ?? 'Системный пресет')
const selectedPresetDescription = computed(() => selectedPreset.value?.description ?? 'Канонические стартовые значения PID и калибровки процесса для зоны.')
const presetPillItems = computed<PresetPillItem[]>(() =>
  presetOptions.value.map((preset) => ({
    key: preset.key,
    label: preset.key === 'system_default' ? 'Системный пресет' : preset.name,
    meta: preset.key === 'system_default' ? 'system' : 'custom',
    locked: preset.key === 'system_default',
    title: preset.description ?? undefined,
    testId: `pid-config-preset-${preset.key}`,
  })),
)

const needsConfirmation = computed(
  () => form.value.zone_coeffs.close.kp > 200 || form.value.zone_coeffs.far.kp > 200,
)

const isDirty = computed(() => {
  const a = form.value
  const b = lastSavedForm.value
  return (
    a.dead_zone !== b.dead_zone ||
    a.close_zone !== b.close_zone ||
    a.far_zone !== b.far_zone ||
    a.max_integral !== b.max_integral ||
    a.zone_coeffs.close.kp !== b.zone_coeffs.close.kp ||
    a.zone_coeffs.close.ki !== b.zone_coeffs.close.ki ||
    a.zone_coeffs.close.kd !== b.zone_coeffs.close.kd ||
    a.zone_coeffs.far.kp !== b.zone_coeffs.far.kp ||
    a.zone_coeffs.far.ki !== b.zone_coeffs.far.ki ||
    a.zone_coeffs.far.kd !== b.zone_coeffs.far.kd
  )
})

function isFieldDirty(key: 'dead_zone' | 'close_zone' | 'far_zone' | 'max_integral'): boolean {
  return form.value[key] !== lastSavedForm.value[key]
}

function isCoeffDirty(zone: 'close' | 'far', coef: 'kp' | 'ki' | 'kd'): boolean {
  return form.value.zone_coeffs[zone][coef] !== lastSavedForm.value.zone_coeffs[zone][coef]
}

function savedBadge(type: 'ph' | 'ec'): string {
  return pidConfigSavedState.value[type] ? '✓' : '—'
}

function toggleSection(key: string, event: Event): void {
  const open = (event.target as HTMLDetailsElement).open
  const next = new Set(openSections.value)
  if (open) next.add(key)
  else next.delete(key)
  openSections.value = next
}

async function onPresetPillClick(key: PresetPillKey): Promise<void> {
  if (props.disabled || loading.value) return
  if (!runtimeTuningBundle.value || key === null) return
  const presetKey = String(key)
  if (selectedPresetKey.value === presetKey) return
  selectedPresetKey.value = presetKey
  await applySelectedPreset()
}

async function loadConfig() {
  try {
    const config = await getPidConfig(props.zoneId, selectedType.value)
    const preview = runtimeTuningBundle.value?.resolved_preview.pid?.[selectedType.value]
    const source = config?.config ?? preview ?? DEFAULT_CONFIGS[selectedType.value]
    const normalized = normalizeConfig(source, selectedType.value)
    form.value = normalized
    lastSavedForm.value = cloneConfig(normalized)
    pidConfigSavedState.value[selectedType.value] = Boolean(config)
    confirmed.value = false
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load PID config:', error)
    const fallback = cloneConfig(DEFAULT_CONFIGS[selectedType.value])
    form.value = fallback
    lastSavedForm.value = cloneConfig(fallback)
  }
}

async function loadStatuses(): Promise<void> {
  try {
    const configs = await getAllPidConfigs(props.zoneId)
    pidConfigSavedState.value = { ph: Boolean(configs.ph), ec: Boolean(configs.ec) }
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load PID status map:', error)
  }
}

async function loadRuntimeTuningBundle(): Promise<void> {
  try {
    const document = await automationConfig.getDocument<Record<string, unknown>>(
      'zone',
      props.zoneId,
      RUNTIME_TUNING_BUNDLE_NAMESPACE,
    )
    runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(document)
    selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load runtime tuning bundle:', error)
  }
}

async function persistRuntimeTuningBundle(nextBundle: RuntimeTuningBundlePayload): Promise<void> {
  const document = await automationConfig.updateDocument(
    'zone',
    props.zoneId,
    RUNTIME_TUNING_BUNDLE_NAMESPACE,
    nextBundle,
  )
  runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(document)
  selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
}

async function applySelectedPreset(): Promise<void> {
  if (!runtimeTuningBundle.value) return
  presetSwitching.value = true
  try {
    await persistRuntimeTuningBundle({
      ...runtimeTuningBundle.value,
      selected_preset_key: selectedPresetKey.value,
    })
    const selected = selectedRuntimeTuningPreset(runtimeTuningBundle.value)
    const previewPid = runtimeTuningBundle.value.resolved_preview?.pid
    const nextPh = normalizeConfig(
      (previewPid?.ph && Object.keys(previewPid.ph).length > 0)
        ? previewPid.ph
        : selected?.pid?.ph,
      'ph',
    )
    const nextEc = normalizeConfig(
      (previewPid?.ec && Object.keys(previewPid.ec).length > 0)
        ? previewPid.ec
        : selected?.pid?.ec,
      'ec',
    )

    await Promise.all([
      updatePidConfig(props.zoneId, 'ph', nextPh),
      updatePidConfig(props.zoneId, 'ec', nextEc),
    ])

    emit('saved', {
      type: selectedType.value,
      config: selectedType.value === 'ph' ? nextPh : nextEc,
      updated_by: null,
      updated_at: null,
      is_default: false,
    })
    await Promise.all([loadStatuses(), loadConfig()])
  } catch (error) {
    logger.error('[PidConfigForm] Failed to apply runtime tuning preset:', error)
  } finally {
    presetSwitching.value = false
  }
}

function extractCurrentPhase(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const payload = raw as Record<string, unknown>
  const activeGrowCycle = (
    payload.activeGrowCycle && typeof payload.activeGrowCycle === 'object' && !Array.isArray(payload.activeGrowCycle)
      ? payload.activeGrowCycle
      : (payload.active_grow_cycle && typeof payload.active_grow_cycle === 'object' && !Array.isArray(payload.active_grow_cycle)
        ? payload.active_grow_cycle
        : null)
  ) as Record<string, unknown> | null
  if (!activeGrowCycle) return null
  return activeGrowCycle.currentPhase ?? activeGrowCycle.current_phase ?? null
}

async function hydratePhaseTargets(): Promise<void> {
  if (props.phaseTargets) {
    resolvedPhaseTargets.value = props.phaseTargets
    return
  }
  try {
    const payload = await api.zones.getDetail(props.zoneId)
    resolvedPhaseTargets.value = resolveRecipePhasePidTargets(extractCurrentPhase(payload))
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load current recipe phase targets:', error)
    resolvedPhaseTargets.value = null
  }
}

async function onSubmit() {
  if (props.disabled || loading.value) return
  if (validationError.value) return
  if (!phaseTargetAvailable.value) {
    logger.warn('[PidConfigForm] Refusing to save PID config without recipe phase target', {
      zoneId: props.zoneId,
      pidType: selectedType.value,
    })
    return
  }
  if (needsConfirmation.value && !confirmed.value) {
    confirmed.value = true
    return
  }
  try {
    await updatePidConfig(props.zoneId, selectedType.value, form.value)
    if (runtimeTuningBundle.value) {
      await persistRuntimeTuningBundle(
        withPidOverride(
          runtimeTuningBundle.value,
          selectedType.value,
          form.value as unknown as Record<string, unknown>,
        ),
      )
    } else {
      logger.warn('[PidConfigForm] runtime_tuning_bundle is unavailable; saved only zone.pid.*', {
        zoneId: props.zoneId,
        pidType: selectedType.value,
      })
    }
    await Promise.all([loadStatuses(), loadConfig()])
    emit('saved', {
      type: selectedType.value,
      config: cloneConfig(form.value),
      updated_by: null,
      updated_at: null,
      is_default: false,
    })
    confirmed.value = false
  } catch (error) {
    logger.error('[PidConfigForm] Failed to save PID config:', error)
  }
}

function onReset() {
  void loadConfig()
}

async function selectType(next: 'ph' | 'ec'): Promise<void> {
  if (next === selectedType.value) return
  if (isDirty.value && !(await ask('Несохранённые изменения будут потеряны. Продолжить?', 'Несохранённые изменения'))) return
  selectedType.value = next
}

watch(selectedType, () => {
  void loadConfig()
})

watch(
  () => props.phaseTargets,
  (targets) => {
    resolvedPhaseTargets.value = targets
  },
)

watch(
  form,
  () => {
    if (confirmed.value) confirmed.value = false
  },
  { deep: true },
)

onMounted(() => {
  void hydratePhaseTargets()
  void loadRuntimeTuningBundle().then(() => Promise.all([loadStatuses(), loadConfig()]))
})
</script>
