<template>
  <section class="flex flex-col gap-3.5">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <p class="text-xs text-[var(--text-muted)] flex-1 min-w-0">
        Двухточечная калибровка pH/EC буферами. AE3 хранит offset/slope и применяет к raw из mqtt-bridge.
      </p>
      <Chip :tone="overallTone">
        <template #icon>
          <span
            class="inline-block w-1.5 h-1.5 rounded-full"
            :class="overallDotClass"
          ></span>
        </template>
        <span class="font-mono">{{ okCount }} / {{ items.length }}</span>
      </Chip>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <ShellCard
        title="Контур pH"
      >
        <template #actions>
          <Chip :tone="phDone === phTotal && phTotal > 0 ? 'growth' : phTotal > 0 ? 'warn' : 'neutral'">
            <span class="font-mono">{{ phDone }} / {{ phTotal }}</span>
          </Chip>
        </template>
        <div class="flex flex-wrap gap-1.5">
          <Chip
            v-for="it in phItems"
            :key="it.node_channel_id"
            :tone="rowTone(it.calibration_status)"
          >
            <template #icon>
              <span
                class="inline-block w-1.5 h-1.5 rounded-full"
                :class="rowDot(it.calibration_status)"
              ></span>
            </template>
            {{ it.channel_uid }}
          </Chip>
          <span
            v-if="phItems.length === 0"
            class="text-xs text-[var(--text-dim)]"
          >—</span>
        </div>
      </ShellCard>

      <ShellCard
        title="Контур EC"
      >
        <template #actions>
          <Chip :tone="ecDone === ecTotal && ecTotal > 0 ? 'growth' : ecTotal > 0 ? 'warn' : 'neutral'">
            <span class="font-mono">{{ ecDone }} / {{ ecTotal }}</span>
          </Chip>
        </template>
        <div class="flex flex-wrap gap-1.5">
          <Chip
            v-for="it in ecItems"
            :key="it.node_channel_id"
            :tone="rowTone(it.calibration_status)"
          >
            <template #icon>
              <span
                class="inline-block w-1.5 h-1.5 rounded-full"
                :class="rowDot(it.calibration_status)"
              ></span>
            </template>
            {{ it.channel_uid }}
          </Chip>
          <span
            v-if="ecItems.length === 0"
            class="text-xs text-[var(--text-dim)]"
          >—</span>
        </div>
      </ShellCard>
    </div>

    <ShellCard
      title="Каналы зоны"
      :pad="false"
    >
      <template #actions>
        <Chip tone="neutral">
          <span class="font-mono">{{ items.length }} каналов</span>
        </Chip>
      </template>
      <div class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-[var(--bg-elevated)]">
              <th
                v-for="col in HEADERS"
                :key="col"
                class="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--text-dim)] font-semibold whitespace-nowrap"
              >
                {{ col }}
              </th>
              <th class="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="it in items"
              :key="it.node_channel_id"
              class="border-t border-[var(--border-muted)]"
              :class="rowBgClass(it.calibration_status)"
            >
              <td class="px-3 py-2 font-medium font-mono">
                {{ it.sensor_type.toUpperCase() }}
              </td>
              <td class="px-3 py-2 font-mono text-xs">
                {{ it.node_uid || '—' }} · {{ it.channel_uid }}
              </td>
              <td class="px-3 py-2">
                <Chip :tone="rowTone(it.calibration_status)">
                  {{ it.calibration_status }}
                </Chip>
              </td>
              <td class="px-3 py-2 text-xs text-[var(--text-muted)]">
                {{ formatRelative(it.last_calibrated_at) }}
              </td>
              <td class="px-3 py-2 text-right flex flex-wrap gap-1.5 justify-end">
                <Button
                  size="sm"
                  variant="secondary"
                  @click="$emit('open-history', it)"
                >
                  История
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  @click="$emit('calibrate', it)"
                >
                  {{ it.calibration_status === 'ok' ? '↻ перекалибровать' : 'откалибровать' }}
                </Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-if="items.length === 0"
        class="px-3 py-6 text-sm text-[var(--text-dim)]"
      >
        В зоне не найдены pH/EC sensor channels.
      </div>
    </ShellCard>

    <div class="flex items-center justify-between gap-3 flex-wrap pt-2">
      <Hint :show="true">
        После калибровки сенсоров проверьте статус в readiness-bar и перейдите к
        <strong>насосам</strong>.
      </Hint>
      <div class="flex gap-1.5 flex-wrap">
        <Button
          size="sm"
          variant="secondary"
          @click="$emit('export-csv')"
        >
          Экспорт CSV
        </Button>
        <Button
          size="sm"
          variant="primary"
          :disabled="items.length === 0"
          @click="$emit('open-sensor-drawer')"
        >
          ▶ Открыть калибровку сенсоров
        </Button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import { Chip, Hint } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import type { SensorCalibrationOverview } from '@/types/SensorCalibration'

const props = defineProps<{
  zoneId: number
  items: SensorCalibrationOverview[]
}>()

defineEmits<{
  (e: 'calibrate', item: SensorCalibrationOverview): void
  (e: 'open-sensor-drawer'): void
  (e: 'export-csv'): void
  (e: 'open-history', item: SensorCalibrationOverview): void
}>()

const HEADERS = ['Тип', 'Канал', 'Статус', 'Калибровка']

const phItems = computed(() => props.items.filter((i) => i.sensor_type === 'ph'))
const ecItems = computed(() => props.items.filter((i) => i.sensor_type === 'ec'))

const okCount = computed(() => props.items.filter((i) => i.calibration_status === 'ok').length)

const phTotal = computed(() => phItems.value.length)
const phDone = computed(() => phItems.value.filter((i) => i.calibration_status === 'ok').length)
const ecTotal = computed(() => ecItems.value.length)
const ecDone = computed(() => ecItems.value.filter((i) => i.calibration_status === 'ok').length)

const overallTone = computed<ChipTone>(() => {
  if (props.items.length === 0) return 'neutral'
  if (okCount.value === props.items.length) return 'growth'
  if (props.items.some((i) => i.calibration_status === 'critical')) return 'alert'
  return 'warn'
})

const overallDotClass = computed(() =>
  overallTone.value === 'growth'
    ? 'bg-growth'
    : overallTone.value === 'alert'
      ? 'bg-warn'
      : overallTone.value === 'warn'
        ? 'bg-warn'
        : 'bg-[var(--text-dim)]',
)

function rowTone(status: SensorCalibrationOverview['calibration_status']): ChipTone {
  if (status === 'ok') return 'growth'
  if (status === 'warning') return 'warn'
  if (status === 'critical') return 'alert'
  return 'neutral'
}

function rowDot(status: SensorCalibrationOverview['calibration_status']): string {
  if (status === 'ok') return 'bg-growth'
  if (status === 'warning' || status === 'critical') return 'bg-warn'
  return 'bg-[var(--text-dim)]'
}

function rowBgClass(status: SensorCalibrationOverview['calibration_status']): string {
  if (status === 'ok') return 'bg-growth-soft/30'
  return ''
}

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return 'никогда'
  const diffMs = Date.now() - new Date(dateStr).getTime()
  if (Number.isNaN(diffMs)) return 'никогда'
  const days = Math.floor(diffMs / 86_400_000)
  if (days === 0) return 'сегодня'
  if (days === 1) return 'вчера'
  if (days < 30) return `${days} дн. назад`
  return `${Math.floor(days / 30)} мес. назад`
}
</script>