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
    
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-lg font-semibold">{{ device.uid || device.name || device.id }}</div>
        <div class="text-xs text-neutral-400">
          <span v-if="device.zone">
            <Link :href="`/zones/${device.zone.id}`" class="text-sky-400 hover:underline">Zone: {{ device.zone.name }}</Link>
          </span>
          <span v-else>Zone: -</span>
          · Type: {{ device.type || '-' }}
          <span v-if="device.fw_version"> · FW: {{ device.fw_version }}</span>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <Badge :variant="device.status === 'online' ? 'success' : device.status === 'offline' ? 'danger' : 'neutral'">
          {{ device.status?.toUpperCase() || 'UNKNOWN' }}
        </Badge>
        <NodeLifecycleBadge v-if="device.lifecycle_state" :lifecycle-state="device.lifecycle_state" />
        <Button size="sm" variant="secondary" @click="onRestart">Restart</Button>
      </div>
    </div>

    <!-- Визуализация связи с зоной -->
    <Card v-if="device.zone" class="mb-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg border-2 border-sky-500/50 bg-sky-950/20 flex items-center justify-center">
            <span class="text-2xl">🌱</span>
          </div>
          <div>
            <div class="text-sm font-semibold text-neutral-200">Привязано к зоне</div>
            <Link :href="`/zones/${device.zone.id}`" class="text-sky-400 hover:text-sky-300 hover:underline text-sm">
              {{ device.zone.name }}
            </Link>
            <div v-if="device.zone.status" class="text-xs text-neutral-400 mt-1">
              Статус: {{ device.zone.status }}
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Link :href="`/zones/${device.zone.id}`">
            <Button size="sm" variant="outline">
              Перейти к зоне →
            </Button>
          </Link>
          <button 
            @click="detachNode"
            :disabled="detaching"
            class="inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-red-600/50 h-8 px-3 text-xs bg-red-900/50 hover:bg-red-800/50 text-red-200 border border-red-700/50 hover:border-red-600/50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg v-if="!detaching" class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            <span v-if="detaching">Отвязка...</span>
            <span v-else>Отвязать от зоны</span>
          </button>
        </div>
      </div>
    </Card>
    <Card v-else class="mb-3 border-amber-500/30 bg-amber-950/10">
      <div class="flex items-center gap-2 text-amber-400">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <span class="text-sm">Устройство не привязано к зоне</span>
      </div>
    </Card>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
      <Card class="xl:col-span-2">
        <div class="text-sm font-semibold mb-2">Channels</div>
        <DeviceChannelsTable 
          :channels="channels" 
          :node-type="device.type"
          :testing-channels="testingChannels"
          @test="onTestPump" 
        />
      </Card>
      <Card>
        <div class="text-sm font-semibold mb-2">NodeConfig</div>
        <pre class="text-xs text-neutral-300 overflow-auto">{{ nodeConfig }}</pre>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Link, usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import NodeLifecycleBadge from '@/Components/NodeLifecycleBadge.vue'
import DeviceChannelsTable from '@/Pages/Devices/DeviceChannelsTable.vue'
import Toast from '@/Components/Toast.vue'
import { logger } from '@/utils/logger'
import axios from 'axios'
import { useHistory } from '@/composables/useHistory'
import type { Device, DeviceChannel } from '@/types'
import type { ToastVariant } from '@/composables/useToast'

interface PageProps {
  device?: Device
}

interface ToastItem {
  id: number
  message: string
  variant: ToastVariant
  duration: number
}

const page = usePage<PageProps>()
const device = computed(() => (page.props.device || {}) as Device)
const channels = computed(() => (device.value.channels || []) as DeviceChannel[])
const testingChannels = ref<Set<string>>(new Set())
const toasts = ref<ToastItem[]>([])
const detaching = ref(false)
let toastIdCounter = 0

// История просмотров
const { addToHistory } = useHistory()

// Добавляем устройство в историю просмотров
watch(device, (newDevice) => {
  if (newDevice?.id) {
    addToHistory({
      id: newDevice.id,
      type: 'device',
      name: newDevice.name || newDevice.uid || `Устройство ${newDevice.id}`,
      url: `/devices/${newDevice.id}`
    })
  }
}, { immediate: true })

const nodeConfig = computed(() => {
  const config = {
    id: device.value.uid || device.value.id,
    name: device.value.name,
    type: device.value.type,
    status: device.value.status,
    fw_version: device.value.fw_version,
    config: device.value.config,
    channels: channels.value.map(c => ({
      channel: c.channel,
      type: c.type,
      metric: c.metric,
      unit: c.unit,
    })),
  }
  return JSON.stringify(config, null, 2)
})

function showToast(message: string, variant: ToastVariant = 'info', duration: number = 3000): number {
  const id = ++toastIdCounter
  toasts.value.push({ id, message, variant, duration })
  return id
}

function removeToast(id: number): void {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index > -1) {
    toasts.value.splice(index, 1)
  }
}

const onRestart = async (): Promise<void> => {
  try {
    const response = await axios.post(`/api/nodes/${device.value.id}/commands`, {
      type: 'restart',
      params: {},
    }, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    if (response.data?.status === 'ok') {
      logger.debug('[Devices/Show] Device restart command sent successfully', response.data)
      showToast('Команда перезапуска отправлена', 'success', 3000)
    }
  } catch (err) {
    logger.error('[Devices/Show] Failed to restart device:', err)
    let errorMsg = 'Неизвестная ошибка'
    if (err && err.response && err.response.data && err.response.data.message) errorMsg = err.response.data.message
    else if (err && err.message) errorMsg = err.message
    showToast(`Ошибка перезапуска: ${errorMsg}`, 'error', 5000)
  }
}

const detachNode = async (): Promise<void> => {
  if (!device.value.zone_id) {
    showToast('Нода уже отвязана от зоны', 'warning', 3000)
    return
  }

  if (!confirm('Вы уверены, что хотите отвязать ноду от зоны? Нода будет сброшена в состояние "Зарегистрирована" и появится в списке новых нод.')) {
    return
  }

  detaching.value = true
  try {
    const response = await axios.post(`/api/nodes/${device.value.id}/detach`, {}, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    if (response.data?.status === 'ok') {
      logger.debug('[Devices/Show] Node detached successfully', response.data)
      showToast(`Нода "${device.value.uid || device.value.name}" успешно отвязана от зоны`, 'success', 3000)
      
      // Перезагружаем страницу для обновления данных
      router.reload({ only: ['device'], preserveScroll: false })
    }
  } catch (err: any) {
    logger.error('[Devices/Show] Failed to detach node:', err)
    let errorMsg = 'Неизвестная ошибка'
    if (err?.response?.data?.message) {
      errorMsg = err.response.data.message
    } else if (err?.message) {
      errorMsg = err.message
    }
    showToast(`Ошибка отвязки: ${errorMsg}`, 'error', 5000)
  } finally {
    detaching.value = false
  }
}

// Функция для теста конкретного насоса/клапана
const onTestPump = async (channelName: string, channelType: string): Promise<void> => {
  if (testingChannels.value.has(channelName)) return
  
  testingChannels.value.add(channelName)
  const channelLabel = getChannelLabel(channelName, channelType)
  showToast(`Запуск теста: ${channelLabel}...`, 'info', 2000)
  
  try {
    // Определяем команду в зависимости от типа канала
    let commandType = 'run_pump'
    let params = { duration_ms: 3000 } // 3 секунды
    
    // Для клапанов используем другую команду (заглушка)
    if (channelType === 'valve' || channelName.includes('valve')) {
      commandType = 'set_relay'
      params = { state: true, duration_ms: 3000 }
    }
    
    const response = await axios.post(`/api/nodes/${device.value.id}/commands`, {
      type: commandType,
      channel: channelName,
      params: params,
    }, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    if (response.data?.status === 'ok' && response.data?.data?.command_id) {
      const cmdId = response.data.data.command_id
      // Ожидаем ответа от ноды
      const result = await checkCommandStatus(cmdId, 30) // Максимум 15 секунд
      
      if (result.success) {
        showToast(`Тест ${channelLabel} выполнен успешно!`, 'success', 5000)
      } else {
        showToast(`Ошибка теста ${channelLabel}: ${result.status}`, 'error', 5000)
      }
    } else {
      showToast(`Не удалось отправить команду для ${channelLabel}`, 'error', 5000)
    }
  } catch (err) {
    logger.error(`[Devices/Show] Failed to test ${channelName}:`, err)
    let errorMsg = 'Неизвестная ошибка'
    if (err && err.response && err.response.data && err.response.data.message) errorMsg = err.response.data.message
    else if (err && err.message) errorMsg = err.message
    showToast(`Ошибка теста ${channelLabel}: ${errorMsg}`, 'error', 5000)
  } finally {
    testingChannels.value.delete(channelName)
  }
}

// Функция для получения читаемого названия канала
function getChannelLabel(channelName, channelType) {
  const name = (channelName || '').toLowerCase()
  const nodeType = (device.value.type || '').toLowerCase()
  
  // PH нода
  if (nodeType.includes('ph')) {
    if (name.includes('acid') || name.includes('up')) return 'PH UP тест'
    if (name.includes('base') || name.includes('down')) return 'PH DOWN тест'
  }
  
  // EC нода
  if (nodeType.includes('ec')) {
    if (name.includes('nutrient_a') || name.includes('pump_a')) return 'Тест насоса A'
    if (name.includes('nutrient_b') || name.includes('pump_b')) return 'Тест насоса B'
    if (name.includes('nutrient_c') || name.includes('pump_c')) return 'Тест насоса C'
    if (name.includes('nutrient')) return 'Тест насоса питательного раствора'
  }
  
  // Pump нода
  if (nodeType.includes('pump')) {
    if (name.includes('main') || name.includes('primary')) return 'Тест главного насоса'
    if (name.includes('backup') || name.includes('reserve') || name.includes('reserve')) return 'Тест резервного насоса'
    if (name.includes('transfer') || name.includes('перекач')) return 'Тест перекачивающего насоса'
    if (name.includes('valve') || channelType === 'valve') return 'Тест клапана'
  }
  
  // Общий случай
  return channelName || 'Канал'
}

// Функция для проверки статуса команды
async function checkCommandStatus(cmdId, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await axios.get(`/api/commands/${cmdId}/status`, {
        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      })
      
      if (response.data?.status === 'ok') {
        const cmdStatus = response.data.data.status
        if (cmdStatus === 'ack') {
          return { success: true, status: 'ack' }
        } else if (cmdStatus === 'failed') {
          return { success: false, status: 'failed' }
        } else if (cmdStatus === 'pending') {
          // Продолжаем ожидание
          await new Promise(resolve => setTimeout(resolve, 500))
          continue
        }
      }
    } catch (err) {
      logger.error('[Devices/Show] Failed to check command status:', err)
      // Если команда не найдена, возможно она еще не создана, продолжаем ожидание
      if ((err as { response?: { status?: number } })?.response?.status === 404 && i < maxAttempts - 1) {
        await new Promise(resolve => setTimeout(resolve, 500))
        continue
      }
      return { success: false, status: 'error', error: err.message }
    }
  }
  return { success: false, status: 'timeout' }
}

</script>

