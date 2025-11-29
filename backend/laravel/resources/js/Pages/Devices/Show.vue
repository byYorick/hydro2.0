<template>
  <AppLayout>
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
import { logger } from '@/utils/logger'
import { useHistory } from '@/composables/useHistory'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useApi } from '@/composables/useApi'
import { useDevicesStore } from '@/stores/devices'
import type { Device, DeviceChannel } from '@/types'

interface PageProps {
  device?: Device
}

const page = usePage<PageProps>()
const device = computed(() => (page.props.device || {}) as Device)
const channels = computed(() => (device.value.channels || []) as DeviceChannel[])
const testingChannels = ref<Set<string>>(new Set())
const detaching = ref(false)
const { showToast } = useToast()
const { api } = useApi(showToast)
const devicesStore = useDevicesStore()

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

const onRestart = async (): Promise<void> => {
  try {
    const response = await api.post<{ status: string }>(
      `/nodes/${device.value.id}/commands`,
      {
        type: 'restart',
        params: {},
      }
    )
    
    if (response.data?.status === 'ok') {
      logger.debug('[Devices/Show] Device restart command sent successfully', response.data)
      showToast('Команда перезапуска отправлена', 'success', TOAST_TIMEOUT.NORMAL)
    }
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Devices/Show] Failed to restart device:', err)
  }
}

const detachNode = async (): Promise<void> => {
  if (!device.value.zone_id) {
    showToast('Нода уже отвязана от зоны', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  if (!confirm('Вы уверены, что хотите отвязать ноду от зоны? Нода будет сброшена в состояние "Зарегистрирована" и появится в списке новых нод.')) {
    return
  }

  detaching.value = true
  try {
    const response = await api.post<{ status: string; data?: Device }>(
      `/nodes/${device.value.id}/detach`,
      {}
    )
    
    if (response.data?.status === 'ok') {
      logger.debug('[Devices/Show] Node detached successfully', response.data)
      showToast(`Нода "${device.value.uid || device.value.name}" успешно отвязана от зоны`, 'success', TOAST_TIMEOUT.NORMAL)
      
      // Обновляем device локально, убирая zone_id, вместо полного reload
      const updatedDevice = response.data?.data || {
        ...device.value,
        zone_id: null,
        zone: null,
      }
      
      // Обновляем device в store для мгновенного отображения
      if (updatedDevice?.id) {
        devicesStore.upsert(updatedDevice)
        logger.debug('[Devices/Show] Device updated in store after detach', { deviceId: updatedDevice.id })
      }
      
      // Опционально: можно перенаправить на список устройств, если нужно
      // router.visit('/devices')
    }
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('[Devices/Show] Failed to detach node:', err)
  } finally {
    detaching.value = false
  }
}

// Функция для теста конкретного насоса/клапана
const onTestPump = async (channelName: string, channelType: string): Promise<void> => {
  if (testingChannels.value.has(channelName)) return
  
  testingChannels.value.add(channelName)
  const channelLabel = getChannelLabel(channelName, channelType)
  showToast(`Запуск теста: ${channelLabel}...`, 'info', TOAST_TIMEOUT.SHORT)
  
  try {
    // Определяем команду в зависимости от типа канала
    let commandType = 'run_pump'
    let params = { duration_ms: 3000 } // 3 секунды
    
    // Для клапанов используем другую команду (заглушка)
    if (channelType === 'valve' || channelName.includes('valve')) {
      commandType = 'set_relay'
      params = { state: true, duration_ms: 3000 }
    }
    
    const response = await api.post<{ status: string; data?: { command_id: number } }>(
      `/nodes/${device.value.id}/commands`,
      {
        type: commandType,
        channel: channelName,
        params: params,
      }
    )
    
    if (response.data?.status === 'ok' && response.data?.data?.command_id) {
      const cmdId = response.data.data.command_id
      // Ожидаем ответа от ноды
      const result = await checkCommandStatus(cmdId, 30) // Максимум 30 секунд
      
      if (result.success) {
        showToast(`Тест ${channelLabel} выполнен успешно!`, 'success', TOAST_TIMEOUT.LONG)
      } else {
        showToast(`Ошибка теста ${channelLabel}: ${result.status}`, 'error', TOAST_TIMEOUT.LONG)
      }
    } else {
      showToast(`Не удалось отправить команду для ${channelLabel}`, 'error', TOAST_TIMEOUT.LONG)
    }
  } catch (err) {
    // Ошибка уже обработана в useApi через showToast
    logger.error(`[Devices/Show] Failed to test ${channelName}:`, err)
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
async function checkCommandStatus(cmdId: number, maxAttempts = 30): Promise<{ success: boolean; status: string; error?: string }> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await api.get<{ status: string; data?: { status: string } }>(
        `/commands/${cmdId}/status`
      )
      
      if (response.data?.status === 'ok' && response.data?.data) {
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
      const errorStatus = (err as { response?: { status?: number } })?.response?.status
      if (errorStatus === 404 && i < maxAttempts - 1) {
        await new Promise(resolve => setTimeout(resolve, 500))
        continue
      }
      const errorMessage = err instanceof Error ? err.message : 'Unknown error'
      return { success: false, status: 'error', error: errorMessage }
    }
  }
  return { success: false, status: 'timeout' }
}

</script>

