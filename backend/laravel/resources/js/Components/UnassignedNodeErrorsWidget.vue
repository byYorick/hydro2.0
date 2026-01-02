<template>
  <Card class="unassigned-errors-widget">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-[color:var(--text-primary)]">
        {{ zoneId ? 'Ошибки узлов зоны' : 'Ошибки неназначенных узлов' }}
      </h3>
      <Badge :variant="errors.length > 0 ? 'danger' : 'success'">
        {{ errors.length }}
      </Badge>
    </div>

    <div
      v-if="loading"
      class="text-center py-4"
    >
      <LoadingState />
    </div>

    <div
      v-else-if="error"
      class="text-[color:var(--accent-red)] text-sm py-2"
    >
      {{ error }}
    </div>

    <div
      v-else-if="errors.length === 0"
      class="text-[color:var(--text-dim)] text-sm py-4 text-center"
    >
      Нет ошибок {{ zoneId ? 'узлов зоны' : 'неназначенных узлов' }}
    </div>

    <div
      v-else
      class="space-y-2 max-h-[400px] overflow-y-auto"
    >
      <div
        v-for="err in errors"
        :key="err.id"
        class="border border-[color:var(--border-muted)] rounded-lg p-3 hover:bg-[color:var(--bg-elevated)] transition-colors"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="flex items-center gap-2 mb-1 flex-wrap">
              <span class="font-mono text-sm text-[color:var(--text-muted)]">{{ err.hardware_id }}</span>
              <Badge 
                :variant="getSeverityVariant(err.severity)" 
                size="sm"
              >
                {{ err.severity }}
              </Badge>
              <Badge
                v-if="err.count > 1"
                variant="info"
                size="sm"
              >
                ×{{ err.count }}
              </Badge>
            </div>
            <p class="text-sm text-[color:var(--text-primary)] mb-1">
              {{ err.error_message }}
            </p>
            <div class="flex items-center gap-4 text-xs text-[color:var(--text-dim)] flex-wrap">
              <span v-if="err.error_code">Код: {{ err.error_code }}</span>
              <span>Последний раз: {{ formatDate(err.last_seen_at) }}</span>
              <span v-if="err.first_seen_at !== err.last_seen_at">
                Первый раз: {{ formatDate(err.first_seen_at) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="errors.length > 0 && !zoneId"
      class="mt-4 pt-4 border-t border-[color:var(--border-muted)]"
    >
      <a
        href="/monitoring/unassigned-errors"
        class="text-sm text-[color:var(--accent-cyan)] hover:text-[color:var(--accent-green)] transition-colors"
      >
        Показать все ошибки →
      </a>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import LoadingState from '@/Components/LoadingState.vue'
import { useApi } from '@/composables/useApi'

interface UnassignedError {
  id: number
  hardware_id: string
  error_message: string
  error_code: string | null
  severity?: string
  topic: string
  last_payload: any
  count: number
  first_seen_at: string
  last_seen_at: string
  node_id: number | null
}

interface Props {
  zoneId?: number
  limit?: number
}

const props = withDefaults(defineProps<Props>(), {
  zoneId: undefined,
  limit: 10
})

const errors = ref<UnassignedError[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
let refreshInterval: ReturnType<typeof setInterval> | null = null

const { api } = useApi()

const getSeverityVariant = (severity: string | undefined): 'danger' | 'warning' | 'info' => {
  const upper = (severity || 'ERROR').toUpperCase()
  if (upper === 'CRITICAL' || upper === 'ERROR') return 'danger'
  if (upper === 'WARNING') return 'warning'
  return 'info'
}

const formatDate = (dateString: string) => {
  if (!dateString) return 'неизвестно'
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  
  if (diffMins < 1) return 'только что'
  if (diffMins < 60) return `${diffMins} мин назад`
  
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours} ч назад`
  
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays} дн назад`
}

const fetchErrors = async () => {
  try {
    loading.value = true
    error.value = null
    
    if (props.zoneId) {
      // Загружаем ошибки для конкретной зоны
      const response = await api.get<{ data: UnassignedError[], meta: any }>(`/api/zones/${props.zoneId}/unassigned-errors`, {
        params: {
          per_page: props.limit
        }
      })
      errors.value = response.data?.data || []
    } else {
      // Загружаем все неназначенные ошибки
      const response = await api.get<{ data: UnassignedError[], meta: any }>('/api/unassigned-node-errors', {
        params: {
          unassigned_only: true,
          per_page: props.limit
        }
      })
      errors.value = response.data?.data || []
    }
  } catch (err: any) {
    error.value = err.response?.data?.message || 'Ошибка загрузки данных'
    console.error('Failed to fetch unassigned node errors:', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchErrors()
  
  // Обновляем каждые 30 секунд
  refreshInterval = setInterval(fetchErrors, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.unassigned-errors-widget {
  min-height: 200px;
}
</style>
