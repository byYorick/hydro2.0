<template>
  <section class="flex flex-col gap-3.5">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <p class="text-xs text-[var(--text-muted)] flex-1 min-w-0">
        Статус и история калибровки насосов, участвующих в коррекции на потоке.
        Предельные значения времени работы — в расширенных настройках ниже.
      </p>
      <Chip :tone="overallTone">
        <template #icon>
          <span
            class="inline-block w-1.5 h-1.5 rounded-full"
            :class="overallDotClass"
          />
        </template>
        <span class="font-mono">{{ calibratedCount }} / {{ pumpRows.length }}</span>
      </Chip>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <ShellCard
        v-for="path in paths"
        :key="path.group"
        :title="path.title"
      >
        <template #actions>
          <Chip :tone="path.done === path.total ? 'growth' : 'warn'">
            <span class="font-mono">{{ path.done }} / {{ path.total }}</span>
          </Chip>
        </template>
        <div class="flex flex-wrap gap-1.5">
          <Chip
            v-for="p in path.components"
            :key="p.role"
            :tone="rowTone(p)"
          >
            <template #icon>
              <span
                class="inline-block w-1.5 h-1.5 rounded-full"
                :class="rowDot(p)"
              />
            </template>
            {{ p.shortLabel }}
          </Chip>
        </div>
      </ShellCard>
    </div>

    <ShellCard
      title="Каналы зоны"
      :pad="false"
    >
      <template #actions>
        <Chip tone="neutral">
          <span class="font-mono">{{ pumpRows.length }} каналов</span>
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
              <th class="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in pumpRows"
              :key="p.role"
              class="border-t border-[var(--border-muted)]"
              :class="rowBgClass(p)"
            >
              <td class="px-3 py-2 font-medium">
                {{ p.shortLabel }}
              </td>
              <td class="px-3 py-2 font-mono text-xs">
                <span v-if="p.channel">{{ p.nodeUid }} · {{ p.channel }}</span>
                <span
                  v-else
                  class="text-[var(--text-dim)]"
                >— не привязан</span>
              </td>
              <td class="px-3 py-2 font-mono">
                {{ formatFloat(p.mlPerSec, 2) }}
              </td>
              <td class="px-3 py-2 font-mono">
                {{ formatFloat(p.kFactor, 6) }}
              </td>
              <td class="px-3 py-2 text-xs text-[var(--text-muted)]">
                {{ p.updatedText }}
              </td>
              <td class="px-3 py-2 text-right">
                <Button
                  v-if="!p.canCalibrate"
                  size="sm"
                  variant="secondary"
                  :disabled="true"
                  title="Канал не привязан — привяжите на шаге «Автоматика»"
                >
                  привязать канал
                </Button>
                <Button
                  v-else-if="p.state === 'done'"
                  size="sm"
                  variant="secondary"
                  @click="$emit('calibrate', p)"
                >
                  ↻ перекалибровать
                </Button>
                <Button
                  v-else
                  size="sm"
                  variant="secondary"
                  @click="$emit('calibrate', p)"
                >
                  откалибровать
                </Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </ShellCard>

    <div class="flex items-center justify-between gap-3 flex-wrap pt-2">
      <Hint :show="true">
        После калибровки всех обязательных компонентов подсистема разблокирует
        <strong>Процесс</strong>.
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
          @click="$emit('open-pump-wizard')"
        >
          ▶ Открыть калибровку насосов
        </Button>
      </div>
    </div>

    <details
      class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] px-3 py-2 text-xs"
    >
      <summary class="cursor-pointer text-[var(--text-muted)] font-medium">
        Пределы runtime (переопределение зоны) · min_dose_ms · диапазон мл/сек
      </summary>
      <div class="mt-2 text-[var(--text-muted)] leading-relaxed">
        Расширенные границы runtime применяются только в переопределении зоны.
        Настройка доступна на странице
        <a
          :href="`/zones/${zoneId}/edit#pump-calibration`"
          target="_blank"
          rel="noopener"
          class="text-brand hover:text-brand-ink font-mono"
        >/zones/{{ zoneId }}/edit</a>.
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import { Chip, Hint } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import type { PumpCalibration } from '@/types/PidConfig'

export type PumpRowState = 'done' | 'pending' | 'optional'

export interface PumpRow {
  role: string
  shortLabel: string
  title: string
  description: string
  component: string
  state: PumpRowState
  channel: string | null
  nodeUid: string | null
  mlPerSec: number | null
  kFactor: number | null
  updatedAt: string | null
  updatedText: string
  canCalibrate: boolean
  nodeChannelId: number | null
  group: 'ec' | 'ph'
  required: boolean
}

const props = defineProps<{
  zoneId: number
  pumps: PumpCalibration[]
}>()

defineEmits<{
  (e: 'calibrate', pump: PumpRow): void
  (e: 'open-pump-wizard'): void
  (e: 'export-csv'): void
}>()

const HEADERS = ['Компонент', 'Канал', 'мл/сек', 'k · мс/(мл/л)', 'Обновлено']

const CATALOG: Array<{
  role: string
  shortLabel: string
  title: string
  description: string
  component: string
  group: 'ec' | 'ph'
  required: boolean
}> = [
  { role: 'pump_a', shortLabel: 'NPK', title: 'Насос EC · NPK', description: 'Макро NPK', component: 'npk', group: 'ec', required: true },
  { role: 'pump_b', shortLabel: 'Calcium', title: 'Насос EC · Calcium', description: 'Кальций', component: 'calcium', group: 'ec', required: false },
  { role: 'pump_c', shortLabel: 'Magnesium', title: 'Насос EC · Magnesium', description: 'Магний', component: 'magnesium', group: 'ec', required: false },
  { role: 'pump_d', shortLabel: 'Micro', title: 'Насос EC · Micro', description: 'Микроэлементы', component: 'micro', group: 'ec', required: false },
  { role: 'pump_base', shortLabel: 'pH Up', title: 'Насос pH+', description: 'Щёлочь', component: 'ph_up', group: 'ph', required: true },
  { role: 'pump_acid', shortLabel: 'pH Down', title: 'Насос pH-', description: 'Кислота', component: 'ph_down', group: 'ph', required: true },
]

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

function formatFloat(v: number | null, digits: number): string {
  if (v === null || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

function findPump(role: string): PumpCalibration | null {
  return props.pumps.find((p) => p.role === role) ?? null
}

const pumpRows = computed<PumpRow[]>(() =>
  CATALOG.map((desc) => {
    const pump = findPump(desc.role)
    const calibrated = !!pump?.ml_per_sec && pump.ml_per_sec > 0
    const hasBinding = pump !== null && pump.node_channel_id > 0
    const state: PumpRowState = calibrated ? 'done' : desc.required ? 'pending' : 'optional'

    return {
      role: desc.role,
      shortLabel: desc.shortLabel,
      title: desc.title,
      description: desc.description,
      component: desc.component,
      state,
      channel: pump?.channel ?? null,
      nodeUid: pump?.node_uid ?? null,
      mlPerSec: pump?.ml_per_sec ?? null,
      kFactor: pump?.k_ms_per_ml_l ?? null,
      updatedAt: pump?.valid_from ?? null,
      updatedText: formatRelative(pump?.valid_from ?? null),
      canCalibrate: hasBinding,
      nodeChannelId: pump?.node_channel_id ?? null,
      group: desc.group,
      required: desc.required,
    }
  }),
)

const calibratedCount = computed(
  () => pumpRows.value.filter((p) => p.state === 'done').length,
)

const overallTone = computed<ChipTone>(() => {
  if (calibratedCount.value === pumpRows.value.length) return 'growth'
  if (pumpRows.value.some((p) => p.state === 'pending')) return 'warn'
  return 'neutral'
})

const overallDotClass = computed(() =>
  overallTone.value === 'growth'
    ? 'bg-growth'
    : overallTone.value === 'warn'
      ? 'bg-warn'
      : 'bg-[var(--text-dim)]',
)

const paths = computed(() => {
  const ec = pumpRows.value.filter((p) => p.group === 'ec')
  const ph = pumpRows.value.filter((p) => p.group === 'ph')
  return [
    {
      group: 'ec' as const,
      title: 'Контур дозирования EC',
      components: ec,
      total: ec.length,
      done: ec.filter((p) => p.state === 'done').length,
    },
    {
      group: 'ph' as const,
      title: 'Контур дозирования pH',
      components: ph,
      total: ph.length,
      done: ph.filter((p) => p.state === 'done').length,
    },
  ]
})

function rowTone(p: PumpRow): ChipTone {
  if (p.state === 'done') return 'growth'
  if (p.state === 'pending') return 'warn'
  return 'neutral'
}

function rowDot(p: PumpRow): string {
  if (p.state === 'done') return 'bg-growth'
  if (p.state === 'pending') return 'bg-warn'
  return 'bg-[var(--text-dim)]'
}

function rowBgClass(p: PumpRow): string {
  if (p.state === 'done') return 'bg-growth-soft/30'
  return ''
}
</script>
