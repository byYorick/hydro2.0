<template>
  <section
    class="flex flex-col gap-2 px-3.5 py-2.5 border border-[var(--border-muted)] rounded-md bg-[var(--bg-surface)]"
  >
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div class="flex items-center gap-2.5">
        <Chip :tone="summary.blockers === 0 ? 'growth' : 'warn'">
          <template #icon>
            <span class="font-mono text-[11px]">{{ summary.blockers === 0 ? '✓' : '!' }}</span>
          </template>
          Калибровка
          <span class="font-mono ml-1">{{ summary.passed }}/{{ summary.total }}</span>
        </Chip>
        <span
          class="w-px h-5 bg-[var(--border-muted)]"
          aria-hidden="true"
        ></span>
        <span class="text-xs text-[var(--text-muted)]">
          {{ summary.blockers === 0
            ? 'все обязательные контракты пройдены'
            : `${summary.blockers} блокер(а)` }}
        </span>
      </div>

      <div class="flex items-center gap-1.5 flex-wrap">
        <button
          v-for="contract in blockerContracts"
          :key="contract.id"
          type="button"
          class="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-mono rounded-full border bg-warn-soft text-warn border-warn-soft cursor-pointer"
          @click="$emit('open-contract', contract)"
        >
          <span class="inline-block w-1.5 h-1.5 rounded-full bg-warn"></span>
          {{ contract.subsystem }} · {{ contract.component }}
        </button>
        <Button
          v-if="blockerContracts.length > 0"
          size="sm"
          variant="secondary"
          @click="$emit('open-blockers')"
        >
          детали
        </Button>
        <Button
          size="sm"
          variant="primary"
          @click="$emit('open-pump-wizard')"
        >
          Калибровка насосов
        </Button>
      </div>
    </div>

    <div class="flex gap-[3px] h-[7px]">
      <span
        v-for="contract in contracts"
        :key="contract.id"
        :class="[
          'flex-1 rounded-sm transition-colors',
          {
            'bg-growth': contract.status === 'passed',
            'bg-warn': contract.status === 'blocker',
            'bg-brand': contract.status === 'active',
            'bg-[var(--border-muted)]': contract.status === 'optional',
          },
        ]"
        :title="`${contract.title}: ${statusLabel(contract.status)}`"
      ></span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import Chip from '@/Components/Shared/Primitives/Chip.vue'
import type {
  CalibrationContract,
  ContractStatus,
} from '@/composables/useCalibrationContracts'

const props = defineProps<{
  contracts: CalibrationContract[]
  summary: { passed: number; total: number; blockers: number }
}>()

defineEmits<{
  (e: 'open-blockers'): void
  (e: 'open-pump-wizard'): void
  (e: 'open-contract', contract: CalibrationContract): void
}>()

const blockerContracts = computed(() =>
  props.contracts.filter((c) => c.status === 'blocker'),
)

function statusLabel(status: ContractStatus): string {
  switch (status) {
    case 'passed':
      return 'пройден'
    case 'blocker':
      return 'блокер'
    case 'active':
      return 'активный'
    default:
      return 'опциональный'
  }
}
</script>
