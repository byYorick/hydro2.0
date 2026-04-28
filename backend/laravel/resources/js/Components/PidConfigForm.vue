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
            <span class="inline-block w-1.5 h-1.5 rounded-full bg-brand" />
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
          :disabled="loading || !phaseTargetAvailable"
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
    <div class="flex flex-wrap items-center gap-1.5">
      <span class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] mr-1">
        Пресет
      </span>
      <button
        v-for="preset in presetOptions"
        :key="preset.key"
        type="button"
        :data-testid="`pid-config-preset-${preset.key}`"
        :disabled="presetSwitching || loading"
        :class="[
          'h-7 px-2.5 rounded-md text-xs font-medium border transition-colors',
          selectedPresetKey === preset.key
            ? 'bg-brand text-white border-brand'
            : 'bg-[var(--bg-surface)] text-[var(--text-primary)] border-[var(--border-muted)] hover:border-brand',
          (presetSwitching || loading) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
        ]"
        @click="onPresetPillClick(preset.key)"
      >
        {{ preset.name }}
      </button>
      <span
        v-if="selectedPresetDescription"
        class="text-[11px] text-[var(--text-dim)] ml-1.5"
      >
        · {{ selectedPresetDescription }}
      </span>
    </div>

    <!-- LOOP TABS -->
    <div class="flex gap-0.5 border-b border-[var(--border-muted)]">
      <button
        type="button"
        data-testid="pid-config-type-ph"
        :class="tabClass('ph')"
        @click="selectedType = 'ph'"
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
        @click="selectedType = 'ec'"
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
          dead / close / far · границы реакций PID
        </span>
      </summary>
      <div class="p-3 grid grid-cols-1 md:grid-cols-4 gap-3">
        <Field
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
          <input
            :value="phaseTargetDisplay"
            data-testid="pid-config-input-target"
            type="number"
            :step="0.01"
            :min="selectedType === 'ph' ? 4 : 0"
            :max="selectedType === 'ph' ? 9 : 10"
            :class="readonlyCls"
            :placeholder="`Цель ${selectedType.toUpperCase()} не задана`"
            readonly
          >
        </Field>
        <Field
          label="Мёртвая зона"
          hint="0..2 · игнорируется мелкое отклонение"
        >
          <template
            v-if="isFieldDirty('dead_zone')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.dead_zone"
            type="number"
            step="0.01"
            min="0"
            max="2"
            :class="inputCls"
            :title="fieldHelp('dead_zone')"
          >
        </Field>
        <Field
          label="Ближняя зона"
          hint="должна быть > мёртвой"
        >
          <template
            v-if="isFieldDirty('close_zone')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.close_zone"
            type="number"
            step="0.01"
            min="0"
            max="5"
            :class="inputCls"
            :title="fieldHelp('close_zone')"
          >
        </Field>
        <Field
          label="Дальняя зона"
          hint="должна быть > ближней"
        >
          <template
            v-if="isFieldDirty('far_zone')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.far_zone"
            type="number"
            step="0.01"
            min="0"
            max="10"
            :class="inputCls"
            :title="fieldHelp('far_zone')"
          >
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
        <Field label="Kp">
          <template
            v-if="isCoeffDirty('close', 'kp')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.zone_coeffs.close.kp"
            type="number"
            step="0.1"
            min="0"
            max="1000"
            :class="inputCls"
            :title="fieldHelp('close.kp')"
          >
        </Field>
        <Field label="Ki">
          <template
            v-if="isCoeffDirty('close', 'ki')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.zone_coeffs.close.ki"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :class="inputCls"
            :title="fieldHelp('close.ki')"
          >
        </Field>
        <Field label="Kd">
          <template
            v-if="isCoeffDirty('close', 'kd')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.zone_coeffs.close.kd"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :class="inputCls"
            :title="fieldHelp('close.kd')"
          >
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
        <Field label="Kp">
          <template
            v-if="isCoeffDirty('far', 'kp')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.zone_coeffs.far.kp"
            type="number"
            step="0.1"
            min="0"
            max="1000"
            :class="inputCls"
            :title="fieldHelp('far.kp')"
          >
        </Field>
        <Field label="Ki">
          <template
            v-if="isCoeffDirty('far', 'ki')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.zone_coeffs.far.ki"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :class="inputCls"
            :title="fieldHelp('far.ki')"
          >
        </Field>
        <Field label="Kd">
          <template
            v-if="isCoeffDirty('far', 'kd')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.zone_coeffs.far.kd"
            type="number"
            step="0.01"
            min="0"
            max="100"
            :class="inputCls"
            :title="fieldHelp('far.kd')"
          >
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
        <span class="text-[11px] text-[var(--text-dim)]">max_integral · защита от переполнения</span>
      </summary>
      <div class="p-3 grid grid-cols-1 md:grid-cols-3 gap-3">
        <Field
          label="Предел интеграла"
          hint="pH обычно 12–20 · EC 20–100"
        >
          <template
            v-if="isFieldDirty('max_integral')"
            #right
          >
            <span class="text-brand font-mono text-xs">●</span>
          </template>
          <input
            v-model.number="form.max_integral"
            type="number"
            step="1"
            min="1"
            max="500"
            :class="inputCls"
            :title="fieldHelp('max_integral')"
          >
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
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import { Chip, Field, Stat } from '@/Components/Shared/Primitives'
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

const props = withDefaults(
  defineProps<{
    zoneId: number
    phaseTargets?: RecipePhasePidTargets | null
  }>(),
  { phaseTargets: null },
)

const emit = defineEmits<{
  saved: [config: PidConfigWithMeta]
}>()

const inputCls =
  'block w-full h-8 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none focus-visible:ring-2 focus-visible:ring-brand'
const readonlyCls =
  'block w-full h-8 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] text-[var(--text-muted)] px-2.5 text-sm font-mono outline-none cursor-not-allowed'
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
  max_integral: 'Предел накопления интегральной ошибки. Нужен, чтобы интегральная часть не разгоняла контур в saturation.',
}

function fieldHelp(key: string): string {
  return FIELD_HELP[key] ?? 'Параметр PID-контура коррекции.'
}

const DEFAULT_CONFIGS: Record<'ph' | 'ec', PidConfig> = {
  ph: {
    dead_zone: 0.04,
    close_zone: 0.18,
    far_zone: 0.65,
    zone_coeffs: {
      close: { kp: 0.18, ki: 0.01, kd: 0.0 },
      far: { kp: 0.28, ki: 0.015, kd: 0.0 },
    },
    max_integral: 12.0,
  },
  ec: {
    dead_zone: 0.06,
    close_zone: 0.25,
    far_zone: 0.9,
    zone_coeffs: {
      close: { kp: 0.35, ki: 0.02, kd: 0.0 },
      far: { kp: 0.55, ki: 0.03, kd: 0.0 },
    },
    max_integral: 20.0,
  },
}

const selectedType = ref<'ph' | 'ec'>('ph')
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

async function onPresetPillClick(key: string): Promise<void> {
  if (!runtimeTuningBundle.value) return
  if (selectedPresetKey.value === key) return
  selectedPresetKey.value = key
  await applySelectedPreset()
}

function cloneConfig(config: PidConfig): PidConfig {
  return JSON.parse(JSON.stringify(config)) as PidConfig
}

function toNumberOr(value: unknown, fallback: number): number {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

function normalizeConfig(raw: Partial<PidConfig> | null | undefined, type: 'ph' | 'ec'): PidConfig {
  const defaults = DEFAULT_CONFIGS[type]
  const closeRaw: Partial<PidConfig['zone_coeffs']['close']> = raw?.zone_coeffs?.close ?? {}
  const farRaw: Partial<PidConfig['zone_coeffs']['far']> = raw?.zone_coeffs?.far ?? {}

  return {
    dead_zone: toNumberOr(raw?.dead_zone, defaults.dead_zone),
    close_zone: toNumberOr(raw?.close_zone, defaults.close_zone),
    far_zone: toNumberOr(raw?.far_zone, defaults.far_zone),
    zone_coeffs: {
      close: {
        kp: toNumberOr(closeRaw.kp, defaults.zone_coeffs.close.kp),
        ki: toNumberOr(closeRaw.ki, defaults.zone_coeffs.close.ki),
        kd: toNumberOr(closeRaw.kd, defaults.zone_coeffs.close.kd),
      },
      far: {
        kp: toNumberOr(farRaw.kp, defaults.zone_coeffs.far.kp),
        ki: toNumberOr(farRaw.ki, defaults.zone_coeffs.far.ki),
        kd: toNumberOr(farRaw.kd, defaults.zone_coeffs.far.kd),
      },
    },
    max_integral: toNumberOr(raw?.max_integral, defaults.max_integral),
  }
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

watch(selectedType, (next, prev) => {
  if (isDirty.value && prev && next !== prev) {
    const proceed = window.confirm('Несохранённые изменения будут потеряны. Продолжить?')
    if (!proceed) {
      selectedType.value = prev
      return
    }
  }
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
