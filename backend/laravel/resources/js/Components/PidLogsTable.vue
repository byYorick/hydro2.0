<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">Логи PID</div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-sky-600 text-white': filterType === 'ph' }"
            @click="filterType = 'ph'"
          >
            pH
          </Button>
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-sky-600 text-white': filterType === 'ec' }"
            @click="filterType = 'ec'"
          >
            EC
          </Button>
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-sky-600 text-white': filterType === null }"
            @click="filterType = null"
          >
            Все
          </Button>
        </div>
      </div>

      <div v-if="loading" class="text-sm text-neutral-400 text-center py-4">
        Загрузка...
      </div>

      <div v-else-if="logs.length === 0" class="text-sm text-neutral-400 text-center py-4">
        Нет логов
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-neutral-800">
              <th class="text-left py-2 px-3 text-xs font-medium text-neutral-400">Время</th>
              <th class="text-left py-2 px-3 text-xs font-medium text-neutral-400">Тип</th>
              <th class="text-left py-2 px-3 text-xs font-medium text-neutral-400">Зона</th>
              <th class="text-left py-2 px-3 text-xs font-medium text-neutral-400">Output</th>
              <th class="text-left py-2 px-3 text-xs font-medium text-neutral-400">Error</th>
              <th class="text-left py-2 px-3 text-xs font-medium text-neutral-400">Current</th>
              <th class="text-left py-2 px-3 text-xs font-medium text-neutral-400">Target</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="log in logs"
              :key="log.id"
              class="border-b border-neutral-800 hover:bg-neutral-900/50"
            >
              <td class="py-2 px-3 text-neutral-300">
                {{ new Date(log.created_at).toLocaleString('ru-RU') }}
              </td>
              <td class="py-2 px-3">
                <Badge
                  :variant="
                    log.type === 'config_updated'
                      ? 'info'
                      : log.zone_state === 'far'
                        ? 'warning'
                        : 'neutral'
                  "
                  class="text-xs"
                >
                  {{ log.type === 'config_updated' ? 'Config' : log.type.toUpperCase() }}
                </Badge>
              </td>
              <td class="py-2 px-3 text-neutral-300">
                <span v-if="log.zone_state" class="text-xs">
                  {{ log.zone_state }}
                </span>
                <span v-else class="text-xs text-neutral-500">-</span>
              </td>
              <td class="py-2 px-3 text-neutral-300">
                <span v-if="log.output !== undefined">{{ log.output.toFixed(2) }}</span>
                <span v-else class="text-neutral-500">-</span>
              </td>
              <td class="py-2 px-3 text-neutral-300">
                <span v-if="log.error !== undefined" :class="getErrorClass(log.error)">
                  {{ log.error.toFixed(3) }}
                </span>
                <span v-else class="text-neutral-500">-</span>
              </td>
              <td class="py-2 px-3 text-neutral-300">
                <span v-if="log.current !== undefined">{{ log.current.toFixed(2) }}</span>
                <span v-else class="text-neutral-500">-</span>
              </td>
              <td class="py-2 px-3 text-neutral-300">
                <span v-if="log.target !== undefined">{{ log.target.toFixed(2) }}</span>
                <span v-else class="text-neutral-500">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Пагинация -->
      <div v-if="total > limit" class="flex items-center justify-between pt-4 border-t border-neutral-800">
        <div class="text-xs text-neutral-400">
          Показано {{ logs.length }} из {{ total }}
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            :disabled="offset === 0"
            @click="loadLogs(offset - limit)"
          >
            Назад
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="offset + limit >= total"
            @click="loadLogs(offset + limit)"
          >
            Вперед
          </Button>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { usePidConfig } from '@/composables/usePidConfig'
import Card from './Card.vue'
import Button from './Button.vue'
import Badge from './Badge.vue'
import type { PidLog } from '@/types/PidConfig'

interface Props {
  zoneId: number
}

const props = defineProps<Props>()

const filterType = ref<'ph' | 'ec' | null>(null)
const logs = ref<PidLog[]>([])
const total = ref(0)
const limit = ref(50)
const offset = ref(0)
const loading = ref(false)

const { getPidLogs } = usePidConfig()

let pollInterval: ReturnType<typeof setInterval> | null = null

function getErrorClass(error: number): string {
  const absError = Math.abs(error)
  if (absError > 1.0) return 'text-red-400'
  if (absError > 0.5) return 'text-amber-400'
  return 'text-neutral-300'
}

async function loadLogs(newOffset: number = 0) {
  loading.value = true
  offset.value = newOffset

  try {
    const result = await getPidLogs(props.zoneId, {
      type: filterType.value || undefined,
      limit: limit.value,
      offset: offset.value,
    })
    logs.value = result.logs
    total.value = result.total
  } catch (error) {
    console.error('Failed to load PID logs:', error)
  } finally {
    loading.value = false
  }
}

function startPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
  }
  pollInterval = setInterval(() => {
    loadLogs(offset.value)
  }, 5000) // Обновление каждые 5 секунд
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

watch(filterType, () => {
  loadLogs(0)
})

onMounted(() => {
  loadLogs()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

