<template>
  <div class="border border-[var(--border-muted)] rounded-md overflow-hidden">
    <div
      class="grid items-center px-3 py-2 bg-[var(--bg-elevated)] text-[11px] uppercase tracking-wider text-[var(--text-dim)]"
      style="grid-template-columns: 24px 1.4fr 1fr 1fr 90px"
    >
      <span aria-hidden="true" />
      <span>Имя</span>
      <span>Культура</span>
      <span>Стадия</span>
      <span>Статус</span>
    </div>

    <button
      v-for="zone in zones"
      :key="zone.id"
      type="button"
      :aria-current="activeId === zone.id ? 'true' : undefined"
      class="grid w-full items-center px-3 py-2.5 text-left border-t border-[var(--border-muted)] cursor-pointer transition-colors"
      :class="activeId === zone.id ? 'bg-brand-soft' : 'bg-transparent hover:bg-[var(--bg-elevated)]'"
      style="grid-template-columns: 24px 1.4fr 1fr 1fr 90px"
      @click="$emit('pick', zone.id)"
    >
      <span class="flex items-center">
        <span
          class="inline-block w-2.5 h-2.5 rounded-full"
          :class="activeId === zone.id ? 'bg-brand' : 'bg-[var(--border-strong)]'"
        />
      </span>
      <span class="text-sm font-medium text-[var(--text-primary)] truncate">{{ zone.name }}</span>
      <span class="text-xs text-[var(--text-muted)] truncate">{{ zone.plant ?? '—' }}</span>
      <span class="font-mono text-[11px] text-[var(--text-muted)] truncate">{{ zone.stage ?? '—' }}</span>
      <span>
        <Chip :tone="statusTone(zone.status)">{{ statusLabel(zone.status) }}</Chip>
      </span>
    </button>

    <div
      v-if="zones.length === 0"
      class="px-3 py-6 text-center text-xs text-[var(--text-dim)] border-t border-[var(--border-muted)]"
    >
      В выбранной теплице нет зон
    </div>
  </div>
</template>

<script setup lang="ts">
import Chip from '@/Components/Shared/Primitives/Chip.vue'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'

export interface ZoneListItem {
  id: number
  name: string
  description?: string | null
  status?: string | null
  /** Имя культуры (zone.activeGrowCycle.plant.name). */
  plant?: string | null
  /** Текущая стадия (например «Vegetation d42»). */
  stage?: string | null
}

defineProps<{
  zones: readonly ZoneListItem[]
  activeId?: number | null
}>()

defineEmits<{ (e: 'pick', id: number): void }>()

function statusTone(raw: string | null | undefined): ChipTone {
  const s = (raw ?? '').toLowerCase()
  if (s.includes('run')) return 'growth'
  if (s.includes('draft') || s.includes('stop') || s.includes('paus')) return 'warn'
  if (s.includes('error') || s.includes('fail')) return 'alert'
  return 'neutral'
}

function statusLabel(raw: string | null | undefined): string {
  const s = (raw ?? '').toLowerCase()
  if (s.includes('run')) return 'активна'
  if (s.includes('draft')) return 'черновик'
  if (s.includes('stop')) return 'остановлена'
  if (s.includes('paus')) return 'на паузе'
  if (s.includes('error') || s.includes('fail')) return 'ошибка'
  return raw || 'idle'
}
</script>
