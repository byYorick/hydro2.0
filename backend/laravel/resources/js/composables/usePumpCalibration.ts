import { computed, reactive, ref, watch } from 'vue'
import { usePidConfig } from '@/composables/usePidConfig'
import { usePumpCalibrationSettings } from '@/composables/usePumpCalibrationSettings'
import type { Device } from '@/types'
import type { PumpCalibrationComponent, PumpChannelOption, PumpCalibrationSavePayload } from '@/types/Calibration'
import type { PumpCalibrationConfig } from '@/types/Device'

interface PumpCalibrationProps {
  show?: boolean
  zoneId: number | null
  devices: Device[]
  saveSuccessSeq?: number
  runSuccessSeq?: number
  lastRunToken?: string | null
}

const componentOptions: Array<{ value: PumpCalibrationComponent; label: string }> = [
  { value: 'npk', label: 'NPK (комплекс)' },
  { value: 'calcium', label: 'Calcium' },
  { value: 'magnesium', label: 'Magnesium (MgSO4)' },
  { value: 'micro', label: 'Micro' },
  { value: 'ph_up', label: 'pH Up' },
  { value: 'ph_down', label: 'pH Down' },
]

const componentKeywords: Record<PumpCalibrationComponent, string[]> = {
  npk: ['npk', 'part_a', 'nutrient_a', 'a'],
  calcium: ['calcium', 'cal', 'part_b', 'nutrient_b', 'b'],
  magnesium: ['magnesium', 'mg', 'epsom', 'mgso4', 'part_c', 'nutrient_c', 'c'],
  micro: ['micro', 'trace', 'part_d', 'nutrient_d', 'd'],
  ph_up: ['ph_up', 'phup', 'base', 'alkali'],
  ph_down: ['ph_down', 'phdown', 'acid'],
}

export { componentOptions }

export function usePumpCalibration(props: PumpCalibrationProps) {
  const settings = usePumpCalibrationSettings()
  const { getPumpCalibrations } = usePidConfig()
  const form = reactive<{
    component: PumpCalibrationComponent
    node_channel_id: number | null
    duration_sec: number
    actual_ml: number | null
    test_volume_l: number | null
    ec_before_ms: number | null
    ec_after_ms: number | null
    temperature_c: number | null
  }>({
    component: 'npk',
    node_channel_id: null,
    duration_sec: settings.value.default_run_duration_sec,
    actual_ml: null,
    test_volume_l: null,
    ec_before_ms: null,
    ec_after_ms: null,
    temperature_c: null,
  })

  const formError = ref<string | null>(null)
  const persistedBindings = ref<Partial<Record<PumpCalibrationComponent, number>>>({})
  const dbCalibrationsByChannelId = ref<Record<number, PumpCalibrationConfig>>({})
  const pendingRun = ref<{
    runToken: string
    component: PumpCalibrationComponent
    node_channel_id: number
    duration_sec: number
  } | null>(null)

  const storageKey = computed(() => {
    if (!props.zoneId) {
      return null
    }
    return `zone:${props.zoneId}:pump_component_bindings`
  })

  const pumpChannels = computed<PumpChannelOption[]>(() => {
    const keywordPriority: Array<{ keyword: string; score: number }> = [
      { keyword: 'nutrient', score: 30 },
      { keyword: 'pump', score: 20 },
      { keyword: 'dose', score: 15 },
      { keyword: 'ph', score: 10 },
      { keyword: 'acid', score: 10 },
      { keyword: 'base', score: 10 },
    ]

    const channels: PumpChannelOption[] = []

    props.devices.forEach((device) => {
      const deviceLabel = device.uid || device.name || `Node ${device.id}`
      ;(device.channels || []).forEach((channel) => {
        const channelId = Number(channel.id)
        if (!Number.isInteger(channelId) || channelId <= 0) {
          return
        }

        const channelType = String(channel.type || '').toLowerCase()
        if (!channelType.includes('actuator')) {
          return
        }

        const channelName = String(channel.channel || '')
        const lowerName = channelName.toLowerCase()
        const priority = keywordPriority.reduce((maxScore, item) => {
          return lowerName.includes(item.keyword) ? Math.max(maxScore, item.score) : maxScore
        }, 0)

        channels.push({
          id: channelId,
          label: `${deviceLabel} / ${channelName}`,
          channelName,
          priority,
          calibration: dbCalibrationsByChannelId.value[channelId] ?? channel.pump_calibration ?? null,
        })
      })
    })

    return channels.sort((a, b) => {
      if (a.priority !== b.priority) {
        return b.priority - a.priority
      }
      return a.label.localeCompare(b.label)
    })
  })

  const channelById = computed(() => {
    return new Map(pumpChannels.value.map((channel) => [channel.id, channel]))
  })

  const selectedChannel = computed(() => {
    if (!form.node_channel_id) {
      return null
    }
    return channelById.value.get(form.node_channel_id) || null
  })

  const selectedCalibration = computed(() => selectedChannel.value?.calibration || null)

  const calibratedChannels = computed(() => {
    return pumpChannels.value.filter((channel) => channel.calibration && Number(channel.calibration.ml_per_sec) > 0)
  })

  function normalizeComponent(value: unknown): PumpCalibrationComponent | null {
    const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
    if (
      raw === 'npk' ||
      raw === 'calcium' ||
      raw === 'magnesium' ||
      raw === 'micro' ||
      raw === 'ph_up' ||
      raw === 'ph_down'
    ) {
      return raw
    }
    if (raw === 'phup' || raw === 'base') {
      return 'ph_up'
    }
    if (raw === 'phdown' || raw === 'acid') {
      return 'ph_down'
    }
    return null
  }

  function scoreComponent(channelName: string, component: PumpCalibrationComponent): number {
    const lowerName = String(channelName || '').toLowerCase()
    return componentKeywords[component].reduce((score, keyword) => {
      return lowerName.includes(keyword) ? score + 10 : score
    }, 0)
  }

  const autoComponentMap = computed<Partial<Record<PumpCalibrationComponent, number>>>(() => {
    const result: Partial<Record<PumpCalibrationComponent, number>> = {}
    const usedIds = new Set<number>()
    const components = componentOptions.map((option) => option.value)
    const availableIds = new Set(pumpChannels.value.map((channel) => channel.id))

    const assign = (component: PumpCalibrationComponent, channelId: number | null | undefined): boolean => {
      if (!channelId || !availableIds.has(channelId) || usedIds.has(channelId)) {
        return false
      }
      result[component] = channelId
      usedIds.add(channelId)
      return true
    }

    components.forEach((component) => {
      assign(component, persistedBindings.value[component])
    })

    components.forEach((component) => {
      if (result[component]) {
        return
      }

      const byCalibration = pumpChannels.value
        .filter((channel) => normalizeComponent(channel.calibration?.component) === component)
        .sort((a, b) => {
          const aTs = Date.parse(String(a.calibration?.calibrated_at || ''))
          const bTs = Date.parse(String(b.calibration?.calibrated_at || ''))
          return (Number.isFinite(bTs) ? bTs : 0) - (Number.isFinite(aTs) ? aTs : 0)
        })

      for (const candidate of byCalibration) {
        if (assign(component, candidate.id)) {
          break
        }
      }
    })

    components.forEach((component) => {
      if (result[component]) {
        return
      }

      const byKeyword = pumpChannels.value
        .map((channel) => ({
          channel,
          score: scoreComponent(channel.channelName, component),
        }))
        .filter((entry) => entry.score > 0)
        .sort((a, b) => b.score - a.score || b.channel.priority - a.channel.priority)

      for (const candidate of byKeyword) {
        if (assign(component, candidate.channel.id)) {
          break
        }
      }
    })

    return result
  })

  function loadPersistedBindings(): void {
    if (typeof window === 'undefined' || !storageKey.value) {
      persistedBindings.value = {}
      return
    }

    const raw = window.localStorage.getItem(storageKey.value)
    if (!raw) {
      persistedBindings.value = {}
      return
    }

    try {
      const parsed = JSON.parse(raw) as Partial<Record<PumpCalibrationComponent, number>>
      const sanitized: Partial<Record<PumpCalibrationComponent, number>> = {}
      componentOptions.forEach(({ value }) => {
        const candidate = Number(parsed[value])
        if (Number.isInteger(candidate) && candidate > 0) {
          sanitized[value] = candidate
        }
      })
      persistedBindings.value = sanitized
    } catch {
      persistedBindings.value = {}
    }
  }

  function savePersistedBindings(): void {
    if (typeof window === 'undefined' || !storageKey.value) {
      return
    }
    window.localStorage.setItem(storageKey.value, JSON.stringify(persistedBindings.value))
  }

  function ensureSelection(): void {
    if (pumpChannels.value.length === 0) {
      form.node_channel_id = null
      return
    }

    const component = form.component
    const preferredChannelId = autoComponentMap.value[component]
    if (preferredChannelId) {
      form.node_channel_id = preferredChannelId
      return
    }

    const firstMapped = componentOptions.find((option) => autoComponentMap.value[option.value])
    if (firstMapped) {
      form.component = firstMapped.value
      form.node_channel_id = autoComponentMap.value[firstMapped.value] || null
      return
    }

    if (!form.node_channel_id || !channelById.value.has(form.node_channel_id)) {
      form.node_channel_id = pumpChannels.value[0].id
    }
  }

  function moveToNextComponent(): void {
    const components = componentOptions.map((option) => option.value)
    const currentIndex = components.indexOf(form.component)

    for (let offset = 1; offset <= components.length; offset += 1) {
      const component = components[(currentIndex + offset) % components.length]
      const channelId = autoComponentMap.value[component]
      if (!channelId) {
        continue
      }
      form.component = component
      form.node_channel_id = channelId
      form.actual_ml = null
      form.ec_before_ms = null
      form.ec_after_ms = null
      form.test_volume_l = null
      form.temperature_c = null
      formError.value = null
      return
    }

    form.actual_ml = null
    form.ec_before_ms = null
    form.ec_after_ms = null
    form.test_volume_l = null
    form.temperature_c = null
    formError.value = null
  }

  function validateCommon(): string | null {
    if (!props.zoneId || props.zoneId <= 0) {
      return 'Не удалось определить зону для калибровки.'
    }
    if (!form.node_channel_id || form.node_channel_id <= 0) {
      return 'Выберите канал помпы.'
    }
    if (
      !Number.isFinite(form.duration_sec)
      || form.duration_sec < settings.value.calibration_duration_min_sec
      || form.duration_sec > settings.value.calibration_duration_max_sec
    ) {
      return `Время запуска должно быть от ${settings.value.calibration_duration_min_sec} до ${settings.value.calibration_duration_max_sec} секунд.`
    }
    const hasAnyEcCalibrationInput = form.test_volume_l !== null || form.ec_before_ms !== null || form.ec_after_ms !== null
    if (hasAnyEcCalibrationInput) {
      if (!Number.isFinite(form.test_volume_l) || (form.test_volume_l as number) <= 0) {
        return 'Для расчёта k укажите объём тестового раствора больше 0 л.'
      }
      if (!Number.isFinite(form.ec_before_ms) || (form.ec_before_ms as number) < 0) {
        return 'Для расчёта k укажите EC до дозы (>= 0).'
      }
      if (!Number.isFinite(form.ec_after_ms) || (form.ec_after_ms as number) < 0) {
        return 'Для расчёта k укажите EC после дозы (>= 0).'
      }
      if ((form.ec_after_ms as number) <= (form.ec_before_ms as number)) {
        return 'EC после дозы должен быть больше EC до дозы.'
      }
    }
    return null
  }

  function buildSavePayload(): PumpCalibrationSavePayload {
    const payload: PumpCalibrationSavePayload = {
      node_channel_id: form.node_channel_id as number,
      duration_sec: Math.trunc(form.duration_sec),
      actual_ml: Number(form.actual_ml),
      component: form.component,
      skip_run: true,
    }

    const currentDurationSec = Math.trunc(form.duration_sec)
    if (
      pendingRun.value
      && pendingRun.value.component === form.component
      && pendingRun.value.node_channel_id === form.node_channel_id
      && pendingRun.value.duration_sec === currentDurationSec
    ) {
      payload.run_token = pendingRun.value.runToken
    } else {
      payload.manual_override = true
    }

    if (Number.isFinite(form.test_volume_l) && (form.test_volume_l as number) > 0) {
      payload.test_volume_l = Number(form.test_volume_l)
    }
    if (Number.isFinite(form.ec_before_ms) && (form.ec_before_ms as number) >= 0) {
      payload.ec_before_ms = Number(form.ec_before_ms)
    }
    if (Number.isFinite(form.ec_after_ms) && (form.ec_after_ms as number) >= 0) {
      payload.ec_after_ms = Number(form.ec_after_ms)
    }
    if (Number.isFinite(form.temperature_c)) {
      payload.temperature_c = Number(form.temperature_c)
    }

    return payload
  }

  const estimatedK = computed<number | null>(() => {
    if (
      !Number.isFinite(form.actual_ml) ||
      !Number.isFinite(form.test_volume_l) ||
      !Number.isFinite(form.ec_before_ms) ||
      !Number.isFinite(form.ec_after_ms)
    ) {
      return null
    }

    const actualMl = Number(form.actual_ml)
    const testVolume = Number(form.test_volume_l)
    const ecBefore = Number(form.ec_before_ms)
    const ecAfter = Number(form.ec_after_ms)

    if (actualMl <= 0 || testVolume <= 0 || ecAfter <= ecBefore) {
      return null
    }

    const mlPerL = actualMl / testVolume
    if (mlPerL <= 0) {
      return null
    }
    return (ecAfter - ecBefore) / mlPerL
  })

  function formatDateTime(value: string): string {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return value
    }
    return date.toLocaleString('ru-RU')
  }

  async function refreshDbCalibrations(): Promise<void> {
    if (!props.zoneId || props.zoneId <= 0) {
      dbCalibrationsByChannelId.value = {}
      return
    }

    try {
      const calibrations = await getPumpCalibrations(props.zoneId)
      dbCalibrationsByChannelId.value = calibrations.reduce<Record<number, PumpCalibrationConfig>>((acc, item) => {
        acc[item.node_channel_id] = {
          ml_per_sec: item.ml_per_sec ?? undefined,
          k_ms_per_ml_l: item.k_ms_per_ml_l ?? undefined,
          component: item.component ?? undefined,
          calibrated_at: item.valid_from ?? null,
        }
        return acc
      }, {})
    } catch {
      // Не блокируем UX модалки, если refresh из БД не удался.
    }
  }

  // ── Watchers ─────────────────────────────────────────────────────────────
  watch(
    () => props.show,
    (isOpen) => {
      if (!isOpen) {
        return
      }
      void refreshDbCalibrations()
      loadPersistedBindings()
      pendingRun.value = null
      formError.value = null
      form.duration_sec = settings.value.default_run_duration_sec
      ensureSelection()
    },
  )

  watch(
    pumpChannels,
    () => {
      ensureSelection()
    },
    { immediate: true },
  )

  watch(
    () => form.component,
    (component) => {
      const preferredChannelId = autoComponentMap.value[component]
      if (preferredChannelId) {
        form.node_channel_id = preferredChannelId
        return
      }

      if (!form.node_channel_id || !channelById.value.has(form.node_channel_id)) {
        form.node_channel_id = pumpChannels.value[0]?.id || null
      }
    },
  )

  watch(
    () => form.node_channel_id,
    (nodeChannelId) => {
      if (!nodeChannelId || !channelById.value.has(nodeChannelId)) {
        return
      }
      persistedBindings.value[form.component] = nodeChannelId
      savePersistedBindings()
    },
  )

  watch(
    () => props.runSuccessSeq,
    (next, prev) => {
      if (!props.show || !props.lastRunToken || (next ?? 0) <= (prev ?? 0) || !form.node_channel_id) {
        return
      }

      pendingRun.value = {
        runToken: props.lastRunToken,
        component: form.component,
        node_channel_id: form.node_channel_id,
        duration_sec: Math.trunc(form.duration_sec),
      }
    },
  )

  watch(
    () => props.saveSuccessSeq,
    async (next, prev) => {
      if (!props.show || (next ?? 0) <= (prev ?? 0)) {
        return
      }
      pendingRun.value = null
      await refreshDbCalibrations()
      moveToNextComponent()
    },
  )

  return {
    form,
    formError,
    componentOptions,
    pumpChannels,
    channelById,
    selectedChannel,
    selectedCalibration,
    calibratedChannels,
    autoComponentMap,
    estimatedK,
    validateCommon,
    moveToNextComponent,
    buildSavePayload,
    formatDateTime,
  }
}
