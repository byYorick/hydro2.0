<template>
  <AppLayout>
    <div class="flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <h1 class="text-lg font-semibold">Добавление новой ноды</h1>
        <Button size="sm" variant="secondary" @click="refreshNodes">
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Обновить список
        </Button>
      </div>

      <!-- Инструкция -->
      <Card>
        <div class="text-sm font-semibold mb-2">Инструкция по добавлению ноды</div>
        <ol class="text-xs text-[color:var(--text-muted)] space-y-1 list-decimal list-inside">
          <li>Включите новую ноду. Она поднимет точку доступа Wi-Fi.</li>
          <li>Подключитесь с телефона к точке доступа ноды.</li>
          <li>Откройте в браузере <code class="text-[color:var(--accent-cyan)]">192.168.4.1</code></li>
          <li>Введите SSID и пароль вашей Wi-Fi сети.</li>
          <li>Нода перезагрузится и отправит discovery сообщение.</li>
          <li>Нажмите "Обновить список" или нода появится автоматически.</li>
          <li>Привяжите ноду к зоне через форму ниже.</li>
        </ol>
      </Card>

      <!-- Список новых нод -->
      <Card>
        <div class="text-sm font-semibold mb-3">Новые ноды (без привязки к зоне)</div>
        <div v-if="loading" class="text-sm text-[color:var(--text-dim)] py-4 text-center">
          Загрузка...
        </div>
        <div v-else-if="newNodes.length === 0" class="text-sm text-[color:var(--text-dim)] py-4 text-center">
          Новых нод не найдено. Убедитесь, что нода подключена к Wi-Fi и отправила discovery сообщение.
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="node in newNodes"
            :key="node.id"
            class="p-3 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
              <div class="flex items-start justify-between mb-2">
              <div>
                <div class="text-sm font-semibold">{{ node.name || node.uid || `Node #${node.id}` }}</div>
                <div class="text-xs text-[color:var(--text-muted)] mt-1">
                  <span v-if="node.uid">UID: {{ node.uid }}</span>
                  <span v-if="node.type" class="ml-2">Тип: {{ node.type }}</span>
                  <span v-if="node.fw_version" class="ml-2">FW: {{ node.fw_version }}</span>
                </div>
                <div class="text-xs text-[color:var(--text-dim)] mt-1">
                  <span v-if="node.last_seen_at">
                    Последний раз видели: {{ formatDate(node.last_seen_at) }}
                  </span>
                  <span v-else>Никогда не видели</span>
                  <span v-if="node.lifecycle_state" class="ml-2">
                    · Lifecycle: <span class="text-[color:var(--accent-cyan)]">{{ getStateLabel(node.lifecycle_state) }}</span>
                  </span>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <Badge :variant="getStatusVariant(node.status)">
                  {{ node.status || 'unknown' }}
                </Badge>
                <Badge 
                  v-if="node.lifecycle_state" 
                  :variant="getLifecycleVariant(node.lifecycle_state)"
                >
                  {{ getStateLabel(node.lifecycle_state) }}
                </Badge>
              </div>
            </div>

            <!-- Форма привязки к зоне -->
            <div class="mt-3 pt-3 border-t border-[color:var(--border-muted)]">
              <div class="text-xs font-semibold mb-2 text-[color:var(--text-muted)]">Привязать к зоне:</div>
              <form @submit.prevent="assignNode(node)" class="grid grid-cols-1 md:grid-cols-4 gap-2">
                <label :for="`node-${node.id}-greenhouse`" class="sr-only">Теплица</label>
                <select
                  :id="`node-${node.id}-greenhouse`"
                  :name="`node_${node.id}_greenhouse_id`"
                  v-model="assignmentForms[node.id].greenhouse_id"
                  @change="onGreenhouseChange(node.id)"
                  class="input-select"
                  required
                >
                  <option :value="null">Выберите теплицу</option>
                  <option v-for="gh in greenhouses" :key="gh.id" :value="gh.id">
                    {{ gh.name }}
                  </option>
                </select>
                <label :for="`node-${node.id}-zone`" class="sr-only">Зона</label>
                <select
                  :id="`node-${node.id}-zone`"
                  :name="`node_${node.id}_zone_id`"
                  v-model="assignmentForms[node.id].zone_id"
                  class="input-select"
                  :disabled="!assignmentForms[node.id].greenhouse_id"
                  required
                >
                  <option :value="null">Выберите зону</option>
                  <option v-for="zone in getZonesForGreenhouse(assignmentForms[node.id].greenhouse_id)" :key="zone.id" :value="zone.id">
                    {{ zone.name }}
                  </option>
                </select>
                <label :for="`node-${node.id}-name`" class="sr-only">Имя ноды</label>
                <input
                  :id="`node-${node.id}-name`"
                  :name="`node_${node.id}_name`"
                  v-model="assignmentForms[node.id].name"
                  placeholder="Имя ноды (опционально)"
                  class="input-field"
                />
                <Button
                  type="submit"
                  size="sm"
                  :disabled="assigning[node.id] || !assignmentForms[node.id].zone_id"
                >
                  <span v-if="assigning[node.id]">Привязка...</span>
                  <span v-else>Привязать</span>
                </Button>
              </form>
            </div>
          </div>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { logger } from '@/utils/logger'
import { useNodeLifecycle } from '@/composables/useNodeLifecycle'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useToast } from '@/composables/useToast'
import { useApi } from '@/composables/useApi'
import { useLoading } from '@/composables/useLoading'
import { extractData } from '@/utils/apiHelpers'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { Device, Greenhouse, Zone } from '@/types'

const { showToast } = useToast()
const { api } = useApi(showToast)
const { loading, startLoading, stopLoading } = useLoading<boolean>(false)

// Инициализация composables для lifecycle
const { canAssignToZone, getStateLabel } = useNodeLifecycle(showToast)
const { handleError } = useErrorHandler(showToast)

const newNodes = ref<Device[]>([])
const greenhouses = ref<Greenhouse[]>([])
const zones = ref<Zone[]>([])
const assigning = reactive<Record<number, boolean>>({})
const assignmentForms = reactive<Record<number, { greenhouse_id: number | null; zone_id: number | null; name: string }>>({})
const pendingAssignments = reactive<Record<number, string>>({})
let refreshInterval: ReturnType<typeof setInterval> | null = null

function formatDate(dateString) {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('ru-RU')
}

function getStatusVariant(status) {
  switch (status) {
    case 'online': return 'success'
    case 'offline': return 'neutral'
    case 'degraded': return 'warning'
    case 'maintenance': return 'info'
    default: return 'neutral'
  }
}

function getLifecycleVariant(lifecycleState) {
  switch (lifecycleState) {
    case 'ACTIVE': return 'success'
    case 'REGISTERED_BACKEND': return 'info'
    case 'ASSIGNED_TO_ZONE': return 'info'
    case 'DEGRADED': return 'warning'
    case 'MAINTENANCE': return 'warning'
    case 'DECOMMISSIONED': return 'neutral'
    default: return 'neutral'
  }
}

function getZonesForGreenhouse(greenhouseId) {
  if (!greenhouseId) return []
  return zones.value.filter(z => z.greenhouse_id === greenhouseId)
}

function onGreenhouseChange(nodeId) {
  // Сбросить zone_id при смене теплицы
  if (assignmentForms[nodeId]) {
    assignmentForms[nodeId].zone_id = null
  }
}

async function loadNewNodes(): Promise<void> {
  startLoading()
  try {
    const previousNodes = new Map(newNodes.value.map(node => [node.id, node]))

    const response = await api.get<{ data?: Device[] } | Device[]>(
      '/nodes',
      { params: { unassigned: true } }
    )
    
    const data = extractData<Device[]>(response.data) || []
    // Обработка пагинации или прямого массива
    if (Array.isArray(data)) {
      newNodes.value = data
    } else {
      newNodes.value = []
    }
    
    // Инициализировать формы для каждой ноды
    newNodes.value.forEach(node => {
      if (node.id && !assignmentForms[node.id]) {
        assignmentForms[node.id] = {
          greenhouse_id: null,
          zone_id: null,
          name: node.name || '',
        }
      }
    })

    // Показать успех привязки для нод, которые исчезли из списка (zone_id установлен)
    const currentIds = new Set(newNodes.value.map(node => node.id))
    Object.entries(pendingAssignments).forEach(([idStr, label]) => {
      const id = Number(idStr)
      if (Number.isFinite(id) && !currentIds.has(id)) {
        showToast(`Нода "${label}" успешно привязана к зоне!`, 'success', TOAST_TIMEOUT.NORMAL)
        delete pendingAssignments[id]
        delete assignmentForms[id]
      }
    })

    // Удаляем формы для нод, которые больше не в списке (на всякий случай)
    previousNodes.forEach((_node, id) => {
      if (!currentIds.has(id)) {
        delete assignmentForms[id]
      }
    })
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Devices/Add] Failed to load new nodes:', err)
  } finally {
    stopLoading()
  }
}

async function loadGreenhouses(): Promise<void> {
  try {
    const response = await api.get<{ data?: Greenhouse[] } | Greenhouse[]>('/greenhouses')
    
    const data = extractData<Greenhouse[]>(response.data) || []
    // Обработка пагинации или прямого массива
    if (Array.isArray(data)) {
      greenhouses.value = data
    } else {
      greenhouses.value = []
    }
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Devices/Add] Failed to load greenhouses:', err)
  }
}

async function loadZones(): Promise<void> {
  try {
    const response = await api.get<{ data?: Zone[] } | Zone[]>('/zones')
    
    const data = extractData<Zone[]>(response.data) || []
    // Обработка пагинации или прямого массива
    if (Array.isArray(data)) {
      zones.value = data
    } else {
      zones.value = []
    }
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Devices/Add] Failed to load zones:', err)
  }
}

async function assignNode(node) {
  const form = assignmentForms[node.id]
  if (!form.zone_id) {
    showToast('Выберите зону для привязки', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  // Lifecycle-aware валидация: проверяем, может ли узел быть присвоен к зоне
  if (node.lifecycle_state && node.lifecycle_state !== 'REGISTERED_BACKEND') {
    const currentStateLabel = getStateLabel(node.lifecycle_state)
    showToast(
      `Узел не может быть присвоен к зоне. Текущее состояние: ${currentStateLabel}. Требуется: Зарегистрирован (REGISTERED_BACKEND)`,
      'error',
      6000
    )
    return
  }

  // Дополнительная проверка через API, если lifecycle_state не доступен
  if (!node.lifecycle_state) {
    try {
      const canAssign = await canAssignToZone(node.id)
      if (!canAssign) {
        showToast(
          'Узел не может быть присвоен к зоне. Узел должен быть зарегистрирован (REGISTERED_BACKEND) перед присвоением.',
          'error',
          6000
        )
        return
      }
    } catch (err) {
      logger.warn('[Devices/Add] Failed to check lifecycle state, proceeding with assignment:', err)
      // Продолжаем с присвоением, backend вернет ошибку если lifecycle не подходит
    }
  }

  assigning[node.id] = true
  try {
    const updateData = {
      zone_id: form.zone_id,
      name: form.name || node.name || node.uid,
    }
    
    const response = await api.patch<{ status: string; data?: Device }>(
      `/nodes/${node.id}`,
      updateData
    )
    
    if (response.data?.status === 'ok' && response.data?.data) {
      const updatedNode = response.data.data
      
      // Проверяем состояние привязки:
      // - Если pending_zone_id установлен (а zone_id = NULL) → привязка в процессе
      // - Если zone_id установлен (а pending_zone_id = NULL) → привязка завершена (lifecycle может измениться позже)
      // - Если lifecycle_state = ASSIGNED_TO_ZONE → полностью завершена
      
      if (updatedNode?.lifecycle_state === 'ASSIGNED_TO_ZONE') {
        // Полностью завершено (редкий случай - обычно это происходит асинхронно)
        showToast(`Нода "${node.uid}" успешно привязана к зоне и получила конфиг`, 'success', TOAST_TIMEOUT.NORMAL)
        
        // Удалить ноду из списка новых (так как она теперь привязана)
        newNodes.value = newNodes.value.filter(n => n.id !== node.id)
        delete assignmentForms[node.id]
        delete pendingAssignments[node.id]
      } else if (updatedNode?.pending_zone_id && !updatedNode?.zone_id) {
        // Конфиг публикуется, ожидаем подтверждения от ноды (через history-logger)
        showToast(
          `Нода "${node.uid}" привязывается к зоне. Конфиг публикуется, ожидайте подтверждения (~2-5 сек)...`,
          'info',
          5000
        )

        pendingAssignments[node.id] = node.uid || node.name || `Node #${node.id}`
        
        // Обновляем данные ноды, но оставляем в списке
        const nodeIndex = newNodes.value.findIndex(n => n.id === node.id)
        if (nodeIndex >= 0) {
          newNodes.value[nodeIndex] = { ...newNodes.value[nodeIndex], ...updatedNode }
        }
        
        // Автоматически обновим список через 3 секунды для проверки завершения
        setTimeout(() => {
          loadNewNodes()
        }, 3000)
      } else if (updatedNode?.zone_id && !updatedNode?.pending_zone_id) {
        // zone_id установлен, pending_zone_id сброшен → привязка успешно завершена
        // (lifecycle может еще быть REGISTERED_BACKEND, но это не важно - привязка завершена)
        showToast(`Нода "${node.uid}" успешно привязана к зоне!`, 'success', TOAST_TIMEOUT.NORMAL)
        
        // Удалить ноду из списка новых
        newNodes.value = newNodes.value.filter(n => n.id !== node.id)
        delete assignmentForms[node.id]
        delete pendingAssignments[node.id]
      } else {
        // Неизвестное состояние
        logger.warn('[Devices/Add] Unexpected node state after assignment:', {
          node_id: node.id,
          zone_id: updatedNode?.zone_id,
          pending_zone_id: updatedNode?.pending_zone_id,
          lifecycle_state: updatedNode?.lifecycle_state,
        })
        showToast(
          `Нода "${node.uid}" обновлена. Проверьте статус через несколько секунд.`,
          'warning',
          TOAST_TIMEOUT.LONG
        )
      }
    }
  } catch (err) {
    logger.error('[Devices/Add] Failed to assign node:', err)
    
    // Используем централизованный обработчик ошибок
    handleError(err, {
      component: 'Devices/Add',
      action: 'assignNode',
      nodeId: node.id,
      zoneId: form.zone_id,
    })
    
    // Дополнительная обработка lifecycle ошибок
    if (err?.response?.data?.message?.includes('lifecycle') || 
        err?.response?.data?.message?.includes('state')) {
      showToast(
        `Ошибка lifecycle: ${err.response.data.message}. Убедитесь, что узел в состоянии REGISTERED_BACKEND.`,
        'error',
        7000
      )
    }
  } finally {
    assigning[node.id] = false
  }
}

async function refreshNodes() {
  showToast('Обновление списка нод...', 'info', TOAST_TIMEOUT.SHORT)
  await loadNewNodes()
}

onMounted(async () => {
  await Promise.all([
    loadNewNodes(),
    loadGreenhouses(),
    loadZones(),
  ])
  
  // Автоматическое обновление каждые 10 секунд
  refreshInterval = setInterval(() => {
    loadNewNodes()
  }, 10000)
})

onUnmounted(() => {
  // Очищаем интервал при уходе со страницы, чтобы предотвратить накопление таймеров
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})
</script>
