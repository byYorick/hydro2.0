<template>
  <div
    class="relative flex gap-3 px-1 py-2"
    :class="canExpand ? 'cursor-pointer select-none' : ''"
    @click="canExpand ? $emit('toggle') : undefined"
  >
    <div class="relative flex w-4 shrink-0 justify-center">
      <span
        class="mt-1.5 h-2 w-2 rounded-full shrink-0"
        :class="eventDotClass(item.kind)"
      />
    </div>

    <div class="min-w-0 flex-1">
      <div class="flex items-start justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <Badge
            :variant="getEventVariant(item.kind)"
            class="text-xs shrink-0"
          >
            {{ translateEventKind(item.kind) }}
          </Badge>
          <span class="text-xs text-[color:var(--text-dim)]">
            {{ item.occurred_at ? new Date(item.occurred_at).toLocaleString('ru-RU') : '—' }}
          </span>
        </div>
        <span
          v-if="canExpand"
          class="shrink-0 text-[10px] text-[color:var(--text-dim)]"
        >
          {{ expanded ? '▲' : '▼' }}
        </span>
      </div>

      <p class="mt-0.5 text-sm text-[color:var(--text-muted)]">
        {{ item.message }}
      </p>

      <div
        v-if="expanded && details.length > 0"
        class="mt-2 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
      >
        <div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs font-mono">
          <template
            v-for="detail in details"
            :key="detail.label"
          >
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">{{ detail.label }}:</span>
            <strong
              :class="detail.variant === 'error' ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-primary)]'"
            >
              {{ detail.value }}
            </strong>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import { translateEventKind } from '@/utils/i18n'
import { buildEventDetails } from '@/utils/eventDetails'
import { eventDotClass, getEventVariant, hasExpandablePayload } from '@/utils/eventPayload'
import type { ZoneEvent } from '@/types/ZoneEvent'

const props = defineProps<{
  item: ZoneEvent
  expanded: boolean
}>()

defineEmits<{
  toggle: []
}>()

const canExpand = computed(() => hasExpandablePayload(props.item))
const details = computed(() => props.expanded ? buildEventDetails(props.item) : [])
</script>
