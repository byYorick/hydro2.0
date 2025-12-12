<template>
  <Card class="unassigned-errors-widget">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold">Ошибки неназначенных узлов</h3>
      <Badge :variant="unassignedCount > 0 ? 'danger' : 'success'">
        {{ unassignedCount }}
      </Badge>
    </div>

    <div v-if="loading" class="text-center py-4">
      <LoadingState />
    </div>

    <div v-else-if="error" class="text-red-600 text-sm py-2">
      {{ error }}
    </div>

    <div v-else-if="errors.length === 0" class="text-gray-500 text-sm py-4 text-center">
      Нет ошибок неназначенных узлов
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="err in errors"
        :key="err.id"
        class="border rounded p-3 hover:bg-gray-50 transition-colors"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="flex items-center gap-2 mb-1">
              <span class="font-mono text-sm text-gray-600">{{ err.hardware_id }}</span>
              <Badge :variant="err.error_level === 'ERROR' ? 'danger' : 'warning'" size="sm">
                {{ err.error_level }}
              </Badge>
              <Badge v-if="err.count > 1" variant="info" size="sm">
                ×{{ err.count }}
              </Badge>
            </div>
            <p class="text-sm text-gray-800 mb-1">{{ err.error_message }}</p>
            <div class="flex items-center gap-4 text-xs text-gray-500">
              <span v-if="err.error_code">Код: {{ err.error_code }}</span>
              <span>Последний раз: {{ formatDate(err.last_seen_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="errors.length > 0" class="mt-4 pt-4 border-t">
      <a
        href="/monitoring/unassigned-errors"
        class="text-sm text-blue-600 hover:text-blue-800"
      >
        Показать все ошибки →
      </a>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Card } from '@/Components/Card'
import { Badge } from '@/Components/Badge'
import { LoadingState } from '@/Components/LoadingState'
import axios from 'axios'

interface UnassignedError {
  id: number
  hardware_id: string
  error_message: string
  error_code: string | null
  error_level: string
  topic: string
  count: number
  first_seen_at: string
  last_seen_at: string
  node_id: number | null
}

const errors = ref<UnassignedError[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const unassignedCount = computed(() => {
  return errors.value.filter(e => e.node_id === null).length
})

const formatDate = (dateString: string) => {
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
    
    const response = await axios.get('/api/unassigned-node-errors', {
      params: {
        unassigned_only: true,
        per_page: 5
      }
    })
    
    errors.value = response.data.data || []
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
  const interval = setInterval(fetchErrors, 30000)
  
  // Очищаем интервал при размонтировании
  return () => clearInterval(interval)
})
</script>

<style scoped>
.unassigned-errors-widget {
  min-height: 200px;
}
</style>
