<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">
          Настройки PID
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': selectedType === 'ph' }"
            @click="selectedType = 'ph'"
          >
            pH
          </Button>
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': selectedType === 'ec' }"
            @click="selectedType = 'ec'"
          >
            EC
          </Button>
        </div>
      </div>

      <form
        class="space-y-4"
        @submit.prevent="onSubmit"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Целевое значение (target)
            </label>
            <input
              v-model.number="form.target"
              type="number"
              :step="selectedType === 'ph' ? 0.01 : 0.01"
              :min="selectedType === 'ph' ? 4 : 0"
              :max="selectedType === 'ph' ? 9 : 10"
              class="input-field w-full"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              {{ selectedType === 'ph' ? 'Диапазон: 4.0-9.0' : 'Диапазон: 0.0-10.0' }}
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
                required
              />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-[color:var(--border-muted)] pt-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Максимальная доза (мл)
            </label>
            <input
              v-model.number="form.max_output"
              type="number"
              step="0.1"
              min="0.1"
              max="500"
              class="input-field w-full"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              pH: 20 мл, EC: 50 мл — рекомендуемые значения
            </p>
          </div>

          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Пауза между дозами (мин)
            </label>
            <input
              v-model.number="intervalMinutes"
              type="number"
              step="0.5"
              min="0.5"
              max="60"
              class="input-field w-full"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              pH: 1.5 мин, EC: 2 мин — рекомендуемые значения
            </p>
          </div>

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
            Обнаружены агрессивные настройки (Kp &gt; 200 или пауза &lt; 30 сек).
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
            :disabled="loading"
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
import { usePidConfig } from '@/composables/usePidConfig'
import { logger } from '@/utils/logger'
import Card from './Card.vue'
import Button from './Button.vue'
import type { PidConfig, PidConfigWithMeta } from '@/types/PidConfig'

interface Props {
  zoneId: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  saved: [config: PidConfigWithMeta]
}>()

const DEFAULT_CONFIGS: Record<'ph' | 'ec', PidConfig> = {
  ph: {
    target: 5.8,
    dead_zone: 0.05,
    close_zone: 0.3,
    far_zone: 1.0,
    zone_coeffs: {
      close: { kp: 5.0, ki: 0.05, kd: 0.0 },
      far: { kp: 8.0, ki: 0.02, kd: 0.0 },
    },
    max_output: 20.0,
    min_interval_ms: 90_000,
    max_integral: 20.0,
  },
  ec: {
    target: 1.6,
    dead_zone: 0.1,
    close_zone: 0.5,
    far_zone: 1.5,
    zone_coeffs: {
      close: { kp: 30.0, ki: 0.3, kd: 0.0 },
      far: { kp: 50.0, ki: 0.1, kd: 0.0 },
    },
    max_output: 50.0,
    min_interval_ms: 120_000,
    max_integral: 100.0,
  },
}

const selectedType = ref<'ph' | 'ec'>('ph')
const confirmed = ref(false)
const { getPidConfig, updatePidConfig, loading } = usePidConfig()

const form = ref<PidConfig>(cloneConfig(DEFAULT_CONFIGS.ph))

const intervalMinutes = computed({
  get: () => Number(form.value.min_interval_ms || 0) / 60000,
  set: (val: number) => {
    const safeValue = Number.isFinite(val) ? Math.max(0, val) : 0
    form.value.min_interval_ms = Math.round(safeValue * 60000)
  },
})

const needsConfirmation = computed(() => {
  return (
    form.value.zone_coeffs.close.kp > 200 ||
    form.value.zone_coeffs.far.kp > 200 ||
    form.value.min_interval_ms < 30_000
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
    target: toNumberOr(raw?.target, defaults.target),
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
    max_output: toNumberOr(raw?.max_output, defaults.max_output),
    min_interval_ms: Math.max(1000, Math.round(toNumberOr(raw?.min_interval_ms, defaults.min_interval_ms))),
    max_integral: toNumberOr(raw?.max_integral, defaults.max_integral),
  }
}

async function loadConfig() {
  try {
    const config = await getPidConfig(props.zoneId, selectedType.value)
    const source = config.is_default ? DEFAULT_CONFIGS[selectedType.value] : (config.config || DEFAULT_CONFIGS[selectedType.value])
    form.value = normalizeConfig(source, selectedType.value)
    confirmed.value = false
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load PID config:', error)
    form.value = cloneConfig(DEFAULT_CONFIGS[selectedType.value])
  }
}

async function onSubmit() {
  if (needsConfirmation.value && !confirmed.value) {
    confirmed.value = true
    return
  }

  try {
    const saved = await updatePidConfig(props.zoneId, selectedType.value, form.value)
    emit('saved', saved)
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
  form,
  () => {
    if (confirmed.value) {
      confirmed.value = false
    }
  },
  { deep: true }
)

onMounted(() => {
  void loadConfig()
})
</script>
