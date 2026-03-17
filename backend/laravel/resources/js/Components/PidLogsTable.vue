<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">
          Логи PID
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': filterType === 'ph' }"
            @click="filterType = 'ph'"
          >
            pH
          </Button>
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': filterType === 'ec' }"
            @click="filterType = 'ec'"
          >
            EC
          </Button>
          <Button
            size="sm"
            variant="outline"
            :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': filterType === null }"
            @click="filterType = null"
          >
            Все
          </Button>
        </div>
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-muted)] text-center py-4"
      >
        Загрузка...
      </div>

      <div
        v-else-if="logs.length === 0"
        class="text-sm text-[color:var(--text-muted)] text-center py-4"
      >
        Нет логов
      </div>

      <div
        v-else
        class="overflow-x-auto"
      >
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-[color:var(--border-muted)]">
              <th class="text-left py-2 px-3 text-xs font-medium text-[color:var(--text-muted)]">
                Время
              </th>
              <th class="text-left py-2 px-3 text-xs font-medium text-[color:var(--text-muted)]">
                Тип
              </th>
              <th class="text-left py-2 px-3 text-xs font-medium text-[color:var(--text-muted)]">
                Зона
              </th>
              <th class="text-left py-2 px-3 text-xs font-medium text-[color:var(--text-muted)]">
                Output
              </th>
              <th class="text-left py-2 px-3 text-xs font-medium text-[color:var(--text-muted)]">
                Error
              </th>
              <th class="text-left py-2 px-3 text-xs font-medium text-[color:var(--text-muted)]">
                Current
              </th>
              <th class="text-left py-2 px-3 text-xs font-medium text-[color:var(--text-muted)]">
                Target
              </th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="log in logs"
              :key="log.id"
            >
              <tr class="border-b border-[color:var(--border-muted)] hover:bg-[color:var(--bg-elevated)]">
                <td class="py-2 px-3 text-[color:var(--text-primary)]">
                  {{ new Date(log.created_at).toLocaleString('ru-RU') }}
                </td>
                <td class="py-2 px-3">
                  <Badge
                    :variant="badgeVariant(log)"
                    class="text-xs"
                  >
                    {{ badgeLabel(log) }}
                  </Badge>
                </td>
                <td class="py-2 px-3 text-[color:var(--text-primary)]">
                  <span class="text-xs">
                    {{ contextLabel(log) }}
                  </span>
                </td>
                <td class="py-2 px-3 text-[color:var(--text-primary)]">
                  <span v-if="typeof log.output === 'number'">{{ log.output.toFixed(2) }}</span>
                  <span
                    v-else
                    class="text-[color:var(--text-dim)]"
                  >-</span>
                </td>
                <td class="py-2 px-3 text-[color:var(--text-primary)]">
                  <span
                    v-if="typeof log.error === 'number'"
                    :class="getErrorClass(log.error)"
                  >
                    {{ log.error.toFixed(3) }}
                  </span>
                  <span
                    v-else
                    class="text-[color:var(--text-dim)]"
                  >-</span>
                </td>
                <td class="py-2 px-3 text-[color:var(--text-primary)]">
                  <span v-if="typeof log.current === 'number'">{{ log.current.toFixed(2) }}</span>
                  <span
                    v-else
                    class="text-[color:var(--text-dim)]"
                  >-</span>
                </td>
                <td class="py-2 px-3 text-[color:var(--text-primary)]">
                  <span v-if="typeof log.target === 'number'">{{ log.target.toFixed(2) }}</span>
                  <span
                    v-else-if="typeof log.new_config?.target === 'number'"
                  >
                    {{ log.new_config.target.toFixed(2) }}
                  </span>
                  <span
                    v-else
                    class="text-[color:var(--text-dim)]"
                  >-</span>
                </td>
              </tr>
              <tr
                v-if="isConfigUpdated(log)"
                class="border-b border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
              >
                <td class="py-2 px-3"></td>
                <td
                  colspan="6"
                  class="py-2 px-3 text-xs text-[color:var(--text-dim)]"
                >
                  {{ configSummary(log) }}
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Пагинация -->
      <div
        v-if="total > limit"
        class="flex items-center justify-between pt-4 border-t border-[color:var(--border-muted)]"
      >
        <div class="text-xs text-[color:var(--text-muted)]">
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
import { logger } from '@/utils/logger'

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
  if (absError > 1.0) return 'text-[color:var(--accent-red)]'
  if (absError > 0.5) return 'text-[color:var(--accent-amber)]'
  return 'text-[color:var(--text-primary)]'
}

function isConfigUpdated(log: PidLog): boolean {
  return log.type === 'config_updated'
}

function badgeVariant(log: PidLog): 'info' | 'warning' | 'neutral' {
  if (isConfigUpdated(log)) {
    return 'info'
  }

  return log.zone_state === 'far' ? 'warning' : 'neutral'
}

function badgeLabel(log: PidLog): string {
  if (isConfigUpdated(log)) {
    return `Config ${String(log.pid_type || '').toUpperCase() || 'PID'}`
  }

  return String(log.type || 'PID').toUpperCase()
}

function contextLabel(log: PidLog): string {
  if (isConfigUpdated(log)) {
    if (log.updated_by) {
      return `updated_by #${log.updated_by}`
    }

    return `PID ${String(log.pid_type || '').toUpperCase() || 'unknown'}`
  }

  return log.zone_state || '-'
}

function configSummary(log: PidLog): string {
  if (!isConfigUpdated(log)) {
    return ''
  }

  const parts: string[] = []
  if (typeof log.old_config?.target === 'number' && typeof log.new_config?.target === 'number') {
    parts.push(`target ${log.old_config.target.toFixed(2)} → ${log.new_config.target.toFixed(2)}`)
  } else if (typeof log.new_config?.target === 'number') {
    parts.push(`target ${log.new_config.target.toFixed(2)}`)
  }

  if (typeof log.new_config?.max_output === 'number') {
    parts.push(`max dose ${log.new_config.max_output.toFixed(1)} мл`)
  }

  if (typeof log.new_config?.min_interval_ms === 'number') {
    parts.push(`interval ${(log.new_config.min_interval_ms / 1000).toFixed(0)} сек`)
  }

  if (typeof log.new_config?.max_integral === 'number') {
    parts.push(`max integral ${log.new_config.max_integral.toFixed(1)}`)
  }

  return parts.length > 0 ? parts.join(' · ') : 'Параметры конфига обновлены.'
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
    logger.error('Failed to load PID logs:', { error })
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
