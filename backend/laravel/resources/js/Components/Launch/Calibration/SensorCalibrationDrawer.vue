<template>
  <Modal
    :open="show"
    title="Калибровка сенсора"
    placement="workspace"
    hide-default-cancel
    @close="onClose"
  >
    <div class="flex h-full min-h-0 flex-col">
      <div class="shrink-0 space-y-3 border-b border-[color:var(--border-muted)] px-4 py-3 sm:px-6">
        <label class="flex flex-col gap-2 text-xs sm:flex-row sm:items-center">
          <span class="shrink-0">Зона #{{ zoneId }} · канал</span>
          <select
            :value="selectedOverview?.node_channel_id ?? ''"
            class="input-select min-h-11 min-w-0 flex-1"
            aria-label="Канал сенсора"
            @change="requestChannel"
          >
            <option
              v-if="!items.length"
              value=""
            >Нет доступных pH/EC каналов</option>
            <option
              v-for="item in items"
              :key="item.node_channel_id"
              :value="item.node_channel_id"
            >{{ item.sensor_type.toUpperCase() }} · {{ item.node_uid }} · {{ item.channel_uid }}</option>
          </select>
          <Chip
            v-if="selectedOverview"
            :tone="statusTone(selectedOverview.calibration_status)"
          >{{ statusLabel(selectedOverview.calibration_status) }}</Chip>
        </label>
        <ol
          class="grid grid-cols-3 gap-2 text-[10px] sm:text-xs"
          aria-label="Последовательность калибровки"
        >
          <li class="rounded-lg bg-[color:var(--bg-elevated)] p-2">
            1. Подготовка
          </li><li class="rounded-lg bg-[color:var(--bg-elevated)] p-2">
            2. {{ step2SidebarLabel }}
          </li><li class="rounded-lg bg-[color:var(--bg-elevated)] p-2">
            3. {{ step3SidebarLabel }}
          </li>
        </ol>
      </div>
      <section class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
        <div
          v-show="pendingAction"
          ref="confirmationRef"
          :inert="pendingAction ? undefined : true"
          tabindex="-1"
          class="space-y-4 rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-4 focus:outline-none"
          role="alert"
        >
          <h2 class="font-semibold text-[color:var(--text-primary)]">
            {{ pendingAction === 'channel' ? 'Перейти к другому каналу?' : 'Закрыть окно калибровки?' }}
          </h2>
          <p>Несохранённые значения эталонов будут отброшены. Открытая сессия и отправленные команды продолжат выполняться; отмена сессии — отдельное действие.</p>
          <div class="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              @click="pendingAction = null"
            >
              Продолжить работу
            </Button><Button
              variant="danger"
              @click="confirmLeave"
            >
              {{ pendingAction === 'channel' ? 'Перейти без сохранения' : 'Закрыть без сохранения' }}
            </Button>
          </div>
        </div>
        <EmptyState
          v-if="!selectedOverview"
          title="Нет сенсора для калибровки"
          description="Привяжите pH/EC канал к зоне и откройте калибровку повторно."
        />
        <div
          v-else
          v-show="!pendingAction"
          :key="selectedOverview.node_channel_id"
          :inert="pendingAction ? true : undefined"
        >
          <SensorCalibrationWizardCore
            :zone-id="zoneId"
            :overview="selectedOverview"
            :settings="settings"
            :active="show"
            @close="onClose"
            @session-finished="onSessionFinished"
            @state-change="state = $event"
          />
        </div>
      </section>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import EmptyState from '@/Components/EmptyState.vue'
import SensorCalibrationWizardCore from '@/Components/SensorCalibrationWizardCore.vue'
import { Chip } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import type { SensorCalibrationOverview, SensorCalibrationSessionOutcome } from '@/types/SensorCalibration'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = withDefaults(
  defineProps<{
    show: boolean
    zoneId: number
    settings: SensorCalibrationSettings
    items: SensorCalibrationOverview[]
    /** Предвыбранный канал (из строки таблицы) */
    initialChannelId?: number | null
  }>(),
  {
    initialChannelId: null,
  },
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'session-finished', outcome: SensorCalibrationSessionOutcome): void
}>()

const selectedOverview = ref<SensorCalibrationOverview | null>(null)
const state = ref({ hasUnsavedInput: false, activeSession: false, busy: false })
const pendingAction = ref<'close' | 'channel' | null>(null)
const pendingChannel = ref<number | null>(null)
const confirmationRef = ref<HTMLElement | null>(null)
const statusLabel = (status: string) => ({ ok: 'Калибровка действительна', warning: 'Нужна проверка', critical: 'Нужна калибровка', never: 'Калибровка не выполнена' }[status] || 'Состояние неизвестно')
watch(pendingAction, async value => { if (value) { await nextTick(); confirmationRef.value?.focus() } })

const step2SidebarLabel = computed(() => {
  const t = selectedOverview.value?.sensor_type
  if (t === 'ph') return 'Точка 1 — кислый буфер'
  if (t === 'ec') return 'Точка 1 — меньший эталон TDS'
  return 'Точка 1'
})

const step3SidebarLabel = computed(() => {
  const t = selectedOverview.value?.sensor_type
  if (t === 'ph') return 'Точка 2 — щелочной буфер'
  if (t === 'ec') return 'Точка 2 — больший эталон TDS'
  return 'Точка 2'
})

function statusTone(status: SensorCalibrationOverview['calibration_status']): ChipTone {
  if (status === 'ok') return 'growth'
  if (status === 'warning') return 'warn'
  if (status === 'critical') return 'alert'
  return 'neutral'
}

function pickDefaultOverview(): SensorCalibrationOverview | null {
  if (props.items.length === 0) return null
  if (props.initialChannelId != null) {
    const hit = props.items.find((i) => i.node_channel_id === props.initialChannelId)
    if (hit) return hit
  }
  const needy = props.items.find((i) => i.calibration_status !== 'ok')
  return needy ?? props.items[0] ?? null
}

function needsConfirmation(): boolean { return state.value.hasUnsavedInput || state.value.activeSession || state.value.busy }
function onClose(): void {
  if (pendingAction.value) { pendingAction.value = null; return }
  if (needsConfirmation()) { pendingAction.value = 'close'; return }
  emit('close')
}
function requestChannel(event: Event): void {
  const select = event.target as HTMLSelectElement
  const id = Number(select.value)
  select.value = String(selectedOverview.value?.node_channel_id ?? '')
  if (id === selectedOverview.value?.node_channel_id) return
  if (needsConfirmation()) { pendingChannel.value = id; pendingAction.value = 'channel'; return }
  selectChannel(id)
}
function selectChannel(id: number): void {
  state.value = { hasUnsavedInput: false, activeSession: false, busy: false }
  selectedOverview.value = props.items.find(item => item.node_channel_id === id) ?? null
}
function confirmLeave(): void {
  const action = pendingAction.value
  pendingAction.value = null
  if (action === 'channel' && pendingChannel.value != null) selectChannel(pendingChannel.value)
  else emit('close')
}

function onSessionFinished(outcome: SensorCalibrationSessionOutcome): void {
  state.value = { hasUnsavedInput: outcome === 'failed' && state.value.hasUnsavedInput, activeSession: false, busy: false }
  emit('session-finished', outcome)
}

watch(
  () => [props.show, props.initialChannelId] as const,
  ([open]) => {
    if (!open) {
      selectedOverview.value = null
      state.value = { hasUnsavedInput: false, activeSession: false, busy: false }
      pendingAction.value = null
      return
    }
    selectedOverview.value = pickDefaultOverview()
  },
  { immediate: true },
)

watch(
  () => props.items,
  (items) => {
    if (!props.show || items.length === 0) {
      return
    }
    const cur = selectedOverview.value
    if (cur && items.some((i) => i.node_channel_id === cur.node_channel_id)) {
      return
    }
    if (!cur) {
      selectedOverview.value = pickDefaultOverview()
    }
  },
  { deep: true },
)
</script>

