<template>
  <section class="cal-sub">
    <header class="cal-sub__header">
      <div>
        <div class="cal-sub__breadcrumb">
          / зона / калибровка / насосы
        </div>
        <h3 class="cal-sub__title">
          Калибровка дозирующих насосов
        </h3>
        <p class="cal-sub__desc">
          Статус и история калибровки насосов, участвующих в коррекции на потоке.
          Предельные значения времени работы — в расширенных настройках ниже.
        </p>
      </div>
      <span class="cal-sub__progress">
        <span class="cal-sub__progress-dot"></span>
        {{ calibratedCount }} / {{ pumpRows.length }}
      </span>
    </header>

    <div class="cal-paths">
      <div class="cal-path">
        <div class="cal-path__head">
          <div class="cal-path__title">
            Контур дозирования EC
          </div>
          <div class="cal-path__meta">
            {{ ecComponents.length }} компонента · {{ ecDone }} готово
          </div>
        </div>
        <div class="cal-path__pills">
          <span
            v-for="p in ecComponents"
            :key="p.role"
            class="cal-pill"
            :class="pillClass(p)"
          >
            <span class="cal-pill__dot"></span>
            {{ p.shortLabel }}
          </span>
        </div>
      </div>
      <div class="cal-path">
        <div class="cal-path__head">
          <div class="cal-path__title">
            Контур дозирования pH
          </div>
          <div class="cal-path__meta">
            {{ phComponents.length }} компонента · {{ phDone }} готово
          </div>
        </div>
        <div class="cal-path__pills">
          <span
            v-for="p in phComponents"
            :key="p.role"
            class="cal-pill"
            :class="pillClass(p)"
          >
            <span class="cal-pill__dot"></span>
            {{ p.shortLabel }}
          </span>
        </div>
      </div>
    </div>

    <div class="cal-channels">
      <div class="cal-channels__head">
        <span>Каналы зоны</span>
        <span class="cal-channels__count">{{ pumpRows.length }} каналов</span>
      </div>
      <table class="cal-channels__table">
        <thead>
          <tr>
            <th>Компонент</th>
            <th>Канал</th>
            <th>мл/сек</th>
            <th>k · мс/(мл/л)</th>
            <th>Обновлено</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="p in pumpRows"
            :key="p.role"
            :class="`cal-channels__row--${p.state}`"
          >
            <td>{{ p.shortLabel }}</td>
            <td>
              <code v-if="p.channel">{{ p.nodeUid }} · {{ p.channel }}</code>
              <span
                v-else
                class="cal-channels__muted"
              >— не привязан</span>
            </td>
            <td>{{ formatFloat(p.mlPerSec, 2) }}</td>
            <td>{{ formatFloat(p.kFactor, 6) }}</td>
            <td>{{ p.updatedText }}</td>
            <td class="cal-channels__action">
              <button
                v-if="!p.canCalibrate"
                type="button"
                class="cal-btn cal-btn--ghost"
                :title="'Канал не привязан — привяжите на шаге «Автоматика»'"
                disabled
              >
                привязать канал
              </button>
              <button
                v-else-if="p.state === 'done'"
                type="button"
                class="cal-btn cal-btn--ghost"
                @click="$emit('calibrate', p)"
              >
                перекалибровать
              </button>
              <button
                v-else
                type="button"
                class="cal-btn cal-btn--primary"
                @click="$emit('calibrate', p)"
              >
                откалибровать
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="cal-sub__footer">
      <span class="cal-sub__hint">
        После калибровки всех обязательных компонентов подсистема разблокирует <strong>Процесс</strong>.
      </span>
      <div class="cal-sub__actions">
        <button
          type="button"
          class="cal-btn cal-btn--ghost"
          @click="$emit('export-csv')"
        >
          Экспорт CSV
        </button>
        <button
          type="button"
          class="cal-btn cal-btn--primary"
          @click="$emit('open-pump-wizard')"
        >
          Открыть калибровку насосов
        </button>
      </div>
    </footer>

    <details class="cal-sub__advanced">
      <summary>Пределы runtime (переопределение зоны) · min_dose_ms · диапазон мл/сек</summary>
      <div class="cal-sub__advanced-body">
        Расширенные границы runtime применяются только в переопределении зоны.
        Настройка доступна на странице <a
          :href="`/zones/${zoneId}/edit#pump-calibration`"
          target="_blank"
          rel="noopener"
        >/zones/{{ zoneId }}/edit</a>.
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { PumpCalibration } from '@/types/PidConfig';

export type PumpRowState = 'done' | 'pending' | 'optional';

export interface PumpRow {
    role: string;
    shortLabel: string;
    title: string;
    description: string;
    component: string;
    state: PumpRowState;
    channel: string | null;
    nodeUid: string | null;
    mlPerSec: number | null;
    kFactor: number | null;
    updatedAt: string | null;
    updatedText: string;
    canCalibrate: boolean;
    nodeChannelId: number | null;
    group: 'ec' | 'ph';
    required: boolean;
}

interface Props {
    zoneId: number;
    pumps: PumpCalibration[];
}

const props = defineProps<Props>();

defineEmits<{
    (e: 'calibrate', pump: PumpRow): void;
    (e: 'open-pump-wizard'): void;
    (e: 'export-csv'): void;
}>();

const CATALOG: Array<{
    role: string;
    shortLabel: string;
    title: string;
    description: string;
    component: string;
    group: 'ec' | 'ph';
    required: boolean;
}> = [
    { role: 'pump_a', shortLabel: 'NPK', title: 'Насос EC · NPK', description: 'Макро NPK', component: 'npk', group: 'ec', required: true },
    { role: 'pump_b', shortLabel: 'Calcium', title: 'Насос EC · Calcium', description: 'Кальций', component: 'calcium', group: 'ec', required: false },
    { role: 'pump_c', shortLabel: 'Magnesium', title: 'Насос EC · Magnesium', description: 'Магний', component: 'magnesium', group: 'ec', required: false },
    { role: 'pump_d', shortLabel: 'Micro', title: 'Насос EC · Micro', description: 'Микроэлементы', component: 'micro', group: 'ec', required: false },
    { role: 'pump_base', shortLabel: 'pH Up', title: 'Насос pH+', description: 'Щёлочь', component: 'ph_up', group: 'ph', required: true },
    { role: 'pump_acid', shortLabel: 'pH Down', title: 'Насос pH-', description: 'Кислота', component: 'ph_down', group: 'ph', required: true },
];

function formatRelative(dateStr: string | null): string {
    if (!dateStr) return 'никогда';
    const diffMs = Date.now() - new Date(dateStr).getTime();
    if (Number.isNaN(diffMs)) return 'никогда';
    const days = Math.floor(diffMs / 86_400_000);
    if (days === 0) return 'сегодня';
    if (days === 1) return 'вчера';
    if (days < 30) return `${days} дн. назад`;
    return `${Math.floor(days / 30)} мес. назад`;
}

function formatFloat(v: number | null, digits: number): string {
    if (v === null || !Number.isFinite(v)) return '—';
    return v.toFixed(digits);
}

function findPump(role: string): PumpCalibration | null {
    return props.pumps.find((p) => p.role === role) ?? null;
}

const pumpRows = computed<PumpRow[]>(() =>
    CATALOG.map((desc) => {
        const pump = findPump(desc.role);
        const calibrated = !!pump?.ml_per_sec && pump.ml_per_sec > 0;
        const hasBinding = pump !== null && pump.node_channel_id > 0;
        const state: PumpRowState = calibrated ? 'done' : desc.required ? 'pending' : 'optional';

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
        };
    }),
);

const ecComponents = computed(() => pumpRows.value.filter((p) => p.group === 'ec'));
const phComponents = computed(() => pumpRows.value.filter((p) => p.group === 'ph'));

const ecDone = computed(() => ecComponents.value.filter((p) => p.state === 'done').length);
const phDone = computed(() => phComponents.value.filter((p) => p.state === 'done').length);
const calibratedCount = computed(
    () => pumpRows.value.filter((p) => p.state === 'done').length,
);

function pillClass(p: PumpRow): string {
    return `cal-pill--${p.state}`;
}
</script>

<style scoped>
.cal-sub {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
}

.cal-sub__header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
    flex-wrap: wrap;
}

.cal-sub__breadcrumb {
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
    opacity: 0.55;
}

.cal-sub__title {
    font-size: 1rem;
    font-weight: 700;
    margin: 0.1rem 0 0.25rem;
}

.cal-sub__desc {
    margin: 0;
    font-size: 0.78rem;
    opacity: 0.7;
    max-width: 640px;
}

.cal-sub__progress {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.55rem;
    border-radius: 9999px;
    background: rgba(251, 191, 36, 0.1);
    border: 1px solid rgba(251, 191, 36, 0.3);
    color: rgb(234, 179, 8);
    font-size: 0.75rem;
    font-weight: 600;
}

.cal-sub__progress-dot {
    width: 6px;
    height: 6px;
    border-radius: 9999px;
    background: currentColor;
}

.cal-paths {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 0.5rem;
}

.cal-path {
    padding: 0.65rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.45rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
}

.cal-path__head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.5rem;
}

.cal-path__title {
    font-weight: 600;
    font-size: 0.85rem;
}

.cal-path__meta {
    font-size: 0.72rem;
    opacity: 0.65;
}

.cal-path__pills {
    display: flex;
    gap: 0.3rem;
    flex-wrap: wrap;
}

.cal-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.22rem 0.55rem;
    font-size: 0.75rem;
    border-radius: 9999px;
    border: 1px solid transparent;
    background: rgba(148, 163, 184, 0.08);
}

.cal-pill__dot {
    width: 6px;
    height: 6px;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.5);
}

.cal-pill--done {
    background: rgba(34, 197, 94, 0.08);
    border-color: rgba(34, 197, 94, 0.25);
    color: rgb(134, 239, 172);
}
.cal-pill--done .cal-pill__dot {
    background: rgb(34, 197, 94);
}

.cal-pill--pending {
    background: rgba(251, 191, 36, 0.08);
    border-color: rgba(251, 191, 36, 0.3);
    color: rgb(250, 204, 21);
}
.cal-pill--pending .cal-pill__dot {
    background: rgb(251, 191, 36);
}

.cal-pill--optional {
    opacity: 0.7;
}

.cal-channels {
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.5rem;
    overflow: hidden;
}

.cal-channels__head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.15);
    font-size: 0.85rem;
    font-weight: 600;
}

.cal-channels__count {
    font-size: 0.72rem;
    opacity: 0.6;
    font-weight: 500;
}

.cal-channels__table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
}

.cal-channels__table th {
    text-align: left;
    padding: 0.45rem 0.8rem;
    font-weight: 600;
    font-size: 0.66rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    opacity: 0.55;
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    background: rgba(148, 163, 184, 0.02);
}

.cal-channels__table td {
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    vertical-align: middle;
}

.cal-channels__table tr:last-child td {
    border-bottom: none;
}

.cal-channels__muted {
    opacity: 0.6;
    color: rgb(251, 113, 133);
}

.cal-channels__action {
    text-align: right;
    white-space: nowrap;
}

.cal-channels__row--pending td {
    background: rgba(251, 191, 36, 0.03);
}

.cal-channels__row--done td {
    background: rgba(34, 197, 94, 0.02);
}

.cal-btn {
    padding: 0.3rem 0.7rem;
    border-radius: 0.35rem;
    border: 1px solid transparent;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 500;
}

.cal-btn:disabled {
    cursor: not-allowed;
    opacity: 0.5;
}

.cal-btn--primary {
    background: rgb(56, 189, 248);
    color: #0f172a;
}
.cal-btn--primary:hover:not(:disabled) {
    background: rgb(14, 165, 233);
}

.cal-btn--ghost {
    border-color: rgba(148, 163, 184, 0.3);
}
.cal-btn--ghost:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.08);
}

.cal-sub__footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
    padding-top: 0.4rem;
    flex-wrap: wrap;
}

.cal-sub__hint {
    font-size: 0.75rem;
    opacity: 0.75;
}

.cal-sub__actions {
    display: flex;
    gap: 0.4rem;
}

.cal-sub__advanced {
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 0.4rem;
    font-size: 0.78rem;
}

.cal-sub__advanced summary {
    cursor: pointer;
    padding: 0.55rem 0.85rem;
    opacity: 0.75;
    list-style: none;
}

.cal-sub__advanced summary::before {
    content: '▸ ';
    opacity: 0.55;
}

.cal-sub__advanced[open] summary::before {
    content: '▾ ';
}

.cal-sub__advanced-body {
    padding: 0.55rem 0.85rem 0.75rem;
    opacity: 0.8;
    border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.cal-sub__advanced-body a {
    color: rgb(56, 189, 248);
}
</style>
