<template>
  <AppLayout>
    <div class="space-y-4">
      <header class="ui-hero p-5 space-y-4">
        <div>
          <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
            observability
          </p>
          <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)] mt-1">
            Журнал сервисов
          </h1>
          <p class="text-sm text-[color:var(--text-muted)] max-w-3xl">
            Отслеживайте события автоматизации, MQTT Bridge и cron в одном окне.
          </p>
        </div>
        <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-4">
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Всего записей
            </div>
            <div class="ui-kpi-value">
              {{ totalCount }}
            </div>
            <div class="ui-kpi-hint">
              Для выбранного набора фильтров
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Ошибки
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-red)]">
              {{ errorLogsCount }}
            </div>
            <div class="ui-kpi-hint">
              На текущей странице
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Предупреждения
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-amber)]">
              {{ warningLogsCount }}
            </div>
            <div class="ui-kpi-hint">
              Требуют внимания
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Сервис
            </div>
            <div class="ui-kpi-value text-base md:text-lg leading-tight">
              {{ activeServiceLabel }}
            </div>
            <div class="ui-kpi-hint">
              Активный контур мониторинга
            </div>
          </div>
        </div>
      </header>

      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-3">
        <Tabs
          v-model="activeServiceTab"
          data-testid="logs-service-tabs"
          :tabs="serviceTabs"
          aria-label="Сервисы"
        />
      </div>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Фильтр</span>
            <select
              v-model="filters.level"
              class="input-select h-9"
              data-testid="logs-filter-level"
            >
              <option value="">
                Все уровни
              </option>
              <option
                v-for="level in levelOptions"
                :key="level"
                :value="level"
              >
                {{ level }}
              </option>
            </select>
            <input
              v-model="filters.search"
              type="search"
              placeholder="Поиск по сообщению/контексту"
              class="input-field h-9 w-full sm:w-64"
            />
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <input
              v-model="filters.from"
              type="date"
              class="input-field h-9"
            />
            <input
              v-model="filters.to"
              type="date"
              class="input-field h-9"
            />
            <Button
              size="sm"
              variant="outline"
              :disabled="loading"
              @click="refresh"
            >
              Обновить
            </Button>
          </div>
        </div>
      </section>

      <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              {{ activeServiceLabel }}
            </div>
            <p class="text-xs text-[color:var(--text-dim)]">
              {{ activeServiceDescription }}
            </p>
          </div>
          <span class="text-xs text-[color:var(--text-dim)]">
            {{ totalCount }} записей
          </span>
        </div>

        <div
          v-if="error"
          class="text-sm text-[color:var(--accent-red)]"
        >
          {{ error }}
        </div>

        <div
          v-else-if="loading"
          class="text-sm text-[color:var(--text-dim)] text-center py-8"
        >
          Загрузка логов...
        </div>

        <div
          v-else-if="!hasLogs"
          class="text-sm text-[color:var(--text-dim)] text-center py-8"
        >
          Нет логов по выбранным фильтрам
        </div>

        <div
          v-else
          class="space-y-1 max-h-[560px] overflow-y-auto pr-1"
        >
          <div
            v-for="entry in logs"
            :key="entry.id"
            class="text-sm text-[color:var(--text-muted)] flex items-start gap-3 py-3 border-b border-[color:var(--border-muted)]"
            data-testid="service-log-entry"
          >
            <Badge
              :variant="levelVariant(entry.level)"
              size="xs"
              class="shrink-0"
            >
              {{ entry.level }}
            </Badge>
            <div class="flex-1 min-w-0 space-y-1">
              <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-dim)]">
                <span>{{ formatTime(entry.created_at) }}</span>
                <Badge
                  v-if="showServiceBadge"
                  size="xs"
                  variant="secondary"
                  class="uppercase tracking-[0.08em]"
                  data-testid="service-log-service"
                >
                  {{ serviceLabelFor(entry.service) }}
                </Badge>
              </div>
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                {{ entry.message }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)]">
                {{ summarizeContext(entry.context) }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div
        v-if="meta.total > 0"
        class="flex items-center justify-between pt-2 border-t border-[color:var(--border-muted)]"
      >
        <div class="text-xs text-[color:var(--text-dim)]">
          Страница {{ meta.page }} / {{ meta.last_page }} • {{ meta.total }} записей
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            :disabled="meta.page <= 1 || loading"
            @click="changePage(meta.page - 1)"
          >
            Назад
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="meta.page >= meta.last_page || loading"
            @click="changePage(meta.page + 1)"
          >
            Вперед
          </Button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Tabs from '@/Components/Tabs.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import { formatTime } from '@/utils/formatTime'
import { useApi } from '@/composables/useApi'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'

interface ServiceOption {
  key: string
  label: string
  description?: string
}

interface ServiceLog {
  id: number
  service: string
  level: string
  message: string
  context?: Record<string, any> | null
  created_at: string
}

interface ServiceLogMeta {
  page: number
  per_page: number
  total: number
  last_page: number
}

interface Props {
  serviceOptions: ServiceOption[]
  defaultService?: string
  defaultLevel?: string
  defaultSearch?: string
}

const props = defineProps<Props>()

const { get } = useApi()

const excludedServiceKeys = new Set(['history-logger', 'history-locker'])
const defaultService = props.defaultService && !excludedServiceKeys.has(props.defaultService)
  ? props.defaultService
  : 'all'

const filters = reactive({
  service: defaultService,
  level: props.defaultLevel || '',
  search: props.defaultSearch || '',
  from: '',
  to: '',
})

const activeServiceTab = ref(filters.service)

const levelOptions = ['ERROR', 'WARNING', 'INFO', 'DEBUG']
const logs = ref<ServiceLog[]>([])
const meta = reactive<ServiceLogMeta>({
  page: 1,
  per_page: 50,
  total: 0,
  last_page: 1,
})
const loading = ref(false)
const error = ref('')

const POLL_INTERVAL_MS = 15000
const POLL_KEY = '__logsPollInterval__'
const SEARCH_KEY = '__logsSearchDebounce__'

let pollInterval: ReturnType<typeof setInterval> | null = null
let searchDebounce: ReturnType<typeof setTimeout> | null = null

const dynamicServices = computed<ServiceOption[]>(() => {
  const known = new Set(props.serviceOptions.map((s) => s.key))
  const dynamic = Array.from(new Set(logs.value.map((l) => l.service))).filter((key) =>
    !known.has(key) && !excludedServiceKeys.has(key)
  )
  return dynamic.map((key) => ({
    key,
    label: key,
    description: 'Логи сервиса',
  }))
})

const serviceSelectOptions = computed<ServiceOption[]>(() =>
  [...props.serviceOptions, ...dynamicServices.value]
    .filter((item) => !excludedServiceKeys.has(item.key))
    .filter((item, index, arr) => arr.findIndex((i) => i.key === item.key) === index)
)

const serviceTabs = computed(() => {
  const tabs = [
    { id: 'all', label: 'Все сервисы' },
    ...serviceSelectOptions.value.map((service) => ({
      id: service.key,
      label: service.label,
    })),
  ]

  return tabs.filter((tab, index, arr) => arr.findIndex((item) => item.id === tab.id) === index)
})

const activeServiceOption = computed(() =>
  serviceSelectOptions.value.find((service) => service.key === filters.service)
)

const activeServiceLabel = computed(() => {
  if (filters.service === 'all') return 'Все сервисы'
  return activeServiceOption.value?.label ?? filters.service
})

const activeServiceDescription = computed(() => {
  if (filters.service === 'all') {
    return 'Сводка по сервисам и системе в реальном времени.'
  }
  return activeServiceOption.value?.description ?? 'Логи сервиса'
})

const showServiceBadge = computed(() => filters.service === 'all')

const serviceLabelFor = (serviceKey: string) =>
  serviceSelectOptions.value.find((service) => service.key === serviceKey)?.label ?? serviceKey

const hasLogs = computed(() => logs.value.length > 0)
const totalCount = computed(() => meta.total || logs.value.length)
const errorLogsCount = computed(() =>
  logs.value.filter((entry) => entry.level?.toLowerCase().includes('error') || entry.level?.toLowerCase().includes('critical')).length
)
const warningLogsCount = computed(() =>
  logs.value.filter((entry) => entry.level?.toLowerCase().includes('warn')).length
)

const levelVariant = (level: string) => {
  const normalized = level?.toLowerCase()
  if (normalized.includes('error') || normalized.includes('critical')) {
    return 'danger'
  }
  if (normalized.includes('warn')) {
    return 'warning'
  }
  if (normalized.includes('debug') || normalized.includes('trace')) {
    return 'info'
  }
  return 'neutral'
}

const summarizeContext = (context?: Record<string, any> | null) => {
  if (!context) return 'Дополнительных метаданных нет'
  if (context['zone_id']) {
    return `Зона #${context['zone_id']}`
  }
  if (context['node_id']) {
    return `Нода #${context['node_id']}`
  }
  if (context['task_name']) {
    return `Задача: ${context['task_name']}`
  }
  if (context['service']) {
    return `Сервис: ${context['service']}`
  }
  return Object.entries(context)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(', ')
}

async function fetchLogs(page = 1) {
  loading.value = true
  error.value = ''
  meta.page = page

  try {
    const params: Record<string, any> = {
      page,
      per_page: meta.per_page,
      exclude_services: Array.from(excludedServiceKeys),
    }

    if (filters.service && filters.service !== 'all') params.service = filters.service
    if (filters.level) params.level = filters.level
    if (filters.search.trim()) params.search = filters.search.trim()
    if (filters.from) params.from = filters.from
    if (filters.to) params.to = filters.to

    const response = await get('/logs/service', { params })
    const parsed = normalizeLogsResponse(response)
    logs.value = parsed.logs
    updateMeta(parsed.meta, logs.value.length)
  } catch (err) {
    logger.error('Failed to load service logs', { err })
    error.value = 'Не удалось загрузить логи. Попробуйте обновить страницу.'
  } finally {
    loading.value = false
  }
}

/**
 * Нормализует ответ API для логов (учитываем разные формы: {status, data, meta} | {data:{data,meta}} | массив)
 */
function normalizeLogsResponse(response: any): { logs: ServiceLog[]; meta?: Partial<ServiceLogMeta> | null } {
  const payload = response?.data ?? response
  const directData = extractData<ServiceLog[] | Record<string, any>>(payload)

  // Вариант: extractData вернул массив
  if (Array.isArray(directData)) {
    return { logs: directData, meta: (payload as any)?.meta ?? null }
  }

  // Вариант: объект с data/meta на первом или втором уровне
  const inner = directData ?? payload ?? {}
  const firstLevelData = Array.isArray(inner?.data) ? inner.data : null
  const secondLevelData = Array.isArray(inner?.data?.data) ? inner.data.data : null

  const logsData = firstLevelData || secondLevelData || []
  const metaFromPayload = inner?.meta ?? inner?.data?.meta ?? (payload as any)?.meta ?? null

  return {
    logs: Array.isArray(logsData) ? logsData : [],
    meta: metaFromPayload,
  }
}

function updateMeta(metaPayload?: Partial<ServiceLogMeta> | null, fallbackTotal = 0) {
  const pageValue = (metaPayload as any)?.page ?? (metaPayload as any)?.current_page
  const perPageValue = (metaPayload as any)?.per_page ?? (metaPayload as any)?.perPage
  const totalValue = (metaPayload as any)?.total ?? (metaPayload as any)?.total_count
  const lastPageValue = (metaPayload as any)?.last_page ?? (metaPayload as any)?.lastPage ?? (metaPayload as any)?.total_pages

  meta.page = pageValue ?? meta.page
  meta.per_page = perPageValue ?? meta.per_page
  meta.total = totalValue ?? fallbackTotal ?? meta.total
  meta.last_page = lastPageValue ?? meta.last_page
}

function changePage(newPage: number) {
  if (newPage < 1 || newPage > meta.last_page) return
  fetchLogs(newPage)
}

function refresh() {
  fetchLogs(meta.page)
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval)

  if (typeof window !== 'undefined') {
    const existing = (window as any)[POLL_KEY] as ReturnType<typeof setInterval> | null
    if (existing) clearInterval(existing)
  }

  pollInterval = setInterval(() => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    fetchLogs(meta.page)
  }, POLL_INTERVAL_MS)

  if (typeof window !== 'undefined') {
    const win = window as any
    win[POLL_KEY] = pollInterval
  }
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }

  if (typeof window !== 'undefined') {
    const win = window as any
    const existing = win[POLL_KEY] as ReturnType<typeof setInterval> | null
    if (existing) {
      clearInterval(existing)
      win[POLL_KEY] = null
    }
  }
}

watch(
  () => [filters.service, filters.level, filters.from, filters.to],
  () => fetchLogs(1)
)

watch(
  () => filters.service,
  (value) => {
    if (activeServiceTab.value !== value) {
      activeServiceTab.value = value
    }
  }
)

watch(
  activeServiceTab,
  (value) => {
    if (filters.service !== value) {
      filters.service = value
    }
  }
)

watch(
  () => filters.search,
  () => {
    if (searchDebounce) clearTimeout(searchDebounce)

    if (typeof window !== 'undefined') {
      const existing = (window as any)[SEARCH_KEY] as ReturnType<typeof setTimeout> | null
      if (existing) clearTimeout(existing)
    }

    searchDebounce = setTimeout(() => fetchLogs(1), 400)

    if (typeof window !== 'undefined') {
      const win = window as any
      win[SEARCH_KEY] = searchDebounce
    }
  }
)

onMounted(async () => {
  await fetchLogs()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  if (searchDebounce) {
    clearTimeout(searchDebounce)
    searchDebounce = null
  }
  if (typeof window !== 'undefined') {
    const win = window as any
    const existing = win[SEARCH_KEY] as ReturnType<typeof setTimeout> | null
    if (existing) {
      clearTimeout(existing)
      win[SEARCH_KEY] = null
    }
  }
})
</script>

<style scoped>
select option {
  background-color: var(--bg-surface-strong);
  color: var(--text-primary);
}
</style>
