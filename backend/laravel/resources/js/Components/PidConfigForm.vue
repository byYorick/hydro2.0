<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">Настройки PID</div>
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

      <form @submit.prevent="onSubmit" class="space-y-4">
        <!-- Основные параметры -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Целевое значение (target)
            </label>
            <input
              v-model.number="form.target"
              type="number"
              step="0.01"
              :min="selectedType === 'ph' ? 0 : 0"
              :max="selectedType === 'ph' ? 14 : 10"
              class="input-field w-full"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              {{ selectedType === 'ph' ? 'Диапазон: 0-14' : 'Диапазон: 0-10' }}
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
            <p class="text-xs text-[color:var(--text-dim)] mt-1">Диапазон: 0-2</p>
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
            <p class="text-xs text-[color:var(--text-dim)] mt-1">Должна быть больше dead_zone</p>
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
            <p class="text-xs text-[color:var(--text-dim)] mt-1">Должна быть больше close_zone</p>
          </div>
        </div>

        <!-- Коэффициенты для близкой зоны -->
        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-xs font-medium text-[color:var(--text-muted)] mb-3">Коэффициенты для близкой зоны</div>
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

        <!-- Коэффициенты для дальней зоны -->
        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-xs font-medium text-[color:var(--text-muted)] mb-3">Коэффициенты для дальней зоны</div>
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

        <!-- Дополнительные параметры -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-[color:var(--border-muted)] pt-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Максимальный выход (max_output)
            </label>
            <input
              v-model.number="form.max_output"
              type="number"
              step="0.1"
              min="0"
              max="1000"
              class="input-field w-full"
              required
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Минимальный интервал (min_interval_ms)
            </label>
            <input
              v-model.number="form.min_interval_ms"
              type="number"
              step="1000"
              min="1000"
              max="3600000"
              class="input-field w-full"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">В миллисекундах (1000-3600000)</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
              Скорость адаптации (adaptation_rate)
            </label>
            <input
              v-model.number="form.adaptation_rate"
              type="number"
              step="0.01"
              min="0"
              max="1"
              class="input-field w-full"
              required
            />
            <p class="text-xs text-[color:var(--text-dim)] mt-1">Диапазон: 0-1</p>
          </div>

          <div class="flex items-center gap-2 pt-6">
            <input
              v-model="form.enable_autotune"
              type="checkbox"
              id="autotune"
              class="rounded border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--accent-cyan)] focus:ring-[color:var(--focus-ring)]"
            />
            <label for="autotune" class="text-xs font-medium text-[color:var(--text-muted)]">
              Включить автонастройку (autotune)
            </label>
          </div>
        </div>

        <!-- Safeguard предупреждение -->
        <div
          v-if="needsConfirmation"
          class="rounded-md border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3"
        >
          <div class="text-xs font-medium text-[color:var(--badge-warning-text)] mb-1">Внимание!</div>
          <div class="text-xs text-[color:var(--badge-warning-text)]">
            Обнаружены агрессивные настройки (высокие коэффициенты или короткий интервал).
            Пожалуйста, подтвердите сохранение.
          </div>
        </div>

        <!-- Кнопки -->
        <div class="flex justify-end gap-2 pt-4 border-t border-[color:var(--border-muted)]">
          <Button type="button" variant="outline" size="sm" @click="onReset">
            Сбросить
          </Button>
          <Button type="submit" size="sm" :disabled="loading || (needsConfirmation && !confirmed)">
            {{ loading ? 'Сохранение...' : 'Сохранить' }}
          </Button>
        </div>
      </form>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
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

const selectedType = ref<'ph' | 'ec'>('ph')
const confirmed = ref(false)
const { getPidConfig, updatePidConfig, loading } = usePidConfig()

const form = ref<PidConfig>({
  target: 6.0,
  dead_zone: 0.2,
  close_zone: 0.5,
  far_zone: 1.0,
  zone_coeffs: {
    close: { kp: 10.0, ki: 0.0, kd: 0.0 },
    far: { kp: 12.0, ki: 0.0, kd: 0.0 },
  },
  max_output: 50.0,
  min_interval_ms: 60000,
  enable_autotune: false,
  adaptation_rate: 0.05,
})

const needsConfirmation = computed(() => {
  return (
    form.value.zone_coeffs.close.kp > 500 ||
    form.value.zone_coeffs.far.kp > 500 ||
    form.value.min_interval_ms < 30000
  )
})

async function loadConfig() {
  try {
    const config = await getPidConfig(props.zoneId, selectedType.value)
    if (config.config) {
      form.value = { ...config.config }
    }
  } catch (error) {
    logger.error('[PidConfigForm] Failed to load PID config:', error)
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
  loadConfig()
  confirmed.value = false
}

watch(selectedType, () => {
  loadConfig()
  confirmed.value = false
})

onMounted(() => {
  loadConfig()
})
</script>
