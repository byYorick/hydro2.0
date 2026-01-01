<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center">
    <div class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80" @click="$emit('close')"></div>
    <div class="relative w-full max-w-2xl rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-6 max-h-[90vh] overflow-y-auto" @click.stop>
      <h2 class="text-lg font-semibold mb-4">Digital Twin Simulation</h2>
      
      <form @submit.prevent="onSubmit" class="space-y-4" @click.stop>
        <div>
          <label for="simulation-duration-hours" class="block text-sm font-medium mb-1">Duration (hours)</label>
          <input
            id="simulation-duration-hours"
            name="duration_hours"
            v-model.number="form.duration_hours"
            type="number"
            min="1"
            max="720"
            class="input-field h-9 w-full"
            required
          />
        </div>
        
        <div>
          <label for="simulation-step-minutes" class="block text-sm font-medium mb-1">Step (minutes)</label>
          <input
            id="simulation-step-minutes"
            name="step_minutes"
            v-model.number="form.step_minutes"
            type="number"
            min="1"
            max="60"
            class="input-field h-9 w-full"
            required
          />
        </div>
        
        <div>
          <label for="simulation-recipe-id" class="block text-sm font-medium mb-1">Recipe ID (optional)</label>
          <input
            id="simulation-recipe-id"
            name="recipe_id"
            v-model.number="form.recipe_id"
            type="number"
            class="input-field h-9 w-full"
          />
        </div>
        
        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-sm font-medium mb-2">Initial State (optional)</div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label for="simulation-initial-ph" class="block text-xs text-[color:var(--text-muted)] mb-1">pH</label>
              <input
                id="simulation-initial-ph"
                name="initial_state_ph"
                v-model.number="form.initial_state.ph"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label for="simulation-initial-ec" class="block text-xs text-[color:var(--text-muted)] mb-1">EC</label>
              <input
                id="simulation-initial-ec"
                name="initial_state_ec"
                v-model.number="form.initial_state.ec"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label for="simulation-initial-temp-air" class="block text-xs text-[color:var(--text-muted)] mb-1">Temp Air (°C)</label>
              <input
                id="simulation-initial-temp-air"
                name="initial_state_temp_air"
                v-model.number="form.initial_state.temp_air"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label for="simulation-initial-temp-water" class="block text-xs text-[color:var(--text-muted)] mb-1">Temp Water (°C)</label>
              <input
                id="simulation-initial-temp-water"
                name="initial_state_temp_water"
                v-model.number="form.initial_state.temp_water"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div class="col-span-2">
              <label for="simulation-initial-humidity" class="block text-xs text-[color:var(--text-muted)] mb-1">Влажность (%)</label>
              <input
                id="simulation-initial-humidity"
                name="initial_state_humidity_air"
                v-model.number="form.initial_state.humidity_air"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
          </div>
        </div>
        
        <div v-if="loading" class="text-sm text-[color:var(--text-muted)]">
          Running simulation...
        </div>
        
        <div v-if="error" class="text-sm text-[color:var(--accent-red)]">
          {{ error }}
        </div>
        
        <div class="flex justify-end gap-2 pt-4 border-t border-[color:var(--border-muted)]">
          <Button type="button" variant="secondary" @click="$emit('close')">Cancel</Button>
          <Button type="submit" :disabled="loading">
            {{ loading ? 'Running...' : 'Run Simulation' }}
          </Button>
        </div>
      </form>
      
      <div v-if="results" class="mt-6 border-t border-[color:var(--border-muted)] pt-4" @click.stop>
        <div class="text-sm font-medium mb-3">Simulation Results</div>
        <div class="text-xs text-[color:var(--text-muted)] mb-2">
          Duration: {{ results.duration_hours }}h, Step: {{ results.step_minutes }}min
        </div>
        <div class="h-64">
          <ChartBase v-if="chartOption" :option="chartOption" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { logger } from '@/utils/logger'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useLoading } from '@/composables/useLoading'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useTheme } from '@/composables/useTheme'
import type { EChartsOption } from 'echarts'

interface Props {
  show?: boolean
  zoneId: number
  defaultRecipeId?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  defaultRecipeId: null,
})

const emit = defineEmits<{
  close: []
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)
const { theme } = useTheme()

interface SimulationForm {
  duration_hours: number
  step_minutes: number
  recipe_id: number | null
  initial_state: {
    ph: number | null
    ec: number | null
    temp_air: number | null
    temp_water: number | null
    humidity_air: number | null
  }
}

interface SimulationPoint {
  t: number
  ph: number
  ec: number
  temp_air: number
}

interface SimulationResults {
  duration_hours: number
  step_minutes: number
  points: SimulationPoint[]
}

const form = reactive<SimulationForm>({
  duration_hours: 72,
  step_minutes: 10,
  recipe_id: props.defaultRecipeId || null,
  initial_state: {
    ph: null,
    ec: null,
    temp_air: null,
    temp_water: null,
    humidity_air: null,
  },
})

const { loading, startLoading, stopLoading } = useLoading<boolean>(false)
const error = ref<string | null>(null)
const results = ref<SimulationResults | null>(null)

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const chartPalette = computed(() => {
  theme.value
  return {
    text: resolveCssColor('--text-muted', '#9ca3af'),
    textStrong: resolveCssColor('--text-primary', '#e5e7eb'),
    grid: resolveCssColor('--border-muted', '#374151'),
    ph: resolveCssColor('--accent-cyan', '#3b82f6'),
    ec: resolveCssColor('--accent-green', '#10b981'),
    temp: resolveCssColor('--accent-amber', '#f59e0b'),
  }
})

const chartOption = computed<EChartsOption | null>(() => {
  if (!results.value?.points) return null
  
  const points = results.value.points
  const phData = points.map(p => [p.t, p.ph])
  const ecData = points.map(p => [p.t, p.ec])
  const tempData = points.map(p => [p.t, p.temp_air])
  
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['pH', 'EC', 'Temp Air'],
      textStyle: { color: chartPalette.value.textStrong },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      name: 'Time (hours)',
      nameTextStyle: { color: chartPalette.value.text },
      axisLabel: { color: chartPalette.value.text },
      splitLine: { lineStyle: { color: chartPalette.value.grid } },
    },
    yAxis: [
      {
        type: 'value',
        name: 'pH / EC',
        nameTextStyle: { color: chartPalette.value.text },
        axisLabel: { color: chartPalette.value.text },
        splitLine: { lineStyle: { color: chartPalette.value.grid } },
      },
      {
        type: 'value',
        name: 'Temp (°C)',
        nameTextStyle: { color: chartPalette.value.text },
        axisLabel: { color: chartPalette.value.text },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'pH',
        type: 'line',
        data: phData,
        smooth: true,
        lineStyle: { color: chartPalette.value.ph },
        itemStyle: { color: chartPalette.value.ph },
      },
      {
        name: 'EC',
        type: 'line',
        data: ecData,
        smooth: true,
        lineStyle: { color: chartPalette.value.ec },
        itemStyle: { color: chartPalette.value.ec },
      },
      {
        name: 'Temp Air',
        type: 'line',
        yAxisIndex: 1,
        data: tempData,
        smooth: true,
        lineStyle: { color: chartPalette.value.temp },
        itemStyle: { color: chartPalette.value.temp },
      },
    ],
  }
})

async function onSubmit(): Promise<void> {
  startLoading()
  error.value = null
  results.value = null
  
  try {
    interface SimulationPayload {
      duration_hours: number
      step_minutes: number
      recipe_id?: number
      initial_state?: Partial<SimulationForm['initial_state']>
    }
    
    const payload: SimulationPayload = {
      duration_hours: form.duration_hours,
      step_minutes: form.step_minutes,
    }
    
    if (form.recipe_id) {
      payload.recipe_id = form.recipe_id
    }
    
    // Фильтруем initial_state, убирая null значения
    const initialState: Partial<SimulationForm['initial_state']> = {}
    if (form.initial_state.ph !== null) initialState.ph = form.initial_state.ph
    if (form.initial_state.ec !== null) initialState.ec = form.initial_state.ec
    if (form.initial_state.temp_air !== null) initialState.temp_air = form.initial_state.temp_air
    if (form.initial_state.temp_water !== null) initialState.temp_water = form.initial_state.temp_water
    if (form.initial_state.humidity_air !== null) initialState.humidity_air = form.initial_state.humidity_air
    
    if (Object.keys(initialState).length > 0) {
      payload.initial_state = initialState
    }
    
    const response = await api.post<{ status: string; data?: SimulationResults }>(
      `/zones/${props.zoneId}/simulate`,
      payload
    )
    
    if (response.data?.status === 'ok' && response.data?.data) {
      results.value = response.data.data
      showToast('Simulation completed successfully', 'success', TOAST_TIMEOUT.NORMAL)
    } else {
      error.value = 'Unexpected response format'
    }
  } catch (err) {
    logger.error('[ZoneSimulationModal] Simulation error:', err)
    const errorMsg = err instanceof Error ? err.message : 'Failed to run simulation'
    error.value = errorMsg
  } finally {
    stopLoading()
  }
}
</script>
