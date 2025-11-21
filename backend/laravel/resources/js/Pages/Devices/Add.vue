<template>
  <AppLayout>
    <!-- Toast notifications -->
    <Teleport to="body">
      <div 
        class="fixed top-4 right-4 z-[10000] space-y-2 pointer-events-none"
        style="position: fixed !important; top: 1rem !important; right: 1rem !important; z-index: 10000 !important; pointer-events: none;"
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto"
          style="pointer-events: auto;"
        >
          <Toast
            :message="toast.message"
            :variant="toast.variant"
            :duration="toast.duration"
            @close="removeToast(toast.id)"
          />
        </div>
      </div>
    </Teleport>
    
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
        <ol class="text-xs text-neutral-400 space-y-1 list-decimal list-inside">
          <li>Включите новую ноду. Она поднимет точку доступа Wi-Fi.</li>
          <li>Подключитесь с телефона к точке доступа ноды.</li>
          <li>Откройте в браузере <code class="text-sky-400">192.168.4.1</code></li>
          <li>Введите SSID и пароль вашей Wi-Fi сети.</li>
          <li>Нода перезагрузится и отправит discovery сообщение.</li>
          <li>Нажмите "Обновить список" или нода появится автоматически.</li>
          <li>Привяжите ноду к зоне через форму ниже.</li>
        </ol>
      </Card>

      <!-- Список новых нод -->
      <Card>
        <div class="text-sm font-semibold mb-3">Новые ноды (без привязки к зоне)</div>
        <div v-if="loading" class="text-sm text-neutral-400 py-4 text-center">
          Загрузка...
        </div>
        <div v-else-if="newNodes.length === 0" class="text-sm text-neutral-400 py-4 text-center">
          Новых нод не найдено. Убедитесь, что нода подключена к Wi-Fi и отправила discovery сообщение.
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="node in newNodes"
            :key="node.id"
            class="p-3 rounded-lg border border-neutral-800 bg-neutral-900"
          >
              <div class="flex items-start justify-between mb-2">
              <div>
                <div class="text-sm font-semibold">{{ node.name || node.uid || `Node #${node.id}` }}</div>
                <div class="text-xs text-neutral-400 mt-1">
                  <span v-if="node.uid">UID: {{ node.uid }}</span>
                  <span v-if="node.type" class="ml-2">Тип: {{ node.type }}</span>
                  <span v-if="node.fw_version" class="ml-2">FW: {{ node.fw_version }}</span>
                </div>
                <div class="text-xs text-neutral-500 mt-1">
                  <span v-if="node.last_seen_at">
                    Последний раз видели: {{ formatDate(node.last_seen_at) }}
                  </span>
                  <span v-else>Никогда не видели</span>
                  <span v-if="node.lifecycle_state" class="ml-2">
                    · Lifecycle: <span class="text-sky-400">{{ getStateLabel(node.lifecycle_state) }}</span>
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
            <div class="mt-3 pt-3 border-t border-neutral-800">
              <div class="text-xs font-semibold mb-2 text-neutral-300">Привязать к зоне:</div>
              <form @submit.prevent="assignNode(node)" class="grid grid-cols-1 md:grid-cols-4 gap-2">
                <select
                  v-model="assignmentForms[node.id].greenhouse_id"
                  @change="onGreenhouseChange(node.id)"
                  class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
                  required
                >
                  <option :value="null">Выберите теплицу</option>
                  <option v-for="gh in greenhouses" :key="gh.id" :value="gh.id">
                    {{ gh.name }}
                  </option>
                </select>
                <select
                  v-model="assignmentForms[node.id].zone_id"
                  class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
                  :disabled="!assignmentForms[node.id].greenhouse_id"
                  required
                >
                  <option :value="null">Выберите зону</option>
                  <option v-for="zone in getZonesForGreenhouse(assignmentForms[node.id].greenhouse_id)" :key="zone.id" :value="zone.id">
                    {{ zone.name }}
                  </option>
                </select>
                <input
                  v-model="assignmentForms[node.id].name"
                  placeholder="Имя ноды (опционально)"
                  class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
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
import { ref, reactive, onMounted, computed } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Toast from '@/Components/Toast.vue'
import { logger } from '@/utils/logger'
import axios from 'axios'
import { useNodeLifecycle } from '@/composables/useNodeLifecycle'
import { useErrorHandler } from '@/composables/useErrorHandler'
import type { Device } from '@/types'

// Toast notifications
const toasts = ref([])
let toastIdCounter = 0

function showToast(message, variant = 'info', duration = 3000) {
  const id = ++toastIdCounter
  toasts.value.push({ id, message, variant, duration })
  return id
}

function removeToast(id) {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index > -1) {
    toasts.value.splice(index, 1)
  }
}

// Инициализация composables для lifecycle
const { canAssignToZone, getStateLabel } = useNodeLifecycle(showToast)
const { handleError } = useErrorHandler(showToast)

const loading = ref(false)
const newNodes = ref([])
const greenhouses = ref([])
const zones = ref([])
const assigning = reactive({})
const assignmentForms = reactive({})

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

async function loadNewNodes() {
  loading.value = true
  try {
    const response = await axios.get('/api/nodes', {
      params: { unassigned: true },
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    const data = response.data?.data
    // Обработка пагинации или прямого массива
    if (data?.data && Array.isArray(data.data)) {
      newNodes.value = data.data
    } else if (Array.isArray(data)) {
      newNodes.value = data
    } else {
      newNodes.value = []
    }
    
    // Инициализировать формы для каждой ноды
    newNodes.value.forEach(node => {
      if (!assignmentForms[node.id]) {
        assignmentForms[node.id] = {
          greenhouse_id: null,
          zone_id: null,
          name: node.name || '',
        }
      }
    })
  } catch (err) {
    logger.error('[Devices/Add] Failed to load new nodes:', err)
    showToast('Ошибка при загрузке новых нод', 'error', 5000)
  } finally {
    loading.value = false
  }
}

async function loadGreenhouses() {
  try {
    const response = await axios.get('/api/greenhouses', {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    const data = response.data?.data
    // Обработка пагинации или прямого массива
    if (data?.data && Array.isArray(data.data)) {
      greenhouses.value = data.data
    } else if (Array.isArray(data)) {
      greenhouses.value = data
    } else {
      greenhouses.value = []
    }
  } catch (err) {
    logger.error('[Devices/Add] Failed to load greenhouses:', err)
  }
}

async function loadZones() {
  try {
    const response = await axios.get('/api/zones', {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    const data = response.data?.data
    // Обработка пагинации или прямого массива
    if (data?.data && Array.isArray(data.data)) {
      zones.value = data.data
    } else if (Array.isArray(data)) {
      zones.value = data
    } else {
      zones.value = []
    }
  } catch (err) {
    logger.error('[Devices/Add] Failed to load zones:', err)
  }
}

async function assignNode(node) {
  const form = assignmentForms[node.id]
  if (!form.zone_id) {
    showToast('Выберите зону для привязки', 'error', 3000)
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
    
    const response = await axios.patch(`/api/nodes/${node.id}`, updateData, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    if (response.data?.status === 'ok') {
      showToast(`Нода "${node.uid}" успешно привязана к зоне`, 'success', 3000)
      
      // Backend автоматически переведет узел в ASSIGNED_TO_ZONE, обновляем данные
      const updatedNode = response.data.data
      if (updatedNode) {
        const nodeIndex = newNodes.value.findIndex(n => n.id === node.id)
        if (nodeIndex >= 0) {
          newNodes.value[nodeIndex] = { ...newNodes.value[nodeIndex], ...updatedNode }
        }
      }
      
      // Удалить ноду из списка новых (так как она теперь привязана)
      newNodes.value = newNodes.value.filter(n => n.id !== node.id)
      delete assignmentForms[node.id]
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
  showToast('Обновление списка нод...', 'info', 2000)
  await loadNewNodes()
}

onMounted(async () => {
  await Promise.all([
    loadNewNodes(),
    loadGreenhouses(),
    loadZones(),
  ])
  
  // Автоматическое обновление каждые 10 секунд
  setInterval(() => {
    loadNewNodes()
  }, 10000)
})
</script>

