<template>
  <Card
    class="pid-config-form"
    data-testid="pid-config-form"
  >
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">
          Настройки PID
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            data-testid="pid-config-type-ph"
            :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': selectedType === 'ph' }"
            @click="selectedType = 'ph'"
          >
            pH
          </Button>
          <Button
            size="sm"
            variant="outline"
            data-testid="pid-config-type-ec"
            :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': selectedType === 'ec' }"
            @click="selectedType = 'ec'"
          >
            EC
          </Button>
        </div>
      </div>

      <div
        class="rounded-md border p-3"
        :class="allPidConfigsSaved
          ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)]'
          : 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]'"
      >
        <div
          class="text-xs font-medium"
          :class="allPidConfigsSaved
            ? 'text-[color:var(--badge-success-text)]'
            : 'text-[color:var(--badge-warning-text)]'"
        >
          Сохранение PID для запуска
        </div>
        <div class="mt-2 flex flex-wrap gap-2 text-[11px]">
          <span
            v-for="item in pidSaveStatuses"
            :key="item.type"
            class="inline-flex items-center rounded-full border px-2 py-1"
            :class="item.saved
              ? 'border-[color:var(--badge-success-border)] text-[color:var(--badge-success-text)]'
              : 'border-[color:var(--badge-warning-border)] text-[color:var(--badge-warning-text)]'"
          >
            {{ item.label }}: {{ item.saved ? 'сохранён' : 'не сохранён' }}
          </span>
        </div>
        <div
          class="mt-2 text-xs"
          :class="allPidConfigsSaved
            ? 'text-[color:var(--badge-success-text)]'
            : 'text-[color:var(--badge-warning-text)]'"
        >
          <template v-if="allPidConfigsSaved">
            Оба PID-конфига сохранены в authority-документах зоны.
          </template>
          <template v-else>
            Для запуска цикла нужно явно сохранить и `pH`, и `EC` с target из актуальной recipe phase.
          </template>
        </div>
      </div>

      <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
        <label class="space-y-1.5">
          <span class="block text-xs font-medium text-[color:var(--text-muted)]">
            Preset runtime tuning
          </span>
          <select
            v-model="selectedPresetKey"
            class="input-select w-full"
            data-testid="pid-config-preset-select"
            :disabled="loading || presetSwitching"
            @change="applySelectedPreset"
          >
            <option
              v-for="preset in presetOptions"
              :key="preset.key"
              :value="preset.key"
            >
              {{ preset.name }}
            </option>
          </select>
          <p class="text-xs text-[color:var(--text-dim)]">
            {{ selectedPresetDescription }}
          </p>
        </label>

        <div class="flex items-end">
          <Button
            size="sm"
            variant="outline"
            data-testid="pid-config-toggle-advanced"
            :disabled="loading"
            @click="showAdvanced = !showAdvanced"
          >
            {{ showAdvanced ? 'Скрыть расширенные настройки' : 'Расширенные настройки' }}
          </Button>
        </div>
      </div>

      <div
        v-if="!phaseTargetAvailable"
        class="rounded-md border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] p-3 text-xs text-[color:var(--badge-danger-text)]"
        data-testid="pid-config-phase-target-missing"
      >
        В актуальной recipe phase отсутствует `{{ selectedType.toUpperCase() }}` target. PID-конфиг сохранить нельзя, automation должна перейти в fail-closed.
      </div>

      <div class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
        <div class="font-medium text-[color:var(--text-primary)]">
          {{ selectedPresetName }}
        </div>
        <div class="mt-1">
          Effective PID: dead {{ form.dead_zone }}, close {{ form.close_zone }}, far {{ form.far_zone }}, max_integral {{ form.max_integral }}
        </div>
      </div>

      <form
        v-if="showAdvanced"
        class="space-y-4"
        @submit.prevent="onSubmit"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Целевое значение (target)
            </label>
            <input
              :value="phaseTargetDisplay"
              type="number"
              data-testid="pid-config-input-target"
              :step="selectedType === 'ph' ? 0.01 : 0.01"
              :min="selectedType === 'ph' ? 4 : 0"
              :max="selectedType === 'ph' ? 9 : 10"
              class="input-field w-full"
              :title="fieldHelp('target')"
              :placeholder="selectedType === 'ph' ? 'target pH не задан в recipe phase' : 'target EC не задан в recipe phase'"
              readonly
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              <template v-if="phaseTargetAvailable">
                {{ phaseTargetSourceHint }}
              </template>
              <template v-else>
                Runtime не будет подставлять defaults или manual override вместо отсутствующего recipe phase target.
              </template>
            </p>
          </div>

          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Мертвая зона (dead_zone)
            </label>
            <input
              v-model.number="form.dead_zone"
              type="number"
              step="0.01"
              min="0"
              max="2"
              class="input-field w-full"
              :title="fieldHelp('dead_zone')"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Диапазон: 0-2
            </p>
          </div>

          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Ближняя зона (close_zone)
            </label>
            <input
              v-model.number="form.close_zone"
              type="number"
              step="0.01"
              min="0"
              max="5"
              class="input-field w-full"
              :title="fieldHelp('close_zone')"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Должна быть больше dead_zone
            </p>
          </div>

          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Дальняя зона (far_zone)
            </label>
            <input
              v-model.number="form.far_zone"
              type="number"
              step="0.01"
              min="0"
              max="10"
              class="input-field w-full"
              :title="fieldHelp('far_zone')"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Должна быть больше close_zone
            </p>
          </div>
        </div>

        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-xs font-medium text-[color:var(--text-muted)] mb-3">
            Коэффициенты для близкой зоны
          </div>
          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Kp</label>
              <input
                v-model.number="form.zone_coeffs.close.kp"
                type="number"
                step="0.1"
                min="0"
                max="1000"
                class="input-field w-full"
                :title="fieldHelp('close.kp')"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Ki</label>
              <input
                v-model.number="form.zone_coeffs.close.ki"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="input-field w-full"
                :title="fieldHelp('close.ki')"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Kd</label>
              <input
                v-model.number="form.zone_coeffs.close.kd"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="input-field w-full"
                :title="fieldHelp('close.kd')"
                required
              />
            </div>
          </div>
        </div>

        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-xs font-medium text-[color:var(--text-muted)] mb-3">
            Коэффициенты для дальней зоны
          </div>
          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Kp</label>
              <input
                v-model.number="form.zone_coeffs.far.kp"
                type="number"
                step="0.1"
                min="0"
                max="1000"
                class="input-field w-full"
                :title="fieldHelp('far.kp')"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Ki</label>
              <input
                v-model.number="form.zone_coeffs.far.ki"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="input-field w-full"
                :title="fieldHelp('far.ki')"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Kd</label>
              <input
                v-model.number="form.zone_coeffs.far.kd"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="input-field w-full"
                :title="fieldHelp('far.kd')"
                required
              />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-[color:var(--border-muted)] pt-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Лимит интеграла (max_integral)
            </label>
            <input
              v-model.number="form.max_integral"
              type="number"
              step="1"
              min="1"
              max="500"
              class="input-field w-full"
              :title="fieldHelp('max_integral')"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Ограничивает накопление интегральной ошибки. pH: 20, EC: 100
            </p>
          </div>
        </div>

        <div
          v-if="needsConfirmation"
          class="rounded-md border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3"
        >
          <div class="text-xs font-medium text-[color:var(--badge-warning-text)] mb-1">
            Внимание
          </div>
          <div class="text-xs text-[color:var(--badge-warning-text)]">
            Обнаружены агрессивные настройки (Kp &gt; 200).
            <span v-if="!confirmed"> Нажмите кнопку сохранения ещё раз для подтверждения.</span>
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-4 border-t border-[color:var(--border-muted)]">
          <Button
            type="button"
            variant="outline"
            size="sm"
            @click="onReset"
          >
            Сбросить
          </Button>
          <Button
            type="submit"
            size="sm"
            data-testid="pid-config-save"
            :disabled="loading || !phaseTargetAvailable"
          >
            {{ loading ? 'Сохранение...' : (needsConfirmation && !confirmed ? 'Подтвердить и сохранить' : 'Сохранить') }}
          </Button>
        </div>
      </form>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { resolveRecipePhasePidTargets, type RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import { usePidConfig } from '@/composables/usePidConfig'
import { useApi } from '@/composables/useApi'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import {
  normalizeRuntimeTuningBundleDocument,
  RUNTIME_TUNING_BUNDLE_NAMESPACE,
  selectedRuntimeTuningPreset,
  withPidOverride,
  type RuntimeTuningBundlePayload,
} from '@/composables/runtimeTuningBundle'
import { logger } from '@/utils/logger'
import Card from './Card.vue'
import Button from './Button.vue'
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
const { api } = useApi()
const automationConfig = useAutomationConfig()
const { getPidConfig, getAllPidConfigs, loading } = usePidConfig()
const runtimeTuningBundle = ref<RuntimeTuningBundlePayload | null>(null)
const selectedPresetKey = ref('system_default')

const form = ref<PidConfig>(cloneConfig(DEFAULT_CONFIGS.ph))

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
  const base = phaseLabel ? `Target подтянут из recipe phase «${phaseLabel}».` : 'Target подтянут из актуальной recipe phase.'

  return `${base} Ручное редактирование target запрещено, в zone.pid.* он не сохраняется.`
})
const selectedPreset = computed(() => selectedRuntimeTuningPreset(runtimeTuningBundle.value))
const presetOptions = computed(() => runtimeTuningBundle.value?.presets ?? [])
const selectedPresetName = computed(() => selectedPreset.value?.name ?? 'Системный preset')
const selectedPresetDescription = computed(() => selectedPreset.value?.description ?? 'Канонические стартовые значения PID и process calibration для зоны.')

const needsConfirmation = computed(() => {
  return (
    form.value.zone_coeffs.close.kp > 200 ||
    form.value.zone_coeffs.far.kp > 200
  )
})

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
    form.value = normalizeConfig(source, selectedType.value)
    pidConfigSavedState.value[selectedType.value] = Boolean(config)
    confirmed.value = false
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load PID config:', error)
    form.value = cloneConfig(DEFAULT_CONFIGS[selectedType.value])
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
    const response = await api.get<{ status: string; data?: unknown }>(`/zones/${props.zoneId}`)
    resolvedPhaseTargets.value = resolveRecipePhasePidTargets(extractCurrentPhase(response.data.data))
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

watch(selectedType, () => {
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
.pid-config-form :deep(.input-field) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}
</style>
