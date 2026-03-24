<template>
  <Card>
    <div class="space-y-3">
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
            Открыть визард
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
        class="space-y-2.5"
      >
        <div class="grid gap-2 md:grid-cols-3">
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2.5">
            <div class="text-[11px] uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Всего каналов
            </div>
            <div class="mt-1.5 text-base font-semibold text-[color:var(--text-primary)]">
              {{ calibrations.length }}
            </div>
          </div>
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2.5">
            <div class="text-[11px] uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Откалибровано
            </div>
            <div class="mt-1.5 text-base font-semibold text-[color:var(--text-primary)]">
              {{ calibratedCount }}
            </div>
          </div>
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2.5">
            <div class="text-[11px] uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Требуют внимания
            </div>
            <div class="mt-1.5 text-base font-semibold text-[color:var(--text-primary)]">
              {{ attentionCount }}
            </div>
          </div>
        </div>

        <div class="overflow-x-auto rounded-xl border border-[color:var(--border-muted)]">
          <table class="w-full min-w-[760px] text-xs">
            <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-dim)]">
              <tr class="border-b border-[color:var(--border-muted)]">
                <th class="px-3 py-2 text-left font-medium">Роль</th>
                <th class="px-3 py-2 text-left font-medium">Узел / канал</th>
                <th class="px-3 py-2 text-left font-medium">Статус</th>
                <th class="px-3 py-2 text-left font-medium">Источник</th>
                <th class="px-3 py-2 text-left font-medium">Последнее событие</th>
                <th class="px-3 py-2 text-left font-medium">Примечание</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="pump in calibrations"
                :key="pump.node_channel_id"
                class="border-b border-[color:var(--border-muted)] last:border-b-0"
              >
                <td class="px-3 py-2 align-top">
                  <div class="flex items-center gap-2">
                    <span class="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[color:var(--bg-elevated)] text-[10px] font-semibold text-[color:var(--text-dim)]">
                      {{ roleShortLabel(pump.role) }}
                    </span>
                    <span class="font-medium text-[color:var(--text-primary)]">{{ formatPumpLabel(pump) }}</span>
                  </div>
                </td>
                <td class="px-3 py-2 align-top text-[color:var(--text-dim)]">
                  <div>{{ pump.node_uid }}</div>
                  <div>{{ pump.channel }}</div>
                </td>
                <td class="px-3 py-2 align-top">
                  <Badge :variant="pump.ml_per_sec ? 'success' : 'warning'">
                    {{ pump.ml_per_sec ? `${formatMlPerSec(pump.ml_per_sec)} мл/с` : 'Нет калибровки' }}
                  </Badge>
                  <div class="mt-1 text-[color:var(--text-dim)]">
                    Диапазон {{ formatMlPerSec(pumpSettings.ml_per_sec_min) }}-{{ formatMlPerSec(pumpSettings.ml_per_sec_max) }} мл/с
                  </div>
                </td>
                <td class="px-3 py-2 align-top text-[color:var(--text-dim)] whitespace-nowrap">
                  {{ formatCalibrationSource(pump.source, pump.valid_from) }}
                </td>
                <td class="px-3 py-2 align-top text-[color:var(--text-dim)]">
                  <template v-if="historyByRole[pump.role]">
                    <div class="text-[color:var(--text-primary)]">{{ historyByRole[pump.role]?.message }}</div>
                    <div class="mt-1">{{ formatDateTime(historyByRole[pump.role]?.occurredAt) }}</div>
                    <div v-if="historyByRole[pump.role]?.mlPerSec !== null">
                      {{ formatMlPerSec(historyByRole[pump.role]!.mlPerSec!) }} мл/с
                    </div>
                  </template>
                  <span v-else>Нет событий</span>
                </td>
                <td class="px-3 py-2 align-top text-[color:var(--text-dim)]">
                  <div>Через визард</div>
                  <div v-if="Number(pump.calibration_age_days) > pumpSettings.age_warning_days" class="mt-1 text-[color:var(--badge-warning-text)]">
                    Устарела: {{ pump.calibration_age_days }} дн
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="rounded-md bg-[color:var(--bg-elevated)] px-3 py-2 text-xs text-[color:var(--text-dim)]">
        <strong>Рекомендуемые значения:</strong>
        pH кислота/щёлочь: 0.5-1.0 мл/с · NPK: 0.8-1.5 мл/с · Ca/Mg/Micro: 0.6-1.0 мл/с
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import { useApi } from '@/composables/useApi'
import { usePidConfig } from '@/composables/usePidConfig'
import { usePumpCalibrationSettings } from '@/composables/usePumpCalibrationSettings'
import type { PumpCalibration } from '@/types/PidConfig'

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

const props = withDefaults(defineProps<{
  zoneId: number
  saveSuccessSeq?: number
  runSuccessSeq?: number
}>(), {
  saveSuccessSeq: 0,
  runSuccessSeq: 0,
})
const emit = defineEmits<{
  (e: 'open-pump-calibration'): void
}>()

const calibrations = ref<PumpCalibration[]>([])
const loading = ref(true)
const historyEvents = ref<PumpCalibrationHistoryItem[]>([])

const { api } = useApi()
const { getPumpCalibrations } = usePidConfig()
const pumpSettings = usePumpCalibrationSettings()

const hasUncalibrated = computed(() => calibrations.value.some((pump) => !pump.ml_per_sec || pump.ml_per_sec <= 0))
const uncalibratedCount = computed(() => calibrations.value.filter((pump) => !pump.ml_per_sec || pump.ml_per_sec <= 0).length)
const calibratedCount = computed(() => calibrations.value.filter((pump) => pump.ml_per_sec && pump.ml_per_sec > 0).length)
const staleCount = computed(() => calibrations.value.filter((pump) => Number(pump.calibration_age_days) > pumpSettings.value.age_warning_days).length)
const attentionCount = computed(() => uncalibratedCount.value + staleCount.value)
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

function resolvePumpRole(payload: Record<string, unknown> | null, pumps: PumpCalibration[]): string | null {
  const directRole = typeof payload?.role === 'string' ? payload.role : null
  if (directRole) {
    return directRole
  }

  const component = typeof payload?.component === 'string' ? payload.component : null
  const componentRoleMap: Record<string, string> = {
    ph_down: 'ph_acid_pump',
    ph_up: 'ph_base_pump',
    npk: 'ec_npk_pump',
    calcium: 'ec_calcium_pump',
    magnesium: 'ec_magnesium_pump',
    micro: 'ec_micro_pump',
  }

  if (component && componentRoleMap[component]) {
    return componentRoleMap[component]
  }

  const nodeChannelId = parseNumeric(payload?.node_channel_id)
  if (nodeChannelId === null) {
    return null
  }

  const matchedPump = pumps.find((pump) => Number(pump.node_channel_id) === nodeChannelId)
  return matchedPump?.role ?? null
}

function toHistoryItem(raw: ZoneApiEvent, pumps: PumpCalibration[]): PumpCalibrationHistoryItem | null {
  if (raw.type !== 'PUMP_CALIBRATION_SAVED' && raw.type !== 'PUMP_CALIBRATION_FINISHED') {
    return null
  }

  const payload = toPayloadRecord(raw.payload ?? raw.details)
  const role = resolvePumpRole(payload, pumps)
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

async function loadHistory(): Promise<ZoneApiEvent[]> {
  const response = await api.get<{ status: string; data: ZoneApiEvent[] }>(`/api/zones/${props.zoneId}/events`, {
    params: {
      limit: 80,
    },
  })

  return Array.isArray(response.data.data) ? response.data.data : []
}

async function loadCalibrations(): Promise<void> {
  loading.value = true
  try {
    const [pumps, rawHistory] = await Promise.all([
      getPumpCalibrations(props.zoneId),
      loadHistory(),
    ])
    calibrations.value = pumps
    historyEvents.value = rawHistory
      .map((item) => toHistoryItem(item, pumps))
      .filter((item): item is PumpCalibrationHistoryItem => item !== null)
      .sort((left, right) => right.id - left.id)
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.zoneId, props.saveSuccessSeq, props.runSuccessSeq],
  () => {
  void loadCalibrations()
  },
  { immediate: true }
)
</script>
