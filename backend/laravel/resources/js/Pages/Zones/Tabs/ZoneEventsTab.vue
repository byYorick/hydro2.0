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
            <EventRow
              :item="item"
              :expanded="isExpanded(item.id)"
              @toggle="toggleExpanded(item.id)"
            />
          </template>
        </VirtualList>
        <div
          v-else
          class="space-y-1 max-h-[520px] overflow-y-auto"
        >
          <EventRow
            v-for="item in filteredEvents"
            :key="item.id"
            :item="item"
            :expanded="isExpanded(item.id)"
            @toggle="toggleExpanded(item.id)"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref } from 'vue'
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
  { value: 'ALERT', label: 'Тревога' },
  { value: 'WARNING', label: 'Предупреждение' },
  { value: 'INFO', label: 'Инфо' },
  { value: 'ACTION', label: 'Действие' },
]

const queryLower = computed(() => query.value.toLowerCase())

const filteredEvents = computed(() => {
  const list = Array.isArray(props.events) ? props.events : []
  return list.filter((event) => {
    const matchesKind = selectedKind.value === 'ALL' ? true : classifyEventKind(event.kind) === selectedKind.value
    const matchesQuery = queryLower.value
      ? (event.message?.toLowerCase().includes(queryLower.value) || event.kind?.toLowerCase().includes(queryLower.value))
      : true
    return matchesKind && matchesQuery
  })
})

const useVirtual = computed(() => filteredEvents.value.length > 200)

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
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
  return payload as Record<string, unknown>
}

function hasExpandablePayload(event: ZoneEvent): boolean {
  const payload = toPayloadRecord(event.payload)
  return payload !== null && Object.keys(payload).length > 0
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

function formatPayloadNumber(value: number | null, digits = 3): string | null {
  if (value === null || !Number.isFinite(value)) return null
  return value.toFixed(digits)
}

function boolLabel(value: unknown): string {
  if (value === true) return 'вкл'
  if (value === false) return 'выкл'
  return '—'
}

// IRR_STATE_SNAPSHOT: render pump/valve/level table from snapshot object
function renderIrrSnapshot(payload: Record<string, unknown>): Array<{ label: string, value: string }> {
  const snapshot = toPayloadRecord(payload['snapshot'])
  if (!snapshot) return []
  const labelMap: Record<string, string> = {
    pump_main: 'Насос (основной)',
    valve_clean_fill: 'Клапан заполнения чистой',
    valve_clean_supply: 'Клапан подачи чистой воды',
    valve_solution_fill: 'Клапан заполнения раствора',
    valve_solution_supply: 'Клапан подачи раствора',
    valve_irrigation: 'Клапан полива',
    valve_drain: 'Клапан слива',
    valve_recirc: 'Клапан рециркуляции',
    clean_level_max: 'Уровень чистой (макс)',
    clean_level_min: 'Уровень чистой (мин)',
    solution_level_max: 'Уровень раствора (макс)',
    solution_level_min: 'Уровень раствора (мин)',
  }
  return Object.entries(snapshot).map(([key, val]) => ({
    label: labelMap[key] ?? key.replace(/_/g, ' '),
    value: typeof val === 'boolean' ? boolLabel(val) : String(val ?? '—'),
  }))
}

// EventRow sub-component for reuse in both virtual and regular lists
const EventRow = defineComponent({
  name: 'EventRow',
  props: {
    item: { type: Object as () => ZoneEvent, required: true },
    expanded: { type: Boolean, default: false },
  },
  emits: ['toggle'],
  setup(props, { emit }) {
    return () => {
      const { item, expanded } = props
      const payload = toPayloadRecord(item.payload)
      const canExpand = hasExpandablePayload(item)

      // Build detail panel content based on event kind
      const detailRows: ReturnType<typeof h>[] = []

      if (expanded && payload) {
        if (item.kind === 'IRR_STATE_SNAPSHOT') {
          const nodeUid = readString(payload, 'node_uid')
          const cmdId = readString(payload, 'cmd_id')
          if (nodeUid) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Нода: '), h('strong', {}, nodeUid)]))
          if (cmdId) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Команда: '), h('strong', {}, cmdId)]))
          const snapshotRows = renderIrrSnapshot(payload)
          if (snapshotRows.length > 0) {
            detailRows.push(
              h('div', { class: 'mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5' },
                snapshotRows.map(({ label, value }) =>
                  h('div', { class: 'contents' }, [
                    h('span', { class: 'text-[color:var(--text-dim)]' }, label + ':'),
                    h('strong', {}, value),
                  ])
                )
              )
            )
          }
        } else if (item.kind === 'COMMAND_TIMEOUT') {
          const cmdId = readString(payload, 'cmd_id')
          const timeout = readNumber(payload, 'timeout_minutes')
          const commandId = readNumber(payload, 'command_id')
          if (cmdId) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Команда: '), h('strong', {}, cmdId)]))
          if (timeout !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Таймаут: '), h('strong', {}, `${timeout} мин`)]))
          if (commandId !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'ID команды: '), h('strong', {}, String(commandId))]))
        } else if (item.kind === 'PUMP_CALIBRATION_FINISHED' || item.kind === 'PUMP_CALIBRATION_SAVED') {
          const component = firstString(payload, ['component', 'role'])
          const actualMl = readNumber(payload, 'actual_ml')
          const mlPerSec = readNumber(payload, 'ml_per_sec')
          const nodeUid = readString(payload, 'node_uid')
          const channel = readString(payload, 'channel')
          if (component) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Компонент: '), h('strong', {}, component)]))
          if (actualMl !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Объём: '), h('strong', {}, `${actualMl.toFixed(2)} мл`)]))
          if (mlPerSec !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Скорость: '), h('strong', {}, `${mlPerSec.toFixed(2)} мл/с`)]))
          if (nodeUid) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Нода: '), h('strong', {}, nodeUid)]))
          if (channel) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Канал: '), h('strong', {}, channel)]))
        } else if (item.kind === 'PUMP_CALIBRATION_RUN_SKIPPED') {
          const component = readString(payload, 'component')
          const nodeUid = readString(payload, 'node_uid')
          const channel = readString(payload, 'channel')
          const durationSec = readNumber(payload, 'duration_sec')
          const reason = firstString(payload, ['reason', 'reason_code'])
          if (component) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Компонент: '), h('strong', {}, component)]))
          if (nodeUid) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Нода: '), h('strong', {}, nodeUid)]))
          if (channel) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Канал: '), h('strong', {}, channel)]))
          if (durationSec !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Длительность теста: '), h('strong', {}, `${durationSec} с`)]))
          if (reason) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Причина: '), h('strong', {}, reason)]))
        } else if (item.kind === 'EC_DOSING') {
          const currentEc = readNumber(payload, 'current_ec')
          const targetEc = readNumber(payload, 'target_ec')
          const targetEcMin = readNumber(payload, 'target_ec_min')
          const targetEcMax = readNumber(payload, 'target_ec_max')
          const durationMs = readNumber(payload, 'duration_ms')
          const amountMl = readNumber(payload, 'amount_ml')
          const ecComponent = readString(payload, 'ec_component')
          const nodeUid = readString(payload, 'node_uid')
          const channel = readString(payload, 'channel')
          const attempt = readNumber(payload, 'attempt')
          if (ecComponent) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Компонент: '), h('strong', {}, ecComponent)]))
          if (currentEc !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Текущий EC: '), h('strong', {}, `${currentEc.toFixed(2)} мС/см`)]))
          if (targetEcMin !== null && targetEcMax !== null) {
            detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Цель EC: '), h('strong', {}, `${targetEcMin.toFixed(2)}–${targetEcMax.toFixed(2)} мС/см`)]))
          } else if (targetEc !== null) {
            detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Цель EC: '), h('strong', {}, `${targetEc.toFixed(2)} мС/см`)]))
          }
          if (amountMl !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Доза: '), h('strong', {}, `${amountMl.toFixed(1)} мл`)]))
          if (durationMs !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Импульс насоса: '), h('strong', {}, `${durationMs} мс`)]))
          if (nodeUid) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Нода: '), h('strong', {}, nodeUid)]))
          if (channel) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Канал: '), h('strong', {}, channel)]))
          if (attempt !== null && attempt > 1) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Попытка: '), h('strong', {}, String(attempt))]))
        } else if (item.kind === 'PH_CORRECTED') {
          const currentPh = readNumber(payload, 'current_ph')
          const targetPh = readNumber(payload, 'target_ph')
          const targetPhMin = readNumber(payload, 'target_ph_min')
          const targetPhMax = readNumber(payload, 'target_ph_max')
          const durationMs = readNumber(payload, 'duration_ms')
          const amountMl = readNumber(payload, 'amount_ml')
          const direction = readString(payload, 'direction')
          const nodeUid = readString(payload, 'node_uid')
          const channel = readString(payload, 'channel')
          const attempt = readNumber(payload, 'attempt')
          const dirLabel = direction === 'up' ? 'вверх ↑' : direction === 'down' ? 'вниз ↓' : direction
          if (dirLabel) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Направление: '), h('strong', {}, dirLabel)]))
          if (currentPh !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Текущий pH: '), h('strong', {}, currentPh.toFixed(2))]))
          if (targetPhMin !== null && targetPhMax !== null) {
            detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Цель pH: '), h('strong', {}, `${targetPhMin.toFixed(2)}–${targetPhMax.toFixed(2)}`)]))
          } else if (targetPh !== null) {
            detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Цель pH: '), h('strong', {}, targetPh.toFixed(2))]))
          }
          if (amountMl !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Доза: '), h('strong', {}, `${amountMl.toFixed(1)} мл`)]))
          if (durationMs !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Импульс насоса: '), h('strong', {}, `${durationMs} мс`)]))
          if (nodeUid) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Нода: '), h('strong', {}, nodeUid)]))
          if (channel) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Канал: '), h('strong', {}, channel)]))
          if (attempt !== null && attempt > 1) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Попытка: '), h('strong', {}, String(attempt))]))
        } else if (item.kind === 'CORRECTION_COMPLETE') {
          const currentPh = readNumber(payload, 'current_ph')
          const currentEc = readNumber(payload, 'current_ec')
          const attempt = readNumber(payload, 'attempt')
          if (currentPh !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'pH: '), h('strong', {}, currentPh.toFixed(2))]))
          if (currentEc !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'EC: '), h('strong', {}, `${currentEc.toFixed(2)} мС/см`)]))
          if (attempt !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Попытка: '), h('strong', {}, String(attempt))]))
        } else if (item.kind === 'CORRECTION_EXHAUSTED') {
          const attempt = readNumber(payload, 'attempt')
          const maxAttempts = readNumber(payload, 'max_attempts')
          const ecAttempt = readNumber(payload, 'ec_attempt')
          const phAttempt = readNumber(payload, 'ph_attempt')
          const stage = readString(payload, 'stage')
          if (attempt !== null && maxAttempts !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Попытки: '), h('strong', {}, `${attempt}/${maxAttempts}`)]))
          if (ecAttempt !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'EC попыток: '), h('strong', {}, String(ecAttempt))]))
          if (phAttempt !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'pH попыток: '), h('strong', {}, String(phAttempt))]))
          if (stage) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Стадия: '), h('strong', {}, stage)]))
        } else if (item.kind === 'CORRECTION_SKIPPED_COOLDOWN') {
          const currentPh = readNumber(payload, 'current_ph')
          const currentEc = readNumber(payload, 'current_ec')
          const retrySec = readNumber(payload, 'retry_after_sec')
          if (currentPh !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'pH: '), h('strong', {}, currentPh.toFixed(2))]))
          if (currentEc !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'EC: '), h('strong', {}, `${currentEc.toFixed(2)} мС/см`)]))
          if (retrySec !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Повтор через: '), h('strong', {}, `${retrySec} с`)]))
        } else if (item.kind === 'CORRECTION_SKIPPED_DOSE_DISCARDED') {
          const reason = readString(payload, 'reason')
          const durationMs = readNumber(payload, 'computed_duration_ms')
          const minDoseMs = readNumber(payload, 'min_dose_ms')
          const doseMl = readNumber(payload, 'dose_ml')
          const mlPerSec = readNumber(payload, 'ml_per_sec')
          if (reason) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Причина: '), h('strong', {}, reason)]))
          if (durationMs !== null && minDoseMs !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Импульс: '), h('strong', {}, `${durationMs} мс < ${minDoseMs} мс`)]))
          if (doseMl !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Доза: '), h('strong', {}, `${doseMl.toFixed(4)} мл`)]))
          if (mlPerSec !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Насос: '), h('strong', {}, `${mlPerSec.toFixed(4)} мл/с`)]))
        } else if (item.kind === 'CORRECTION_SKIPPED_WATER_LEVEL') {
          const levelPct = readNumber(payload, 'water_level_pct')
          const retrySec = readNumber(payload, 'retry_after_sec')
          if (levelPct !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Уровень воды: '), h('strong', {}, `${levelPct.toFixed(1)}%`)]))
          if (retrySec !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Повтор через: '), h('strong', {}, `${retrySec} с`)]))
        } else if (item.kind === 'CORRECTION_SKIPPED_FRESHNESS') {
          const sensorScope = readString(payload, 'sensor_scope')
          const sensorType = readString(payload, 'sensor_type')
          const retrySec = readNumber(payload, 'retry_after_sec')
          if (sensorScope) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Окно: '), h('strong', {}, sensorScope)]))
          if (sensorType) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Сенсор: '), h('strong', {}, sensorType)]))
          if (retrySec !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Повтор через: '), h('strong', {}, `${retrySec} с`)]))
        } else if (item.kind === 'CORRECTION_SKIPPED_WINDOW_NOT_READY') {
          const sensorScope = readString(payload, 'sensor_scope')
          const sensorType = readString(payload, 'sensor_type')
          const reason = readString(payload, 'reason')
          const retrySec = readNumber(payload, 'retry_after_sec')
          const sampleCount = readNumber(payload, 'sample_count')
          const slope = readNumber(payload, 'slope')
          if (sensorScope) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Окно: '), h('strong', {}, sensorScope)]))
          if (sensorType) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Сенсор: '), h('strong', {}, sensorType)]))
          if (reason) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Причина: '), h('strong', {}, reason)]))
          if (sampleCount !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Сэмплов: '), h('strong', {}, String(sampleCount))]))
          if (slope !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Slope: '), h('strong', {}, slope.toFixed(4))]))
          if (retrySec !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Повтор через: '), h('strong', {}, `${retrySec} с`)]))
        } else if (item.kind === 'CORRECTION_NO_EFFECT') {
          const pidType = readString(payload, 'pid_type')
          const actualEffect = readNumber(payload, 'actual_effect')
          const thresholdEffect = readNumber(payload, 'threshold_effect')
          const limit = readNumber(payload, 'no_effect_limit')
          if (pidType) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Контур: '), h('strong', {}, pidType.toUpperCase())]))
          if (actualEffect !== null && thresholdEffect !== null) {
            detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Эффект: '), h('strong', {}, `${actualEffect.toFixed(4)} < ${thresholdEffect.toFixed(4)}`)]))
          }
          if (limit !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Лимит: '), h('strong', {}, String(limit))]))
        } else if (item.kind === 'AE_TASK_STARTED' || item.kind === 'AE_TASK_COMPLETED') {
          const taskId = readNumber(payload, 'task_id')
          const topology = readString(payload, 'topology')
          const stage = readString(payload, 'stage')
          const trigger = readString(payload, 'intent_trigger')
          if (taskId !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Задача ID: '), h('strong', {}, String(taskId))]))
          if (topology) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Топология: '), h('strong', {}, topology)]))
          if (stage) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Стадия: '), h('strong', {}, stage)]))
          if (trigger) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Триггер: '), h('strong', {}, trigger)]))
        } else if (item.kind === 'AE_TASK_FAILED') {
          const taskId = readNumber(payload, 'task_id')
          const errorCode = readString(payload, 'error_code')
          const stage = readString(payload, 'stage')
          if (taskId !== null) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Задача ID: '), h('strong', {}, String(taskId))]))
          if (errorCode) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Код ошибки: '), h('strong', { class: 'text-red-500' }, errorCode)]))
          if (stage) detailRows.push(h('div', {}, [h('span', { class: 'text-[color:var(--text-dim)]' }, 'Стадия: '), h('strong', {}, stage)]))
        } else {
          // Generic / correction events
          const dose = firstNumber(payload, ['output', 'ml'])
          const error = firstNumber(payload, ['error', 'diff'])
          const current = firstNumber(payload, ['current', 'current_ph', 'current_ec'])
          const target = firstNumber(payload, ['target', 'target_ph', 'target_ec'])
          const zoneState = firstString(payload, ['zone_state', 'pid_zone'])
          const integral = readNumber(payload, 'integral_term')
          const component = firstString(payload, ['component', 'correction_type'])
          const reason = firstString(payload, ['reason', 'reason_code', 'safety_skip_reason'])
          if (dose !== null) detailRows.push(h('div', {}, ['Доза: ', h('strong', {}, `${formatPayloadNumber(dose, 3)} мл`)]))
          if (error !== null) detailRows.push(h('div', {}, ['Ошибка: ', h('strong', {}, formatPayloadNumber(error, 4))]))
          if (current !== null || target !== null) {
            detailRows.push(h('div', {}, [
              'Текущее: ', h('strong', {}, formatPayloadNumber(current, 3) ?? '—'),
              ' → Цель: ', h('strong', {}, formatPayloadNumber(target, 3) ?? '—'),
            ]))
          }
          if (zoneState) detailRows.push(h('div', {}, ['ПИД-зона: ', h('strong', {}, zoneState)]))
          if (integral !== null) detailRows.push(h('div', {}, ['Интеграл: ', h('strong', {}, formatPayloadNumber(integral, 4))]))
          if (component) detailRows.push(h('div', {}, ['Компонент: ', h('strong', {}, component)]))
          if (reason) detailRows.push(h('div', {}, ['Причина: ', h('strong', {}, reason)]))
        }
      }

      return h('div', {
        class: [
          'flex items-start gap-2 py-2 border-b border-[color:var(--border-muted)] rounded-lg px-1 transition-colors',
          canExpand ? 'cursor-pointer hover:bg-[color:var(--surface-muted)]/30 select-none' : '',
        ],
        onClick: canExpand ? () => emit('toggle') : undefined,
      }, [
        h(Badge, { variant: getEventVariant(item.kind), class: 'text-xs shrink-0 mt-0.5' }, () => translateEventKind(item.kind)),
        h('div', { class: 'flex-1 min-w-0' }, [
          h('div', { class: 'flex items-center justify-between gap-2' }, [
            h('div', { class: 'text-xs text-[color:var(--text-dim)]' },
              item.occurred_at ? new Date(item.occurred_at).toLocaleString('ru-RU') : '—'
            ),
            canExpand
              ? h('span', { class: 'text-[10px] text-[color:var(--text-dim)] shrink-0' }, expanded ? '▲' : '▼')
              : null,
          ]),
          h('div', { class: 'text-sm text-[color:var(--text-muted)] mt-0.5' }, item.message),
          expanded && detailRows.length > 0
            ? h('div', { class: 'mt-2 rounded-lg bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)] p-2.5 text-xs font-mono space-y-1' }, detailRows)
            : null,
        ]),
      ])
    }
  },
})

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
