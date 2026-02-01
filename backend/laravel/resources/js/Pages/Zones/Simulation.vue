<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div class="text-xs text-[color:var(--text-dim)]">
              Симуляция цифрового двойника
            </div>
            <div class="mt-1 flex flex-wrap items-center gap-2">
              <h1 class="text-lg font-semibold text-[color:var(--text-primary)]">
                {{ zone.name }}
              </h1>
              <Badge :variant="statusVariant">
                {{ translateStatus(zone.status) }}
              </Badge>
            </div>
            <div class="mt-1 text-xs text-[color:var(--text-muted)]">
              Теплица: {{ zone.greenhouse?.name || '—' }}
            </div>
          </div>
          <Link :href="`/zones/${zone.id}`">
            <Button
              size="sm"
              variant="outline"
            >
              Назад к зоне
            </Button>
          </Link>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              pH
            </div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">
              {{ formatValue(telemetry?.ph, 2) }}
            </div>
          </div>
          <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              EC
            </div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">
              {{ formatValue(telemetry?.ec, 2) }}
            </div>
          </div>
          <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              Температура
            </div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">
              {{ formatValue(telemetry?.temperature, 1) }} °C
            </div>
          </div>
          <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              Влажность
            </div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">
              {{ formatValue(telemetry?.humidity, 0) }} %
            </div>
          </div>
        </div>
      </div>

      <ZoneSimulationModal
        mode="page"
        :zone-id="zoneId"
        :default-recipe-id="defaultRecipeId"
        :initial-telemetry="telemetry"
        :active-simulation-id="activeSimulationId"
        :active-simulation-status="activeSimulationStatus"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Badge, { type BadgeVariant } from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import ZoneSimulationModal from '@/Components/ZoneSimulationModal.vue'
import { translateStatus } from '@/utils/i18n'
import type { Zone, ZoneTelemetry } from '@/types'

interface Props {
  zoneId: number
  zone: Zone
  telemetry?: ZoneTelemetry | null
  active_grow_cycle?: any
  active_simulation?: { id: number; status: string } | null
}

const props = defineProps<Props>()

const defaultRecipeId = computed(() => props.active_grow_cycle?.recipeRevision?.recipe_id ?? null)
const activeSimulationId = computed(() => props.active_simulation?.id ?? null)
const activeSimulationStatus = computed(() => props.active_simulation?.status ?? null)

const statusVariant = computed<BadgeVariant>(() => {
  switch (props.zone.status) {
    case 'RUNNING':
      return 'success'
    case 'PAUSED':
      return 'neutral'
    case 'WARNING':
      return 'warning'
    case 'ALARM':
      return 'danger'
    default:
      return 'neutral'
  }
})

const formatValue = (value?: number | null, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  return Number(value).toFixed(digits)
}
</script>
