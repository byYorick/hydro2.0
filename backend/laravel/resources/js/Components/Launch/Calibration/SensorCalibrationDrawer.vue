<template>
  <Teleport to="body">
    <transition name="hf-drawer">
      <div
        v-if="show"
        class="fixed inset-0 z-50 flex justify-end bg-black/45 backdrop-blur-sm"
        @click.self="onClose"
      >
        <aside
          class="w-[min(960px,98vw)] h-screen flex flex-col bg-[var(--bg-surface-strong)] border-l border-[var(--border-muted)] shadow-2xl"
          role="dialog"
          aria-modal="true"
        >
          <header
            class="flex items-start justify-between gap-3 px-4 py-3 border-b border-[var(--border-muted)] shrink-0"
          >
            <div class="min-w-0">
              <div class="text-sm font-semibold text-[var(--text-primary)]">
                Калибровка сенсора
              </div>
              <div class="font-mono text-[11px] text-[var(--text-dim)] mt-0.5 truncate">
                / зона#{{ zoneId }}
                <span v-if="selectedOverview"> / {{ selectedOverview.sensor_type.toUpperCase() }} · {{ selectedOverview.channel_uid }}</span>
              </div>
            </div>
            <button
              type="button"
              class="w-7 h-7 inline-flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
              @click="onClose"
            >
              <Ic name="x" />
            </button>
          </header>

          <div class="flex flex-1 min-h-0">
            <aside
              class="w-60 min-w-[240px] shrink-0 border-r border-[var(--border-muted)] bg-[var(--bg-surface)] p-3 flex flex-col gap-3 overflow-y-auto"
            >
              <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)]">
                каналы зоны
              </div>
              <div
                v-if="items.length === 0"
                class="text-xs text-[var(--text-muted)]"
              >
                Нет pH/EC каналов.
              </div>
              <ol
                v-else
                class="list-none m-0 p-0 flex flex-col gap-1.5"
              >
                <li
                  v-for="it in items"
                  :key="it.node_channel_id"
                >
                  <button
                    type="button"
                    class="w-full text-left rounded-md border px-2 py-2 text-xs transition-colors"
                    :class="channelBtnClass(it)"
                    @click="selectedOverview = it"
                  >
                    <div class="font-mono font-semibold">
                      {{ it.sensor_type.toUpperCase() }} · {{ it.channel_uid }}
                    </div>
                    <div class="text-[10px] text-[var(--text-dim)] truncate mt-0.5 font-mono">
                      {{ it.node_uid || 'unknown' }}
                    </div>
                    <div class="mt-1.5">
                      <Chip :tone="statusTone(it.calibration_status)">
                        {{ it.calibration_status }}
                      </Chip>
                    </div>
                  </button>
                </li>
              </ol>

              <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] mt-1">
                этапы
              </div>
              <ol class="list-none m-0 p-0 flex flex-col gap-1.5 text-[11px] text-[var(--text-muted)]">
                <li class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] px-2 py-1.5">
                  <span class="font-medium text-[var(--text-primary)]">1.</span> Подготовка → старт сессии
                </li>
                <li class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] px-2 py-1.5">
                  <span class="font-medium text-[var(--text-primary)]">2.</span> {{ step2SidebarLabel }}
                </li>
                <li class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] px-2 py-1.5">
                  <span class="font-medium text-[var(--text-primary)]">3.</span> {{ step3SidebarLabel }}
                </li>
              </ol>
            </aside>

            <section class="flex-1 min-w-0 overflow-y-auto p-4">
              <div
                v-if="!selectedOverview"
                class="text-sm text-[var(--text-muted)]"
              >
                Выберите канал слева.
              </div>
              <SensorCalibrationWizardCore
                v-else
                :key="selectedOverview.node_channel_id"
                :zone-id="zoneId"
                :overview="selectedOverview"
                :settings="settings"
                :active="show"
                @close="onClose"
                @session-finished="onSessionFinished"
              />
            </section>
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Ic from '@/Components/Icons/Ic.vue'
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

function channelBtnClass(it: SensorCalibrationOverview): string {
  const active = selectedOverview.value?.node_channel_id === it.node_channel_id
  return active
    ? 'border-brand bg-brand-soft text-brand-ink ring-2 ring-brand-soft'
    : 'border-[var(--border-muted)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)]'
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

function onClose(): void {
  emit('close')
}

function onSessionFinished(outcome: SensorCalibrationSessionOutcome): void {
  emit('session-finished', outcome)
}

watch(
  () => [props.show, props.initialChannelId] as const,
  ([open]) => {
    if (!open) {
      selectedOverview.value = null
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

