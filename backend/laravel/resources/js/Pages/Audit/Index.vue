<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Аудит</h1>
    
    <Card class="mb-4">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <label class="text-sm text-neutral-300">Уровень:</label>
        <select v-model="levelFilter" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
          <option value="">Все уровни</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
          <option value="debug">Debug</option>
        </select>
        <label class="ml-4 text-sm text-neutral-300">Поиск:</label>
        <input 
          v-model="searchQuery" 
          placeholder="Поиск по сообщению..." 
          class="h-9 w-64 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" 
        />
        <div class="ml-auto flex gap-2">
          <Button size="sm" @click="loadLogs" :disabled="loading">
            {{ loading ? 'Загрузка...' : 'Обновить' }}
          </Button>
          <Button size="sm" variant="secondary" @click="exportLogs" :disabled="loading || !filtered.length">
            Экспорт
          </Button>
        </div>
      </div>
      
      <div class="text-xs text-neutral-400 mb-2">
        Всего: {{ all.length }} | Отфильтровано: {{ filtered.length }}
      </div>
    </Card>

    <Card>
      <div v-if="loading && all.length === 0" class="text-sm text-neutral-400 px-3 py-6 text-center">
        Загрузка логов...
      </div>
      <div v-else class="rounded-xl border border-neutral-800 overflow-hidden max-h-[720px] flex flex-col">
        <!-- Заголовок таблицы -->
        <div class="flex-shrink-0 grid grid-cols-4 gap-0 bg-neutral-900 text-neutral-300 text-sm border-b border-neutral-800">
          <div v-for="(h, i) in headers" :key="i" class="px-3 py-2 text-left font-medium">
            {{ h }}
          </div>
        </div>
        <!-- Виртуализированный список -->
        <div class="flex-1 overflow-hidden">
          <RecycleScroller
            :items="paginatedLogs"
            :item-size="rowHeight"
            key-field="id"
            v-slot="{ item: log, index }"
            class="virtual-table-body h-full"
          >
            <div 
              :class="index % 2 === 0 ? 'bg-neutral-950' : 'bg-neutral-925'" 
              class="grid grid-cols-4 gap-0 text-sm border-b border-neutral-900"
              style="height:44px"
            >
              <div class="px-3 py-2 flex items-center">
                <Badge 
                  :variant="getLevelVariant(log.level)"
                >
                  {{ log.level?.toUpperCase() || '-' }}
                </Badge>
              </div>
              <div class="px-3 py-2 flex items-center text-xs text-neutral-400">
                {{ formatDateTime(log.created_at) }}
              </div>
              <div class="px-3 py-2 flex items-center">
                <span class="truncate" :title="log.message">{{ log.message || '-' }}</span>
              </div>
              <div class="px-3 py-2 flex items-center">
                <Button 
                  size="sm" 
                  variant="secondary" 
                  @click="showLogDetails(log)"
                  :disabled="!log.context || Object.keys(log.context).length === 0"
                >
                  Детали
                </Button>
              </div>
            </div>
          </RecycleScroller>
          <div v-if="!paginatedLogs.length" class="text-sm text-neutral-400 px-3 py-6 text-center">
            {{ all.length === 0 ? 'Логи не найдены' : 'Нет логов по текущим фильтрам' }}
          </div>
        </div>
        <Pagination
          v-model:current-page="currentPage"
          v-model:per-page="perPage"
          :total="filtered.length"
        />
      </div>
    </Card>

    <!-- Modal для деталей лога -->
    <Modal :open="selectedLog !== null" :title="`Детали лога #${selectedLog?.id}`" @close="selectedLog = null">
      <div v-if="selectedLog" class="space-y-3">
        <div>
          <label class="text-xs text-neutral-400">Уровень</label>
          <div class="mt-1">
            <Badge :variant="getLevelVariant(selectedLog.level)">
              {{ selectedLog.level?.toUpperCase() || '-' }}
            </Badge>
          </div>
        </div>
        <div>
          <label class="text-xs text-neutral-400">Время</label>
          <div class="mt-1 text-sm text-neutral-200">
            {{ formatDateTime(selectedLog.created_at) }}
          </div>
        </div>
        <div>
          <label class="text-xs text-neutral-400">Сообщение</label>
          <div class="mt-1 text-sm text-neutral-200 bg-neutral-900 p-2 rounded">
            {{ selectedLog.message || '-' }}
          </div>
        </div>
        <div v-if="selectedLog.context && Object.keys(selectedLog.context).length > 0">
          <label class="text-xs text-neutral-400">Контекст</label>
          <div class="mt-1 bg-neutral-900 p-3 rounded overflow-auto max-h-60">
            <pre class="text-xs text-neutral-300">{{ JSON.stringify(selectedLog.context, null, 2) }}</pre>
          </div>
        </div>
        <div v-else class="text-xs text-neutral-500">
          Нет дополнительных данных
        </div>
      </div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="selectedLog = null">Закрыть</Button>
      </template>
    </Modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Modal from '@/Components/Modal.vue'
import Pagination from '@/Components/Pagination.vue'
import { logger } from '@/utils/logger'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

interface SystemLog {
  id: number
  level: string
  message: string
  context?: Record<string, unknown>
  created_at: string
}

interface PageProps {
  logs?: SystemLog[]
}

const page = usePage<PageProps>()
const all = computed(() => (page.props.logs || []) as SystemLog[])
const { showToast } = useToast()

const headers = ['Уровень', 'Время', 'Сообщение', 'Действия']
const levelFilter = ref<string>('')
const searchQuery = ref<string>('')
const currentPage = ref<number>(1)
const perPage = ref<number>(25)
const rowHeight = 44
const loading = ref<boolean>(false)
const selectedLog = ref<SystemLog | null>(null)

const filtered = computed(() => {
  return all.value.filter(log => {
    const levelOk = !levelFilter.value || log.level?.toLowerCase() === levelFilter.value.toLowerCase()
    const searchOk = !searchQuery.value || 
      (log.message?.toLowerCase().includes(searchQuery.value.toLowerCase()) ?? false)
    return levelOk && searchOk
  })
})

const paginatedLogs = computed(() => {
  const total = filtered.value.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return filtered.value.slice(start, end)
})

const getLevelVariant = (level?: string): string => {
  if (!level) return 'neutral'
  const l = level.toLowerCase()
  if (l === 'error') return 'danger'
  if (l === 'warning') return 'warning'
  if (l === 'info') return 'info'
  return 'neutral'
}

const loadLogs = async () => {
  loading.value = true
  try {
    // Используем router.reload с only для обновления только логов без сброса состояния
    // Это лучше, чем полный reload, так как сохраняет фильтры и scroll
    await router.reload({ 
      only: ['logs'], 
      preserveScroll: true,
      preserveState: true 
    })
    // После загрузки проверяем, что текущая страница не выходит за пределы
    const maxPage = Math.ceil(all.value.length / perPage.value) || 1
    if (currentPage.value > maxPage) {
      currentPage.value = maxPage
    }
  } catch (err) {
    logger.error('[Audit/Index] Failed to load logs:', err)
    showToast('Ошибка загрузки логов', 'error', TOAST_TIMEOUT.LONG)
  } finally {
    loading.value = false
  }
}

const formatDateTime = (dateString?: string): string => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const showLogDetails = (log: SystemLog) => {
  selectedLog.value = log
}

const exportLogs = () => {
  if (!filtered.value.length) return
  
  const data = filtered.value.map(log => ({
    level: log.level,
    message: log.message,
    context: log.context,
    created_at: log.created_at,
  }))
  
  const json = JSON.stringify(data, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit-logs-${new Date().toISOString().split('T')[0]}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

onMounted(() => {
  loadLogs()
})

// Сбрасываем на первую страницу при изменении фильтров
watch([levelFilter, searchQuery], () => {
  currentPage.value = 1
})
</script>

