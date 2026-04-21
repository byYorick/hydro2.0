<template>
    <div class="pid" data-testid="pid-config-form">
        <!-- ================== ACTION BAR ================== -->
        <div class="pid__actionbar">
            <div class="pid__actionbar-lhs">
                <span v-if="isDirty" class="pid__badge pid__badge--info">
                    <span class="pid__badge-dot" />
                    изменено
                </span>
                <span class="pid__pill pid__pill--violet">
                    Контур {{ selectedType.toUpperCase() }}
                </span>
                <span class="pid__pill">
                    пресет: {{ selectedPresetName }}
                </span>
                <span v-if="phaseTargetAvailable" class="pid__pill pid__pill--success">
                    цель: {{ phaseTargetDisplay }}
                </span>
                <span v-else class="pid__pill pid__pill--danger">
                    нет цели в рецепте
                </span>
                <span class="pid__meta">pH {{ savedBadge('ph') }} · EC {{ savedBadge('ec') }}</span>
            </div>
            <div class="pid__actionbar-rhs">
                <button
                    type="button"
                    class="pid__btn pid__btn--outline"
                    data-testid="pid-config-toggle-advanced"
                    :disabled="loading"
                    @click="showAdvanced = !showAdvanced"
                >
                    {{ showAdvanced ? 'Скрыть продвинутые' : 'Продвинутые настройки' }}
                </button>
                <button
                    type="button"
                    class="pid__btn pid__btn--outline"
                    :disabled="loading"
                    @click="onReset"
                >
                    Откатить изменения
                </button>
                <button
                    type="button"
                    class="pid__btn pid__btn--primary"
                    data-testid="pid-config-save"
                    :disabled="loading || !phaseTargetAvailable || !isDirty"
                    @click="onSubmit"
                >
                    {{
                        loading
                            ? 'Сохранение…'
                            : needsConfirmation && !confirmed
                              ? 'Подтвердить и сохранить'
                              : `Сохранить ${selectedType.toUpperCase()}`
                    }}
                </button>
            </div>
        </div>

        <!-- ================== PRESET STRIP ================== -->
        <div class="pid__preset-strip">
            <span class="pid__preset-strip__label">Пресет</span>
            <button
                v-for="preset in presetOptions"
                :key="preset.key"
                type="button"
                class="pid__preset-pill"
                :class="{ 'pid__preset-pill--active': selectedPresetKey === preset.key }"
                :data-testid="`pid-config-preset-${preset.key}`"
                :disabled="presetSwitching || loading"
                @click="onPresetPillClick(preset.key)"
            >
                {{ preset.name }}
            </button>
            <span v-if="selectedPresetDescription" class="pid__preset-desc">
                · {{ selectedPresetDescription }}
            </span>
        </div>

        <!-- ================== LOOP TABS ================== -->
        <div class="pid__tabs">
            <button
                type="button"
                class="pid__tab"
                :class="{ 'pid__tab--active': selectedType === 'ph' }"
                data-testid="pid-config-type-ph"
                @click="selectedType = 'ph'"
            >
                <span>Контур pH</span>
                <span v-if="pidConfigSavedState.ph" class="pid__tab-badge">сохранено</span>
                <span v-else class="pid__tab-badge pid__tab-badge--soft">нет переопределения</span>
            </button>
            <button
                type="button"
                class="pid__tab"
                :class="{ 'pid__tab--active': selectedType === 'ec' }"
                data-testid="pid-config-type-ec"
                @click="selectedType = 'ec'"
            >
                <span>Контур EC</span>
                <span v-if="pidConfigSavedState.ec" class="pid__tab-badge">сохранено</span>
                <span v-else class="pid__tab-badge pid__tab-badge--soft">нет переопределения</span>
            </button>
        </div>

        <div v-if="!phaseTargetAvailable" class="pid__banner pid__banner--danger">
            В активной фазе рецепта нет целевого значения <strong>{{ selectedType.toUpperCase() }}</strong>.
            PID-конфиг не может быть сохранён — runtime перейдёт в fail-closed.
        </div>

        <div v-if="needsConfirmation" class="pid__banner pid__banner--warn">
            ⚠ Агрессивные настройки (<code>Kp &gt; 200</code>).
            <span v-if="!confirmed">Нажмите «Подтвердить и сохранить» ещё раз.</span>
        </div>

        <!-- ================== SECTIONS ================== -->
        <details class="pid__section" :open="openSections.has('zones')" @toggle="toggleSection('zones', $event)">
            <summary class="pid__section-summary">
                <span class="pid__section-title">Зоны отклонения</span>
                <span class="pid__section-desc">dead / close / far · границы реакций PID</span>
            </summary>
            <div class="pid__section-body">
                <label class="pid__field">
                    <span class="pid__field-label">
                        Цель
                        <span class="pid__field-lock">🔒 из рецепта</span>
                    </span>
                    <input
                        :value="phaseTargetDisplay"
                        type="number"
                        data-testid="pid-config-input-target"
                        :step="0.01"
                        :min="selectedType === 'ph' ? 4 : 0"
                        :max="selectedType === 'ph' ? 9 : 10"
                        class="pid__input pid__input--readonly"
                        :placeholder="`Цель ${selectedType.toUpperCase()} не задана`"
                        readonly
                    />
                    <span class="pid__field-hint">{{ phaseTargetAvailable ? phaseTargetSourceHint : 'runtime не подставит значения по умолчанию' }}</span>
                </label>
                <label class="pid__field">
                    <span class="pid__field-label">
                        Мёртвая зона
                        <span v-if="isFieldDirty('dead_zone')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.dead_zone"
                        type="number"
                        step="0.01"
                        min="0"
                        max="2"
                        class="pid__input"
                        :title="fieldHelp('dead_zone')"
                    />
                    <span class="pid__field-hint">0..2 · игнорируется мелкое отклонение</span>
                </label>
                <label class="pid__field">
                    <span class="pid__field-label">
                        Ближняя зона
                        <span v-if="isFieldDirty('close_zone')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.close_zone"
                        type="number"
                        step="0.01"
                        min="0"
                        max="5"
                        class="pid__input"
                        :title="fieldHelp('close_zone')"
                    />
                    <span class="pid__field-hint">должна быть &gt; мёртвой зоны</span>
                </label>
                <label class="pid__field">
                    <span class="pid__field-label">
                        Дальняя зона
                        <span v-if="isFieldDirty('far_zone')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.far_zone"
                        type="number"
                        step="0.01"
                        min="0"
                        max="10"
                        class="pid__input"
                        :title="fieldHelp('far_zone')"
                    />
                    <span class="pid__field-hint">должна быть &gt; ближней зоны</span>
                </label>
            </div>
        </details>

        <details
            v-if="showAdvanced"
            class="pid__section"
            :open="openSections.has('close')"
            @toggle="toggleSection('close', $event)"
        >
            <summary class="pid__section-summary">
                <span class="pid__section-title">Коэффициенты ближней зоны</span>
                <span class="pid__section-desc">мягкая коррекция около target</span>
            </summary>
            <div class="pid__section-body">
                <label class="pid__field">
                    <span class="pid__field-label">
                        Kp
                        <span v-if="isCoeffDirty('close', 'kp')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.zone_coeffs.close.kp"
                        type="number"
                        step="0.1"
                        min="0"
                        max="1000"
                        class="pid__input"
                        :title="fieldHelp('close.kp')"
                    />
                </label>
                <label class="pid__field">
                    <span class="pid__field-label">
                        Ki
                        <span v-if="isCoeffDirty('close', 'ki')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.zone_coeffs.close.ki"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        class="pid__input"
                        :title="fieldHelp('close.ki')"
                    />
                </label>
                <label class="pid__field">
                    <span class="pid__field-label">
                        Kd
                        <span v-if="isCoeffDirty('close', 'kd')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.zone_coeffs.close.kd"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        class="pid__input"
                        :title="fieldHelp('close.kd')"
                    />
                </label>
            </div>
        </details>

        <details
            v-if="showAdvanced"
            class="pid__section"
            :open="openSections.has('far')"
            @toggle="toggleSection('far', $event)"
        >
            <summary class="pid__section-summary">
                <span class="pid__section-title">Коэффициенты дальней зоны</span>
                <span class="pid__section-desc">агрессивная коррекция при большом отклонении</span>
            </summary>
            <div class="pid__section-body">
                <label class="pid__field">
                    <span class="pid__field-label">
                        Kp
                        <span v-if="isCoeffDirty('far', 'kp')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.zone_coeffs.far.kp"
                        type="number"
                        step="0.1"
                        min="0"
                        max="1000"
                        class="pid__input"
                        :title="fieldHelp('far.kp')"
                    />
                </label>
                <label class="pid__field">
                    <span class="pid__field-label">
                        Ki
                        <span v-if="isCoeffDirty('far', 'ki')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.zone_coeffs.far.ki"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        class="pid__input"
                        :title="fieldHelp('far.ki')"
                    />
                </label>
                <label class="pid__field">
                    <span class="pid__field-label">
                        Kd
                        <span v-if="isCoeffDirty('far', 'kd')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.zone_coeffs.far.kd"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        class="pid__input"
                        :title="fieldHelp('far.kd')"
                    />
                </label>
            </div>
        </details>

        <details
            v-if="showAdvanced"
            class="pid__section"
            :open="openSections.has('integral')"
            @toggle="toggleSection('integral', $event)"
        >
            <summary class="pid__section-summary">
                <span class="pid__section-title">Предел интеграла</span>
                <span class="pid__section-desc">max_integral · защита от переполнения</span>
            </summary>
            <div class="pid__section-body">
                <label class="pid__field">
                    <span class="pid__field-label">
                        Предел интеграла
                        <span v-if="isFieldDirty('max_integral')" class="pid__field-dirty">●</span>
                    </span>
                    <input
                        v-model.number="form.max_integral"
                        type="number"
                        step="1"
                        min="1"
                        max="500"
                        class="pid__input"
                        :title="fieldHelp('max_integral')"
                    />
                    <span class="pid__field-hint">pH обычно 12–20 · EC 20–100</span>
                </label>
            </div>
        </details>

        <!-- ================== PREVIEW ================== -->
        <div class="pid__preview">
            <div>
                <span>Контур</span>
                <strong>{{ selectedType.toUpperCase() }}</strong>
            </div>
            <div>
                <span>Цель</span>
                <strong>{{ phaseTargetAvailable ? phaseTargetDisplay : '—' }}</strong>
            </div>
            <div>
                <span>мёртвая · ближняя · дальняя</span>
                <strong>{{ form.dead_zone }} · {{ form.close_zone }} · {{ form.far_zone }}</strong>
            </div>
            <div>
                <span>Предел интеграла</span>
                <strong>{{ form.max_integral }}</strong>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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

interface Props {
  zoneId: number
  phaseTargets?: RecipePhasePidTargets | null
}

const props = withDefaults(defineProps<Props>(), {
  phaseTargets: null,
})

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

const emit = defineEmits<{
  saved: [config: PidConfigWithMeta]
}>()

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
const pidConfigSavedState = ref<Record<'ph' | 'ec', boolean>>({
  ph: false,
  ec: false,
})
const automationConfig = useAutomationConfig()
const { getPidConfig, getAllPidConfigs, loading } = usePidConfig()
const runtimeTuningBundle = ref<RuntimeTuningBundlePayload | null>(null)
const selectedPresetKey = ref('system_default')

const form = ref<PidConfig>(cloneConfig(DEFAULT_CONFIGS.ph))
const lastSavedForm = ref<PidConfig>(cloneConfig(DEFAULT_CONFIGS.ph))
const openSections = ref<Set<string>>(new Set(['zones']))

const pidSaveStatuses = computed(() => [
  { type: 'ph' as const, label: 'pH', saved: pidConfigSavedState.value.ph },
  { type: 'ec' as const, label: 'EC', saved: pidConfigSavedState.value.ec },
])

const allPidConfigsSaved = computed(() => pidSaveStatuses.value.every((item) => item.saved))
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

const needsConfirmation = computed(() => {
  return (
    form.value.zone_coeffs.close.kp > 200 ||
    form.value.zone_coeffs.far.kp > 200
  )
})

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
    pidConfigSavedState.value = {
      ph: Boolean(configs.ph),
      ec: Boolean(configs.ec),
    }
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load PID status map:', error)
  }
}

async function loadRuntimeTuningBundle(): Promise<void> {
  try {
    const document = await automationConfig.getDocument<Record<string, unknown>>('zone', props.zoneId, RUNTIME_TUNING_BUNDLE_NAMESPACE)
    runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(document)
    selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load runtime tuning bundle:', error)
  }
}

async function persistRuntimeTuningBundle(nextBundle: RuntimeTuningBundlePayload): Promise<void> {
  const document = await automationConfig.updateDocument('zone', props.zoneId, RUNTIME_TUNING_BUNDLE_NAMESPACE, nextBundle)
  runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(document)
  selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
}

async function applySelectedPreset(): Promise<void> {
  if (!runtimeTuningBundle.value) {
    return
  }

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
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null
  }

  const payload = raw as Record<string, unknown>
  const activeGrowCycle = (
    payload.activeGrowCycle && typeof payload.activeGrowCycle === 'object' && !Array.isArray(payload.activeGrowCycle)
      ? payload.activeGrowCycle
      : (payload.active_grow_cycle && typeof payload.active_grow_cycle === 'object' && !Array.isArray(payload.active_grow_cycle)
        ? payload.active_grow_cycle
        : null)
  ) as Record<string, unknown> | null

  if (!activeGrowCycle) {
    return null
  }

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
    if (!runtimeTuningBundle.value) {
      logger.warn('[PidConfigForm] Refusing to save PID config without runtime tuning bundle', {
        zoneId: props.zoneId,
        pidType: selectedType.value,
      })
      return
    }

    await persistRuntimeTuningBundle(withPidOverride(runtimeTuningBundle.value, selectedType.value, form.value as unknown as Record<string, unknown>))
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
  }
)

watch(
  form,
  () => {
    if (confirmed.value) {
      confirmed.value = false
    }
  },
  { deep: true }
)

onMounted(() => {
  void hydratePhaseTargets()
  void loadRuntimeTuningBundle().then(() => Promise.all([loadStatuses(), loadConfig()]))
})
</script>

<style scoped>
.pid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

/* ============== ACTION BAR ============== */
.pid__actionbar {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.6rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    flex-wrap: wrap;
}

.pid__actionbar-lhs,
.pid__actionbar-rhs {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
}

.pid__badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.22rem 0.6rem;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 600;
}

.pid__badge--info {
    background: rgba(56, 189, 248, 0.12);
    color: rgb(125, 211, 252);
    border: 1px solid rgba(56, 189, 248, 0.35);
}

.pid__badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 9999px;
    background: currentColor;
}

.pid__pill {
    padding: 0.18rem 0.55rem;
    font-size: 0.72rem;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.1);
    border: 1px solid rgba(148, 163, 184, 0.25);
    font-family: ui-monospace, monospace;
}

.pid__pill--violet {
    background: rgba(139, 92, 246, 0.12);
    border-color: rgba(139, 92, 246, 0.35);
    color: rgb(196, 181, 253);
}

.pid__pill--success {
    background: rgba(34, 197, 94, 0.1);
    border-color: rgba(34, 197, 94, 0.35);
    color: rgb(134, 239, 172);
}

.pid__pill--danger {
    background: rgba(239, 68, 68, 0.1);
    border-color: rgba(239, 68, 68, 0.4);
    color: rgb(252, 165, 165);
}

.pid__meta {
    font-size: 0.7rem;
    opacity: 0.7;
    font-family: ui-monospace, monospace;
}

.pid__btn {
    padding: 0.3rem 0.75rem;
    border-radius: 0.35rem;
    border: 1px solid transparent;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 500;
}

.pid__btn:disabled {
    cursor: not-allowed;
    opacity: 0.55;
}

.pid__btn--outline {
    border-color: rgba(148, 163, 184, 0.3);
}

.pid__btn--outline:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.08);
}

.pid__btn--primary {
    background: rgb(56, 189, 248);
    color: #0f172a;
}

.pid__btn--primary:hover:not(:disabled) {
    background: rgb(14, 165, 233);
}

/* ============== PRESET STRIP ============== */
.pid__preset-strip {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem;
    padding: 0.5rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 0.45rem;
}

.pid__preset-strip__label {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 700;
    opacity: 0.55;
    padding-right: 0.3rem;
}

.pid__preset-pill {
    padding: 0.22rem 0.65rem;
    border-radius: 9999px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.75rem;
}

.pid__preset-pill:disabled { cursor: not-allowed; opacity: 0.55; }

.pid__preset-pill:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.08);
}

.pid__preset-pill--active {
    background: rgba(56, 189, 248, 0.12);
    border-color: rgba(56, 189, 248, 0.55);
    color: rgb(125, 211, 252);
    font-weight: 600;
}

.pid__preset-desc {
    font-size: 0.7rem;
    opacity: 0.6;
    margin-left: 0.3rem;
}

/* ============== TABS ============== */
.pid__tabs {
    display: flex;
    gap: 0.3rem;
    width: 100%;
    border-bottom: 1px solid rgba(148, 163, 184, 0.15);
    padding-bottom: 0.1rem;
}

.pid__tab {
    flex: 1 1 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    padding: 0.45rem 0.8rem;
    border: 1px solid transparent;
    border-bottom: none;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.82rem;
    border-radius: 0.4rem 0.4rem 0 0;
    margin-bottom: -1px;
}

.pid__tab:hover {
    background: rgba(148, 163, 184, 0.06);
}

.pid__tab--active {
    background: rgba(56, 189, 248, 0.1);
    border-color: rgba(56, 189, 248, 0.45);
    border-bottom-color: transparent;
    color: rgb(125, 211, 252);
    font-weight: 600;
}

.pid__tab-badge {
    padding: 0.05rem 0.4rem;
    font-size: 0.62rem;
    border-radius: 9999px;
    background: rgba(34, 197, 94, 0.18);
    color: rgb(134, 239, 172);
    font-weight: 500;
    letter-spacing: 0.03em;
}

.pid__tab-badge--soft {
    background: rgba(148, 163, 184, 0.15);
    color: rgba(148, 163, 184, 0.9);
}

/* ============== BANNERS ============== */
.pid__banner {
    padding: 0.55rem 0.85rem;
    border-radius: 0.4rem;
    font-size: 0.78rem;
}

.pid__banner--danger {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.35);
    color: rgb(252, 165, 165);
}

.pid__banner--warn {
    background: rgba(251, 191, 36, 0.08);
    border: 1px solid rgba(251, 191, 36, 0.35);
    color: rgb(250, 204, 21);
}

.pid__banner code {
    font-family: ui-monospace, monospace;
    background: rgba(15, 23, 42, 0.3);
    padding: 0 0.3rem;
    border-radius: 0.2rem;
}

/* ============== SECTIONS ============== */
.pid__section {
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.45rem;
    overflow: hidden;
}

.pid__section-summary {
    cursor: pointer;
    list-style: none;
    padding: 0.55rem 0.85rem;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.pid__section-summary::before {
    content: '▸ ';
    opacity: 0.55;
    margin-right: 0.25rem;
}

.pid__section[open] .pid__section-summary::before {
    content: '▾ ';
}

.pid__section-title {
    font-weight: 600;
    font-size: 0.85rem;
}

.pid__section-desc {
    font-size: 0.7rem;
    opacity: 0.6;
}

.pid__section-body {
    border-top: 1px solid rgba(148, 163, 184, 0.15);
    padding: 0.75rem 0.85rem;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.65rem;
}

/* ============== FIELDS ============== */
.pid__field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.8rem;
}

.pid__field-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.68rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-weight: 600;
    opacity: 0.7;
}

.pid__field-lock {
    font-size: 0.6rem;
    opacity: 0.6;
    font-weight: 500;
    text-transform: none;
    letter-spacing: 0;
}

.pid__field-dirty {
    color: rgb(56, 189, 248);
    font-size: 0.9rem;
    line-height: 1;
}

.pid__input {
    padding: 0.42rem 0.55rem;
    border-radius: 0.35rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: transparent;
    color: inherit;
    font-size: 0.85rem;
}

.pid__input:focus-visible {
    outline: none;
    border-color: rgba(56, 189, 248, 0.65);
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.16);
}

.pid__input--readonly {
    opacity: 0.8;
    cursor: not-allowed;
}

.pid__field-hint {
    font-size: 0.68rem;
    opacity: 0.65;
    line-height: 1.3;
}

/* ============== PREVIEW ============== */
.pid__preview {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    padding: 0.6rem 0.85rem;
    border: 1px dashed rgba(56, 189, 248, 0.25);
    background: rgba(56, 189, 248, 0.04);
    border-radius: 0.4rem;
}

.pid__preview > div {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.pid__preview span {
    font-size: 0.6rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    opacity: 0.6;
    font-weight: 600;
}

.pid__preview strong {
    font-size: 0.9rem;
    font-weight: 700;
    color: rgb(125, 211, 252);
    font-family: ui-monospace, monospace;
}
</style>
