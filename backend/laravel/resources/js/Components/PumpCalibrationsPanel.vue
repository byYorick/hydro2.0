<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-2">
        <div class="text-sm font-semibold">Калибровки насосов</div>
        <div class="flex items-center gap-2">
          <Badge
            v-if="hasUncalibrated"
            variant="warning"
          >
            {{ uncalibratedCount }} без калибровки
          </Badge>
          <Button
            size="sm"
            variant="outline"
            @click="emit('open-pump-calibration')"
          >
            Открыть Pump Calibration
          </Button>
        </div>
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

          <div class="rounded-lg bg-[color:var(--bg-elevated)] px-3 py-2 text-xs text-[color:var(--text-dim)]">
            <div class="font-medium text-[color:var(--text-primary)]">
              {{ pump.ml_per_sec ? `Текущая скорость: ${formatMlPerSec(pump.ml_per_sec)} мл/с` : 'Скорость ещё не сохранена' }}
            </div>
            <div class="mt-1">
              Рабочий диапазон системы: {{ formatMlPerSec(pumpSettings.ml_per_sec_min) }}-{{ formatMlPerSec(pumpSettings.ml_per_sec_max) }} мл/с.
              Ручное редактирование из списка убрано, чтобы не дублировать Pump Calibration modal.
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              @click="emit('open-pump-calibration')"
            >
              {{ pump.ml_per_sec ? 'Перекалибровать' : 'Калибровать' }}
            </Button>
          </div>

          <div
            v-if="historyByRole[pump.role]"
            class="rounded-lg bg-[color:var(--bg-elevated)] px-3 py-2 text-xs text-[color:var(--text-dim)]"
          >
            <div class="font-medium text-[color:var(--text-primary)]">
              {{ historyByRole[pump.role]?.message }}
            </div>
            <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1">
              <span>Время: {{ formatDateTime(historyByRole[pump.role]?.occurredAt) }}</span>
              <span>Источник: {{ historyByRole[pump.role]?.source ?? 'не задан' }}</span>
              <span v-if="historyByRole[pump.role]?.mlPerSec !== null">
                Скорость: {{ formatMlPerSec(historyByRole[pump.role]!.mlPerSec!) }} мл/с
              </span>
            </div>
          </div>

          <div
            v-if="Number(pump.calibration_age_days) > pumpSettings.age_warning_days"
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
import { useApi } from '@/composables/useApi'
import { usePageProp } from '@/composables/usePageProps'
import { usePidConfig } from '@/composables/usePidConfig'
import type { PumpCalibration } from '@/types/PidConfig'
import type { PumpCalibrationSettings } from '@/types/SystemSettings'

interface ZoneApiEvent {
  event_id?: number
  id?: number
  type?: string
  created_at?: string | null
  occurred_at?: string | null
  message?: string | null
  payload?: Record<string, unknown> | null
  details?: Record<string, unknown> | null
}

interface PumpCalibrationHistoryItem {
  id: number
  role: string
  message: string
  occurredAt: string | null
  source: string | null
  mlPerSec: number | null
}

const props = defineProps<{ zoneId: number }>()
const emit = defineEmits<{
  (e: 'open-pump-calibration'): void
}>()

const calibrations = ref<PumpCalibration[]>([])
const loading = ref(true)
const historyEvents = ref<PumpCalibrationHistoryItem[]>([])

const { api } = useApi()
const { getPumpCalibrations } = usePidConfig()
const settings = usePageProp<'pumpCalibrationSettings', PumpCalibrationSettings>('pumpCalibrationSettings')
const pumpSettings = computed<PumpCalibrationSettings>(() => settings.value)

const hasUncalibrated = computed(() => calibrations.value.some((pump) => !pump.ml_per_sec || pump.ml_per_sec <= 0))
const uncalibratedCount = computed(() => calibrations.value.filter((pump) => !pump.ml_per_sec || pump.ml_per_sec <= 0).length)
const historyByRole = computed<Record<string, PumpCalibrationHistoryItem>>(() => {
  return historyEvents.value.reduce<Record<string, PumpCalibrationHistoryItem>>((acc, item) => {
    if (!acc[item.role] || acc[item.role].id < item.id) {
      acc[item.role] = item
    }

    return acc
  }, {})
})

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

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return 'не задано'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'не задано'
  }

  return date.toLocaleString('ru-RU')
}

function toPayloadRecord(raw: unknown): Record<string, unknown> | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null
  }

  return raw as Record<string, unknown>
}

function parseNumeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

function toHistoryItem(raw: ZoneApiEvent): PumpCalibrationHistoryItem | null {
  if (raw.type !== 'PUMP_CALIBRATION_SAVED') {
    return null
  }

  const payload = toPayloadRecord(raw.payload ?? raw.details)
  const role = typeof payload?.role === 'string' ? payload.role : null
  const id = Number(raw.event_id ?? raw.id)

  if (!role || !Number.isInteger(id) || id <= 0) {
    return null
  }

  return {
    id,
    role,
    message: typeof raw.message === 'string' && raw.message.trim() !== '' ? raw.message : 'Калибровка насоса сохранена',
    occurredAt: raw.occurred_at ?? raw.created_at ?? null,
    source: typeof payload?.source === 'string' ? payload.source : null,
    mlPerSec: parseNumeric(payload?.ml_per_sec),
  }
}

async function loadHistory(): Promise<void> {
  const response = await api.get<{ status: string; data: ZoneApiEvent[] }>(`/api/zones/${props.zoneId}/events`, {
    params: {
      limit: 80,
    },
  })

  historyEvents.value = Array.isArray(response.data.data)
    ? response.data.data
      .map((item) => toHistoryItem(item))
      .filter((item): item is PumpCalibrationHistoryItem => item !== null)
      .sort((left, right) => right.id - left.id)
    : []
}

async function loadCalibrations(): Promise<void> {
  loading.value = true
  try {
    const [pumps] = await Promise.all([
      getPumpCalibrations(props.zoneId),
      loadHistory(),
    ])
    calibrations.value = pumps
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadCalibrations()
})
</script>
