<template>
  <div
    v-if="summary"
    class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 space-y-2"
    data-testid="irrigation-correction-summary"
  >
    <div class="text-xs font-semibold uppercase tracking-[0.08em] text-[color:var(--text-dim)]">
      Коррекция во время полива (настройки зоны)
    </div>
    <dl class="grid gap-2 text-xs sm:grid-cols-2">
      <div>
        <dt class="text-[color:var(--text-muted)]">
          Режим EC-дозирования
        </dt>
        <dd class="mt-0.5 font-medium text-[color:var(--text-primary)]">
          {{ ecDosingModeLabel }}
        </dd>
      </div>
      <div v-if="summary.dose_ec_channel">
        <dt class="text-[color:var(--text-muted)]">
          Канал EC (single)
        </dt>
        <dd class="mt-0.5 font-mono text-[color:var(--text-primary)]">
          {{ summary.dose_ec_channel }}
        </dd>
      </div>
      <div v-if="summary.correction_during_irrigation !== null">
        <dt class="text-[color:var(--text-muted)]">
          Коррекция при поливе
        </dt>
        <dd class="mt-0.5 text-[color:var(--text-primary)]">
          {{ summary.correction_during_irrigation ? 'Включена' : 'Выключена' }}
        </dd>
      </div>
      <div
        v-if="summary.ec_excluded_components?.length"
        class="sm:col-span-2"
      >
        <dt class="text-[color:var(--text-muted)]">
          Исключённые компоненты
        </dt>
        <dd class="mt-0.5 text-[color:var(--text-primary)]">
          {{ summary.ec_excluded_components.join(', ') }}
        </dd>
      </div>
      <div
        v-if="ratiosSummary"
        class="sm:col-span-2"
      >
        <dt class="text-[color:var(--text-muted)]">
          Доли компонентов (ratios)
        </dt>
        <dd class="mt-0.5 font-mono text-[color:var(--text-primary)] break-all">
          {{ ratiosSummary }}
        </dd>
      </div>
      <div
        v-if="policySummary"
        class="sm:col-span-2"
      >
        <dt class="text-[color:var(--text-muted)]">
          Политика EC (фаза irrigation)
        </dt>
        <dd class="mt-0.5 font-mono text-[color:var(--text-primary)] break-all">
          {{ policySummary }}
        </dd>
      </div>
    </dl>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { IrrigationCorrectionSummary } from '@/types'

const props = defineProps<{
  summary: IrrigationCorrectionSummary | null
}>()

const EC_DOSING_LABELS: Record<string, string> = {
  single: 'Одна доза (single)',
  multi_sequential: 'Пошагово, несколько компонентов (multi_sequential)',
}

const ecDosingModeLabel = computed((): string => {
  const raw = props.summary?.ec_dosing_mode?.trim().toLowerCase() || 'single'
  return EC_DOSING_LABELS[raw] || raw
})

const ratiosSummary = computed((): string | null => {
  const r = props.summary?.ec_component_ratios
  if (!r || typeof r !== 'object') return null
  const entries = Object.entries(r).filter(([, v]) => {
    const n = Number(v)
    return Number.isFinite(n) && n > 0
  })
  if (entries.length === 0) return null
  return entries.map(([k, v]) => `${k}: ${v}`).join(', ')
})

const policySummary = computed((): string | null => {
  const p = props.summary?.ec_component_policy_irrigation
  if (!p || typeof p !== 'object') return null
  const entries = Object.entries(p)
  if (entries.length === 0) return null
  return entries.map(([k, v]) => `${k}: ${v}`).join(', ')
})
</script>
