<template>
  <section
    v-if="lanes.length > 0"
    class="rounded-xl border border-dashed border-[color:var(--border-muted)] px-3 py-2"
    data-testid="scheduler-config-only"
  >
    <div class="text-[10px] text-[color:var(--text-muted)]">
      вне runtime (config-only):
    </div>
    <div class="mt-1 flex flex-wrap gap-1">
      <Badge
        v-for="lane in lanes"
        :key="labelFor(lane)"
        variant="secondary"
        size="xs"
      >
        {{ labelFor(lane) }}
      </Badge>
    </div>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'

export interface ConfigOnlyLane {
  task_type?: string | null
  label?: string | null
}

interface Props {
  lanes: Array<ConfigOnlyLane | string>
}

defineProps<Props>()

function labelFor(lane: ConfigOnlyLane | string): string {
  if (typeof lane === 'string') return lane
  return lane.label ?? lane.task_type ?? 'lane'
}
</script>
