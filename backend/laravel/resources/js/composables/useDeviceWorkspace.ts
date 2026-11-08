import { computed, onMounted, onUnmounted, ref, toValue, type MaybeRefOrGetter, type Ref } from 'vue'
import type { DeviceChannel } from '@/types'
import { useUrlState } from './useUrlState'
import { translateStatus } from '@/utils/i18n'

export function useDeviceWorkspace(options: {
  canDiagnose: Ref<boolean>
  channels: MaybeRefOrGetter<DeviceChannel[]>
  series: Ref<Record<string, Array<{ ts: number; value: number }>>>
}) {
  const deviceViewTabs = computed(() => [
    { id: 'state', label: 'Состояние' }, { id: 'channels', label: 'Каналы' }, { id: 'telemetry', label: 'Измерения' }, { id: 'calibration', label: 'Калибровка' },
    ...(options.canDiagnose.value ? [{ id: 'config', label: 'Конфигурация' }] : []),
  ])
  const deviceView = useUrlState({ key: 'view', defaultValue: 'state', parse: value => value && deviceViewTabs.value.some(tab => tab.id === value) ? value : 'state' })
  const observationNow = ref(Date.now())
  let observationTimer: ReturnType<typeof setInterval> | undefined
  onMounted(() => { observationTimer = setInterval(() => { observationNow.value = Date.now() }, 30_000) })
  onUnmounted(() => { clearInterval(observationTimer) })
  const freshSensorCount = computed(() => toValue(options.channels).filter(channel => {
    const points = options.series.value[channel.channel] ?? []
    const latest = points.reduce((at, point) => Number.isFinite(point.ts) ? Math.max(at, point.ts) : at, 0)
    return latest > 0 && latest <= observationNow.value + 30_000 && observationNow.value - latest <= 300_000
  }).length)

  return { deviceViewTabs, deviceView, freshSensorCount }
}

export function formatDeviceStatus(status?: string | null): string {
  const key = String(status || 'unknown').trim().toUpperCase()
  if (!key || key === 'UNKNOWN') {
    return 'Неизвестно'
  }
  return translateStatus(key)
}
