<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">Настройки PID</div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-sky-600 text-white': selectedType === 'ph' }"
            @click="selectedType = 'ph'"
          >
            pH
          </Button>
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-sky-600 text-white': selectedType === 'ec' }"
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
            <label class="block text-xs font-medium text-neutral-300 mb-1">
              Целевое значение (target)
            </label>
            <input
              v-model.number="form.target"
              type="number"
              step="0.01"
              :min="selectedType === 'ph' ? 0 : 0"
              :max="selectedType === 'ph' ? 14 : 10"
              class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
              required
            />
            <p class="text-xs text-neutral-400 mt-1">
              {{ selectedType === 'ph' ? 'Диапазон: 0-14' : 'Диапазон: 0-10' }}
            </p>
          </div>

          <div>
            <label class="block text-xs font-medium text-neutral-300 mb-1">
              Мертвая зона (dead_zone)
            </label>
            <input
              v-model.number="form.dead_zone"
              type="number"
              step="0.01"
              min="0"
              max="2"
              class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
              required
            />
            <p class="text-xs text-neutral-400 mt-1">Диапазон: 0-2</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-neutral-300 mb-1">
              Ближняя зона (close_zone)
            </label>
            <input
              v-model.number="form.close_zone"
              type="number"
              step="0.01"
              min="0"
              max="5"
              class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
              required
            />
            <p class="text-xs text-neutral-400 mt-1">Должна быть больше dead_zone</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-neutral-300 mb-1">
              Дальняя зона (far_zone)
            </label>
            <input
              v-model.number="form.far_zone"
              type="number"
              step="0.01"
              min="0"
              max="10"
              class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
              required
            />
            <p class="text-xs text-neutral-400 mt-1">Должна быть больше close_zone</p>
          </div>
        </div>

        <!-- Коэффициенты для близкой зоны -->
        <div class="border-t border-neutral-800 pt-4">
          <div class="text-xs font-medium text-neutral-300 mb-3">Коэффициенты для близкой зоны</div>
          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Kp</label>
              <input
                v-model.number="form.zone_coeffs.close.kp"
                type="number"
                step="0.1"
                min="0"
                max="1000"
                class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Ki</label>
              <input
                v-model.number="form.zone_coeffs.close.ki"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Kd</label>
              <input
                v-model.number="form.zone_coeffs.close.kd"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
                required
              />
            </div>
          </div>
        </div>

        <!-- Коэффициенты для дальней зоны -->
        <div class="border-t border-neutral-800 pt-4">
          <div class="text-xs font-medium text-neutral-300 mb-3">Коэффициенты для дальней зоны</div>
          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Kp</label>
              <input
                v-model.number="form.zone_coeffs.far.kp"
                type="number"
                step="0.1"
                min="0"
                max="1000"
                class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Ki</label>
              <input
                v-model.number="form.zone_coeffs.far.ki"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
                required
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Kd</label>
              <input
                v-model.number="form.zone_coeffs.far.kd"
                type="number"
                step="0.01"
                min="0"
                max="100"
                class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
                required
              />
            </div>
          </div>
        </div>

        <!-- Дополнительные параметры -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-neutral-800 pt-4">
          <div>
            <label class="block text-xs font-medium text-neutral-300 mb-1">
              Максимальный выход (max_output)
            </label>
            <input
              v-model.number="form.max_output"
              type="number"
              step="0.1"
              min="0"
              max="1000"
              class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
              required
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-neutral-300 mb-1">
              Минимальный интервал (min_interval_ms)
            </label>
            <input
              v-model.number="form.min_interval_ms"
              type="number"
              step="1000"
              min="1000"
              max="3600000"
              class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
              required
            />
            <p class="text-xs text-neutral-400 mt-1">В миллисекундах (1000-3600000)</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-neutral-300 mb-1">
              Скорость адаптации (adaptation_rate)
            </label>
            <input
              v-model.number="form.adaptation_rate"
              type="number"
              step="0.01"
              min="0"
              max="1"
              class="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
              required
            />
            <p class="text-xs text-neutral-400 mt-1">Диапазон: 0-1</p>
          </div>

          <div class="flex items-center gap-2 pt-6">
            <input
              v-model="form.enable_autotune"
              type="checkbox"
              id="autotune"
              class="rounded border-neutral-700 bg-neutral-900 text-sky-600 focus:ring-sky-500"
            />
            <label for="autotune" class="text-xs font-medium text-neutral-300">
              Включить автонастройку (autotune)
            </label>
          </div>
        </div>

        <!-- Safeguard предупреждение -->
        <div
          v-if="needsConfirmation"
          class="rounded-md border border-amber-500/50 bg-amber-500/10 p-3"
        >
          <div class="text-xs font-medium text-amber-400 mb-1">Внимание!</div>
          <div class="text-xs text-amber-300">
            Обнаружены агрессивные настройки (высокие коэффициенты или короткий интервал).
            Пожалуйста, подтвердите сохранение.
          </div>
        </div>

        <!-- Кнопки -->
        <div class="flex justify-end gap-2 pt-4 border-t border-neutral-800">
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
    console.error('Failed to load PID config:', error)
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
    console.error('Failed to save PID config:', error)
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

