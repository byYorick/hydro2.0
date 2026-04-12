<template>
  <div
    class="relative flex items-start gap-2 px-2.5 py-1.5 transition-colors"
    :class="canExpand ? 'cursor-pointer hover:bg-[color:var(--bg-elevated)]/40 select-none' : ''"
    @click="canExpand ? $emit('toggle') : undefined"
  >
    <!-- Цветная точка -->
    <div class="flex shrink-0 items-center pt-[5px]">
      <span class="h-1.5 w-1.5 rounded-full shrink-0" :class="eventDotClass(item.kind)"></span>
    </div>

    <div class="min-w-0 flex-1">
      <!-- Строка: бейдж + время + стрелка -->
      <div class="flex flex-wrap items-center gap-1">
        <Badge :variant="getEventVariant(item.kind)" size="sm">
          {{ translateEventKind(item.kind) }}
        </Badge>
        <span class="text-[10px] text-[color:var(--text-muted)]">
          {{ item.occurred_at ? new Date(item.occurred_at).toLocaleString('ru-RU') : '—' }}
        </span>
        <span
          v-if="canExpand"
          class="ml-auto shrink-0 text-[10px] text-[color:var(--text-dim)]"
        >
          {{ expanded ? '▲' : '▼' }}
        </span>
      </div>

      <!-- Сообщение -->
      <p
        v-if="item.message"
        class="mt-0.5 text-[11px] leading-snug text-[color:var(--text-muted)]"
      >
        {{ item.message }}
      </p>

      <!-- Расширенные детали -->
      <div
        v-if="expanded && details.length > 0"
        class="mt-1.5 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-2"
      >
        <div class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[10px]">
          <template v-for="detail in details" :key="detail.label">
            <span class="whitespace-nowrap text-[color:var(--text-dim)]">{{ detail.label }}:</span>
            <strong
              class="min-w-0 break-words font-mono leading-snug"
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
const details = computed(() => (props.expanded ? buildEventDetails(props.item) : []))
</script>
