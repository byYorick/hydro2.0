<template>
  <div
    v-if="phases.length"
    class="border border-[var(--border-muted)] rounded-md bg-[var(--bg-elevated)] overflow-hidden"
  >
    <div class="flex items-center gap-2 px-3 py-2 border-b border-[var(--border-muted)] bg-[var(--bg-surface)]">
      <Ic
        name="leaf"
        class="text-brand"
      />
      <span class="text-xs font-semibold text-[var(--text-primary)]">Сводка фаз рецепта</span>
      <Chip
        tone="brand"
        class="ml-auto"
      >
        <span class="font-mono">{{ phases.length }}</span>
      </Chip>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full border-collapse text-xs">
        <thead>
          <tr class="bg-[var(--bg-elevated)]">
            <th
              v-for="col in HEADERS"
              :key="col"
              class="text-left px-2 py-1.5 font-semibold text-[10px] uppercase tracking-wider text-[var(--text-dim)] border-b border-[var(--border-muted)] whitespace-nowrap"
            >
              {{ col }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(phase, index) in rows"
            :key="index"
            class="border-b border-[var(--border-muted)] hover:bg-[var(--bg-elevated)]/50 last:border-b-0"
          >
            <td class="px-2 py-1.5 align-top">
              <span class="font-semibold whitespace-nowrap">{{ phase.name || `Фаза ${index + 1}` }}</span>
            </td>
            <td class="px-2 py-1.5 align-top font-mono">
              {{ phase.duration }}
            </td>
            <td class="px-2 py-1.5 align-top font-mono">
              <div>{{ phase.phTarget }}</div>
              <div class="text-[10px] text-[var(--text-dim)]">
                {{ phase.phRange }}
              </div>
            </td>
            <td class="px-2 py-1.5 align-top font-mono">
              <div>{{ phase.ecTarget }}</div>
              <div class="text-[10px] text-[var(--text-dim)]">
                {{ phase.ecRange }}
              </div>
            </td>
            <td class="px-2 py-1.5 align-top">
              <template v-if="phase.dayNight.temp">
                <span :class="dnCls">день {{ phase.dayNight.temp.day }}</span>
                <span :class="dnCls">ночь {{ phase.dayNight.temp.night }}</span>
              </template>
              <span
                v-else
                class="font-mono"
              >{{ phase.tempFlat }}</span>
            </td>
            <td class="px-2 py-1.5 align-top">
              <template v-if="phase.dayNight.humidity">
                <span :class="dnCls">день {{ phase.dayNight.humidity.day }}</span>
                <span :class="dnCls">ночь {{ phase.dayNight.humidity.night }}</span>
              </template>
              <span
                v-else
                class="font-mono"
              >{{ phase.humidityFlat }}</span>
            </td>
            <td class="px-2 py-1.5 align-top font-mono">
              <div>{{ phase.lighting }}</div>
              <div
                v-if="phase.lightStart"
                class="text-[10px] text-[var(--text-dim)]"
              >
                с {{ phase.lightStart }}
              </div>
            </td>
            <td class="px-2 py-1.5 align-top font-mono">
              <div>{{ phase.irrigation }}</div>
              <div
                v-if="phase.irrigationMode"
                class="text-[10px] text-[var(--text-dim)]"
              >
                {{ phase.irrigationMode }}
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Ic from '@/Components/Icons/Ic.vue'
import { Chip } from '@/Components/Shared/Primitives'

interface RawPhase {
  name?: string | null
  duration_hours?: number | null
  duration_days?: number | null
  ph_target?: number | null
  ph_min?: number | null
  ph_max?: number | null
  ec_target?: number | null
  ec_min?: number | null
  ec_max?: number | null
  temp_air_target?: number | null
  humidity_target?: number | null
  lighting_photoperiod_hours?: number | null
  lighting_start_time?: string | null
  irrigation_interval_sec?: number | null
  irrigation_duration_sec?: number | null
  irrigation_mode?: string | null
  extensions?: Record<string, unknown> | null
}

const props = withDefaults(
  defineProps<{ phases: RawPhase[] }>(),
  { phases: () => [] },
)

const HEADERS = ['Фаза', 'Длит.', 'pH', 'EC (mS/cm)', 'T °C', 'Вл. %', 'Свет', 'Полив']

const dnCls =
  'inline-block px-1.5 py-px rounded-sm text-[10px] font-mono mr-1 last:mr-0 bg-brand-soft text-brand-ink'

function num(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function fmt(value: number | null, digits = 1): string {
  if (value === null) return '—'
  const rounded = Math.round(value * Math.pow(10, digits)) / Math.pow(10, digits)
  return rounded.toFixed(digits).replace(/\.0+$/, '')
}

function fmtInt(value: number | null): string {
  if (value === null) return '—'
  return String(Math.round(value))
}

function getDayNight(
  ext: Record<string, unknown> | null | undefined,
  key: 'temperature' | 'humidity',
): { day: string; night: string } | null {
  if (!ext || typeof ext !== 'object') return null
  const dn = (ext as { day_night?: Record<string, unknown> })?.day_night
  if (!dn || typeof dn !== 'object') return null
  const block = (dn as Record<string, unknown>)[key]
  if (!block || typeof block !== 'object') return null
  const b = block as { day?: unknown; night?: unknown }
  const day = num(b.day)
  const night = num(b.night)
  if (day === null && night === null) return null
  return {
    day: key === 'humidity' ? fmtInt(day) : fmt(day, 1),
    night: key === 'humidity' ? fmtInt(night) : fmt(night, 1),
  }
}

function durationLabel(phase: RawPhase): string {
  const hours = num(phase.duration_hours)
  const days = num(phase.duration_days)
  if (days !== null && days >= 1) return `${fmt(days, 1)} д.`
  if (hours !== null && hours > 0) return `${fmt(hours, 0)} ч`
  return '—'
}

function lightingLabel(phase: RawPhase): string {
  const hrs = num(phase.lighting_photoperiod_hours)
  if (hrs === null) return '—'
  return `${fmtInt(hrs)} ч`
}

function irrigationLabel(phase: RawPhase): string {
  const interval = num(phase.irrigation_interval_sec)
  const duration = num(phase.irrigation_duration_sec)
  if (interval === null && duration === null) return '—'
  const parts: string[] = []
  if (interval !== null) parts.push(`каждые ${Math.round(interval / 60)} мин`)
  if (duration !== null) parts.push(`×${duration} с`)
  return parts.join(' ')
}

const rows = computed(() =>
  props.phases.map((phase) => ({
    name: phase.name || '',
    duration: durationLabel(phase),
    phTarget: fmt(num(phase.ph_target), 1),
    phRange: `${fmt(num(phase.ph_min), 1)} – ${fmt(num(phase.ph_max), 1)}`,
    ecTarget: fmt(num(phase.ec_target), 1),
    ecRange: `${fmt(num(phase.ec_min), 1)} – ${fmt(num(phase.ec_max), 1)}`,
    tempFlat: fmt(num(phase.temp_air_target), 1),
    humidityFlat: fmtInt(num(phase.humidity_target)),
    dayNight: {
      temp: getDayNight(phase.extensions as Record<string, unknown> | null, 'temperature'),
      humidity: getDayNight(phase.extensions as Record<string, unknown> | null, 'humidity'),
    },
    lighting: lightingLabel(phase),
    lightStart: phase.lighting_start_time || '',
    irrigation: irrigationLabel(phase),
    irrigationMode: phase.irrigation_mode || '',
  })),
)
</script>
