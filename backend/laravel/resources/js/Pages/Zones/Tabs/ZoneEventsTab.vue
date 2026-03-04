<template>
  <div class="space-y-4">
    <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Фильтр</span>
          <button
            v-for="kind in kindOptions"
            :key="kind.value"
            type="button"
            class="h-9 px-3 rounded-full border text-xs font-semibold transition-colors"
            :class="selectedKind === kind.value
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="selectedKind = kind.value"
          >
            {{ kind.label }}
          </button>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="query"
            class="input-field h-9 w-full sm:w-64"
            placeholder="Поиск по событию..."
          />
          <Button
            size="sm"
            variant="secondary"
            @click="exportEvents"
          >
            Экспорт CSV
          </Button>
        </div>
      </div>
    </section>

    <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div
        v-if="filteredEvents.length === 0"
        class="text-sm text-[color:var(--text-dim)] text-center py-6"
      >
        Нет событий по текущим фильтрам
      </div>
      <div
        v-else
        class="h-[520px]"
      >
        <VirtualList
          v-if="useVirtual"
          :items="filteredEvents"
          :item-size="64"
          class="h-full"
          key-field="id"
        >
          <template #default="{ item }">
            <div class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-2 border-b border-[color:var(--border-muted)]">
              <Badge
                :variant="getEventVariant(item.kind)"
                class="text-xs shrink-0"
              >
                {{ translateEventKind(item.kind) }}
              </Badge>
              <div class="flex-1 min-w-0">
                <div class="text-xs text-[color:var(--text-dim)]">
                  {{ item.occurred_at ? new Date(item.occurred_at).toLocaleString('ru-RU') : '—' }}
                </div>
                <div class="text-sm">
                  {{ item.message }}
                  <button
                    v-if="hasCorrectionPayload(item)"
                    type="button"
                    class="ml-2 text-xs text-[color:var(--text-dim)] underline underline-offset-2"
                    @click="toggleExpanded(item.id)"
                  >
                    {{ isExpanded(item.id) ? 'Скрыть' : 'Подробности' }}
                  </button>
                </div>
                <div
                  v-if="isExpanded(item.id) && hasCorrectionPayload(item)"
                  class="mt-1 rounded-md bg-[color:var(--bg-elevated)] p-2 text-xs font-mono space-y-0.5"
                >
                  <div v-if="payloadDose(item) !== null">
                    Доза: <strong>{{ formatPayloadNumber(payloadDose(item), 3) }} мл</strong>
                  </div>
                  <div v-if="payloadError(item) !== null">
                    Ошибка: <strong>{{ formatPayloadNumber(payloadError(item), 4) }}</strong>
                  </div>
                  <div v-if="payloadCurrent(item) !== null || payloadTarget(item) !== null">
                    Текущее: <strong>{{ formatPayloadNumber(payloadCurrent(item), 3) ?? '—' }}</strong>
                    → Цель: <strong>{{ formatPayloadNumber(payloadTarget(item), 3) ?? '—' }}</strong>
                  </div>
                  <div v-if="payloadZoneState(item)">
                    Зона PID: <strong>{{ payloadZoneState(item) }}</strong>
                  </div>
                  <div v-if="payloadIntegral(item) !== null">
                    Интеграл: <strong>{{ formatPayloadNumber(payloadIntegral(item), 4) }}</strong>
                  </div>
                  <div v-if="payloadComponent(item)">
                    Компонент: <strong>{{ payloadComponent(item) }}</strong>
                  </div>
                  <div v-if="payloadReason(item)">
                    Причина: <strong>{{ payloadReason(item) }}</strong>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </VirtualList>
        <div
          v-else
          class="space-y-1 max-h-[520px] overflow-y-auto"
        >
          <div
            v-for="item in filteredEvents"
            :key="item.id"
            class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-2 border-b border-[color:var(--border-muted)]"
          >
            <Badge
              :variant="getEventVariant(item.kind)"
              class="text-xs shrink-0"
            >
              {{ translateEventKind(item.kind) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="text-xs text-[color:var(--text-dim)]">
                {{ item.occurred_at ? new Date(item.occurred_at).toLocaleString('ru-RU') : '—' }}
              </div>
              <div class="text-sm">
                {{ item.message }}
                <button
                  v-if="hasCorrectionPayload(item)"
                  type="button"
                  class="ml-2 text-xs text-[color:var(--text-dim)] underline underline-offset-2"
                  @click="toggleExpanded(item.id)"
                >
                  {{ isExpanded(item.id) ? 'Скрыть' : 'Подробности' }}
                </button>
              </div>
              <div
                v-if="isExpanded(item.id) && hasCorrectionPayload(item)"
                class="mt-1 rounded-md bg-[color:var(--bg-elevated)] p-2 text-xs font-mono space-y-0.5"
              >
                <div v-if="payloadDose(item) !== null">
                  Доза: <strong>{{ formatPayloadNumber(payloadDose(item), 3) }} мл</strong>
                </div>
                <div v-if="payloadError(item) !== null">
                  Ошибка: <strong>{{ formatPayloadNumber(payloadError(item), 4) }}</strong>
                </div>
                <div v-if="payloadCurrent(item) !== null || payloadTarget(item) !== null">
                  Текущее: <strong>{{ formatPayloadNumber(payloadCurrent(item), 3) ?? '—' }}</strong>
                  → Цель: <strong>{{ formatPayloadNumber(payloadTarget(item), 3) ?? '—' }}</strong>
                </div>
                <div v-if="payloadZoneState(item)">
                  Зона PID: <strong>{{ payloadZoneState(item) }}</strong>
                </div>
                <div v-if="payloadIntegral(item) !== null">
                  Интеграл: <strong>{{ formatPayloadNumber(payloadIntegral(item), 4) }}</strong>
                </div>
                <div v-if="payloadComponent(item)">
                  Компонент: <strong>{{ payloadComponent(item) }}</strong>
                </div>
                <div v-if="payloadReason(item)">
                  Причина: <strong>{{ payloadReason(item) }}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import VirtualList from '@/Components/VirtualList.vue'
import { translateEventKind, classifyEventKind } from '@/utils/i18n'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface Props {
  events: ZoneEvent[]
  zoneId: number | null
}

const props = defineProps<Props>()

const selectedKind = ref<'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'>('ALL')
const query = ref('')

const kindOptions: Array<{ value: 'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION', label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ALERT', label: 'Alert' },
  { value: 'WARNING', label: 'Warning' },
  { value: 'INFO', label: 'Info' },
  { value: 'ACTION', label: 'Action' },
]

const queryLower = computed(() => query.value.toLowerCase())

const filteredEvents = computed(() => {
  const list = Array.isArray(props.events) ? props.events : []
  return list.filter((event) => {
    // kind в БД — это raw тип (ALERT_CREATED, CYCLE_STARTED и т.д.)
    // Классифицируем его в категорию фильтра через classifyEventKind
    const matchesKind = selectedKind.value === 'ALL' ? true : classifyEventKind(event.kind) === selectedKind.value
    const matchesQuery = queryLower.value
      ? (event.message?.toLowerCase().includes(queryLower.value) || event.kind?.toLowerCase().includes(queryLower.value))
      : true
    return matchesKind && matchesQuery
  })
})

const useVirtual = computed(() => filteredEvents.value.length > 200)

const CORRECTION_EVENT_KINDS = new Set([
  'PH_CORRECTED',
  'EC_DOSING',
  'PID_OUTPUT',
  'CORRECTION_STATE_TRANSITION',
  'RELAY_AUTOTUNE_COMPLETE',
  'RELAY_AUTOTUNE_COMPLETED',
  'PUMP_CALIBRATION_SAVED',
  'CORRECTION_SKIPPED_DEAD_ZONE',
  'CORRECTION_SKIPPED_COOLDOWN',
  'CORRECTION_SKIPPED_MISSING_ACTUATOR',
  'CORRECTION_SKIPPED_NO_CALIBRATION',
  'CORRECTION_SKIPPED_WATER_LEVEL',
  'CORRECTION_SKIPPED_FRESHNESS',
  'CORRECTION_SKIPPED_ANOMALY_BLOCK',
  'PH_CORRECTION_SKIPPED',
  'EC_CORRECTION_SKIPPED',
])

const expandedIds = ref<Set<number>>(new Set())

function getEventVariant(kind: string): 'danger' | 'warning' | 'info' | 'success' | 'neutral' {
  const category = classifyEventKind(kind)
  if (category === 'ALERT') return 'danger'
  if (category === 'WARNING') return 'warning'
  if (category === 'INFO') return 'info'
  if (category === 'ACTION') return 'success'
  return 'neutral'
}

function isExpanded(id: number): boolean {
  return expandedIds.value.has(id)
}

function toggleExpanded(id: number): void {
  const next = new Set(expandedIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expandedIds.value = next
}

function toPayloadRecord(payload: unknown): Record<string, unknown> | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null
  }
  return payload as Record<string, unknown>
}

function hasCorrectionPayload(event: ZoneEvent): boolean {
  const payload = toPayloadRecord(event.payload)
  if (!payload || Object.keys(payload).length === 0) {
    return false
  }

  return (
    CORRECTION_EVENT_KINDS.has(event.kind) ||
    event.kind.startsWith('CORRECTION_SKIPPED_') ||
    event.kind.endsWith('_CORRECTION_SKIPPED') ||
    event.kind.endsWith('_CORRECTION_SKIPPED_STALE_DATA') ||
    event.kind.endsWith('_CORRECTION_SKIPPED_BOUNDS') ||
    event.kind.endsWith('_CORRECTION_SKIPPED_ANOMALY')
  )
}

function readNumber(payload: Record<string, unknown> | null, key: string): number | null {
  if (!payload) return null
  const raw = payload[key]
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  if (typeof raw === 'string' && raw.trim() !== '') {
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function readString(payload: Record<string, unknown> | null, key: string): string | null {
  if (!payload) return null
  const raw = payload[key]
  if (typeof raw === 'string' && raw.trim() !== '') return raw
  if (typeof raw === 'number' && Number.isFinite(raw)) return String(raw)
  return null
}

function firstNumber(payload: Record<string, unknown> | null, keys: string[]): number | null {
  for (const key of keys) {
    const value = readNumber(payload, key)
    if (value !== null) return value
  }
  return null
}

function firstString(payload: Record<string, unknown> | null, keys: string[]): string | null {
  for (const key of keys) {
    const value = readString(payload, key)
    if (value !== null) return value
  }
  return null
}

function payloadDose(event: ZoneEvent): number | null {
  const payload = toPayloadRecord(event.payload)
  return firstNumber(payload, ['output', 'ml'])
}

function payloadError(event: ZoneEvent): number | null {
  const payload = toPayloadRecord(event.payload)
  return firstNumber(payload, ['error', 'diff'])
}

function payloadCurrent(event: ZoneEvent): number | null {
  const payload = toPayloadRecord(event.payload)
  return firstNumber(payload, ['current', 'current_ph', 'current_ec'])
}

function payloadTarget(event: ZoneEvent): number | null {
  const payload = toPayloadRecord(event.payload)
  return firstNumber(payload, ['target', 'target_ph', 'target_ec'])
}

function payloadZoneState(event: ZoneEvent): string | null {
  const payload = toPayloadRecord(event.payload)
  return firstString(payload, ['zone_state', 'pid_zone'])
}

function payloadIntegral(event: ZoneEvent): number | null {
  const payload = toPayloadRecord(event.payload)
  return firstNumber(payload, ['integral_term'])
}

function payloadComponent(event: ZoneEvent): string | null {
  const payload = toPayloadRecord(event.payload)
  return firstString(payload, ['component', 'correction_type'])
}

function payloadReason(event: ZoneEvent): string | null {
  const payload = toPayloadRecord(event.payload)
  return firstString(payload, ['reason', 'reason_code', 'safety_skip_reason'])
}

function formatPayloadNumber(value: number | null, digits = 3): string | null {
  if (value === null || !Number.isFinite(value)) {
    return null
  }
  return value.toFixed(digits)
}

const exportEvents = (): void => {
  if (typeof window === 'undefined') return

  const rows: string[] = ['id,kind,message,occurred_at']
  filteredEvents.value.forEach((event) => {
    const escapedMessage = (event.message || '').replace(/"/g, '""')
    rows.push(`${event.id},${event.kind},"${escapedMessage}",${event.occurred_at}`)
  })

  const csv = rows.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const fileLabel = props.zoneId ? `zone-${props.zoneId}` : 'zone'
  link.href = url
  link.download = `${fileLabel}-events.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>
