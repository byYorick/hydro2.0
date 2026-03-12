<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-2">
        <div class="text-sm font-semibold">Калибровки насосов</div>
        <Badge
          v-if="hasUncalibrated"
          variant="warning"
        >
          {{ uncalibratedCount }} без калибровки
        </Badge>
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-dim)]"
      >
        Загрузка...
      </div>

      <div
        v-else-if="calibrations.length === 0"
        class="text-sm text-[color:var(--text-dim)]"
      >
        Дозирующие насосы не найдены. Подключите узлы к зоне.
      </div>

      <div
        v-else
        class="space-y-3"
      >
        <div
          v-for="pump in calibrations"
          :key="pump.node_channel_id"
          class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-2"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[color:var(--bg-elevated)] text-[10px] font-semibold text-[color:var(--text-dim)]">
                  {{ roleShortLabel(pump.role) }}
                </span>
                <span class="text-sm font-medium truncate">{{ formatPumpLabel(pump) }}</span>
                <Badge :variant="pump.ml_per_sec ? 'success' : 'warning'">
                  {{ pump.ml_per_sec ? `${formatMlPerSec(pump.ml_per_sec)} мл/с` : 'Не откалиброван' }}
                </Badge>
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                {{ pump.node_uid }} / {{ pump.channel }}
              </div>
            </div>
            <span class="text-xs text-[color:var(--text-dim)] whitespace-nowrap">
              {{ formatCalibrationSource(pump.source, pump.valid_from) }}
            </span>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <input
              v-model.number="editValues[pump.node_channel_id]"
              type="number"
              step="0.01"
              min="0.01"
              max="20"
              class="input-field w-28"
              placeholder="мл/сек"
            />
            <span class="text-xs text-[color:var(--text-dim)]">мл/с</span>
            <Button
              size="sm"
              variant="outline"
              :disabled="Boolean(saving[pump.node_channel_id])"
              @click="savePumpCalibration(pump)"
            >
              {{ saving[pump.node_channel_id] ? 'Сохранение...' : 'Сохранить' }}
            </Button>
          </div>

          <div
            v-if="Number(pump.calibration_age_days) > 30"
            class="text-xs text-[color:var(--badge-warning-text)]"
          >
            Калибровка устарела ({{ pump.calibration_age_days }} дн)
          </div>
        </div>
      </div>

      <div class="rounded-md bg-[color:var(--bg-elevated)] p-2 text-xs text-[color:var(--text-dim)]">
        <strong>Рекомендуемые значения:</strong>
        pH кислота/щёлочь: 0.5-1.0 мл/с · NPK: 0.8-1.5 мл/с · Ca/Mg/Micro: 0.6-1.0 мл/с
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import { usePidConfig } from '@/composables/usePidConfig'
import type { PumpCalibration } from '@/types/PidConfig'

const props = defineProps<{ zoneId: number }>()

const calibrations = ref<PumpCalibration[]>([])
const loading = ref(true)
const editValues = ref<Record<number, number>>({})
const saving = ref<Record<number, boolean>>({})

const { getPumpCalibrations, updatePumpCalibration } = usePidConfig()

const hasUncalibrated = computed(() => calibrations.value.some((pump) => !pump.ml_per_sec || pump.ml_per_sec <= 0))
const uncalibratedCount = computed(() => calibrations.value.filter((pump) => !pump.ml_per_sec || pump.ml_per_sec <= 0).length)

function getDefaultMlPerSec(component: string): number {
  const defaults: Record<string, number> = {
    ph_down: 0.5,
    ph_up: 0.5,
    acid: 0.5,
    base: 0.5,
    npk: 1.0,
    calcium: 1.0,
    magnesium: 0.8,
    micro: 0.8,
  }

  return defaults[component] ?? 1.0
}

function roleShortLabel(role: string): string {
  const labels: Record<string, string> = {
    ph_acid_pump: 'pH-',
    ph_base_pump: 'pH+',
    ec_npk_pump: 'N',
    ec_calcium_pump: 'Ca',
    ec_magnesium_pump: 'Mg',
    ec_micro_pump: 'Mi',
  }

  return labels[role] ?? 'P'
}

function formatPumpLabel(pump: PumpCalibration): string {
  const labels: Record<string, string> = {
    ph_acid_pump: 'pH Down (кислота)',
    ph_base_pump: 'pH Up (щёлочь)',
    ec_npk_pump: 'NPK (питательный)',
    ec_calcium_pump: 'Кальций (Ca)',
    ec_magnesium_pump: 'Магний (Mg)',
    ec_micro_pump: 'Микроэлементы',
  }

  return labels[pump.role] ?? pump.channel_label ?? pump.channel
}

function formatMlPerSec(value: number): string {
  return Number(value).toFixed(2).replace(/\.00$/, '')
}

function formatCalibrationSource(source: string | null, validFrom: string | null): string {
  if (!source || !validFrom) return 'Не задана'
  const date = new Date(validFrom).toLocaleDateString('ru-RU')
  if (source === 'relay_autotune') return `Автотюнинг (${date})`
  if (source === 'manual') return `Вручную (${date})`
  if (source === 'manual_calibration') return `Калибровка (${date})`
  return `${source} (${date})`
}

function setSaving(channelId: number, value: boolean): void {
  saving.value = {
    ...saving.value,
    [channelId]: value,
  }
}

async function loadCalibrations(): Promise<void> {
  loading.value = true
  try {
    calibrations.value = await getPumpCalibrations(props.zoneId)
    const nextValues: Record<number, number> = {}
    calibrations.value.forEach((pump) => {
      nextValues[pump.node_channel_id] = pump.ml_per_sec ?? getDefaultMlPerSec(pump.component)
    })
    editValues.value = nextValues
  } finally {
    loading.value = false
  }
}

async function savePumpCalibration(pump: PumpCalibration): Promise<void> {
  const channelId = pump.node_channel_id
  const mlPerSec = Number(editValues.value[channelId])
  if (!Number.isFinite(mlPerSec) || mlPerSec <= 0) {
    return
  }

  setSaving(channelId, true)
  try {
    await updatePumpCalibration(props.zoneId, channelId, { ml_per_sec: mlPerSec })
    await loadCalibrations()
  } finally {
    setSaving(channelId, false)
  }
}

onMounted(() => {
  void loadCalibrations()
})
</script>
