<template>
  <Card>
    <div class="space-y-2">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">
          События цикла
        </div>
        <Button
          size="sm"
          variant="outline"
          :disabled="loading"
          @click="loadEvents"
        >
          <LoadingState
            v-if="loading"
            loading
            size="sm"
            :container-class="'inline-flex mr-2'"
          />
          Обновить
        </Button>
      </div>

      <!-- Кнопка "Загрузить ещё" сверху (старые события) -->
      <div
        v-if="paginated && hasMore && events.length > 0"
        class="text-center"
      >
        <button
          type="button"
          :disabled="loadingMore"
          class="text-xs text-[color:var(--accent-cyan)] hover:underline disabled:opacity-50"
          @click="loadMore"
        >
          {{ loadingMore ? 'Загрузка...' : 'Загрузить ещё' }}
        </button>
      </div>

      <div
        v-if="events.length > 0"
        class="space-y-1 max-h-[400px] overflow-y-auto"
        data-testid="cycle-events-section"
      >
        <div
          v-for="event in events"
          :key="event.id"
          :data-testid="`cycle-event-item-${event.id}`"
          class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-2 px-2 rounded border border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)] transition-colors"
        >
          <Badge
            :variant="getEventVariant(event.type)"
            class="text-xs shrink-0"
          >
            {{ getEventTypeLabel(event.type) }}
          </Badge>
          <div class="flex-1 min-w-0">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              {{ formatDateTime(event.created_at) }}
            </div>
            <div class="text-sm">
              {{ getEventMessage(event) }}
            </div>
          </div>
        </div>
      </div>

      <div
        v-else
        class="text-sm text-[color:var(--text-dim)] text-center py-4"
      >
        Нет событий цикла
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import LoadingState from '@/Components/LoadingState.vue'
import {
  useCycleEvents,
  getEventVariant,
  getEventTypeLabel,
  getEventMessage,
} from '@/composables/useCycleEvents'

interface Props {
  zoneId: number | null | undefined
  phaseId?: number | null
  limit?: number
  paginated?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  phaseId: undefined,
  limit: 50,
  paginated: false,
})

function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  try {
    return new Date(dateStr).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

const { events, loading, loadingMore, hasMore, loadEvents, loadMore } = useCycleEvents(
  () => props.zoneId,
  () => props.phaseId,
  { limit: props.limit },
)
</script>
