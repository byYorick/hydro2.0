<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center">
    <div class="absolute inset-0 bg-black/70" @click="$emit('close')"></div>
    <div class="relative w-full max-w-2xl rounded-xl border border-neutral-800 bg-neutral-925 p-6 max-h-[90vh] overflow-y-auto" @click.stop>
      <h2 class="text-lg font-semibold mb-4">Digital Twin Simulation</h2>
      
      <form @submit.prevent="onSubmit" class="space-y-4" @click.stop>
        <div>
          <label class="block text-sm font-medium mb-1">Duration (hours)</label>
          <input
            v-model.number="form.duration_hours"
            type="number"
            min="1"
            max="720"
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            required
          />
        </div>
        
        <div>
          <label class="block text-sm font-medium mb-1">Step (minutes)</label>
          <input
            v-model.number="form.step_minutes"
            type="number"
            min="1"
            max="60"
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            required
          />
        </div>
        
        <div>
          <label class="block text-sm font-medium mb-1">Recipe ID (optional)</label>
          <input
            v-model.number="form.recipe_id"
            type="number"
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
          />
        </div>
        
        <div class="border-t border-neutral-800 pt-4">
          <div class="text-sm font-medium mb-2">Initial State (optional)</div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-neutral-400 mb-1">pH</label>
              <input
                v-model.number="form.initial_state.ph"
                type="number"
                step="0.1"
                class="w-full h-8 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">EC</label>
              <input
                v-model.number="form.initial_state.ec"
                type="number"
                step="0.1"
                class="w-full h-8 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Temp Air (°C)</label>
              <input
                v-model.number="form.initial_state.temp_air"
                type="number"
                step="0.1"
                class="w-full h-8 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Temp Water (°C)</label>
              <input
                v-model.number="form.initial_state.temp_water"
                type="number"
                step="0.1"
                class="w-full h-8 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
              />
            </div>
            <div class="col-span-2">
              <label class="block text-xs text-neutral-400 mb-1">Humidity (%)</label>
              <input
                v-model.number="form.initial_state.humidity_air"
                type="number"
                step="0.1"
                class="w-full h-8 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
              />
            </div>
          </div>
        </div>
        
        <div v-if="loading" class="text-sm text-neutral-400">
          Running simulation...
        </div>
        
        <div v-if="error" class="text-sm text-red-400">
          {{ error }}
        </div>
        
        <div class="flex justify-end gap-2 pt-4 border-t border-neutral-800">
          <Button type="button" variant="secondary" @click="$emit('close')">Cancel</Button>
          <Button type="submit" :disabled="loading">
            {{ loading ? 'Running...' : 'Run Simulation' }}
          </Button>
        </div>
      </form>
      
      <div v-if="results" class="mt-6 border-t border-neutral-800 pt-4" @click.stop>
        <div class="text-sm font-medium mb-3">Simulation Results</div>
        <div class="text-xs text-neutral-400 mb-2">
          Duration: {{ results.duration_hours }}h, Step: {{ results.step_minutes }}min
        </div>
        <div class="h-64">
          <ChartBase v-if="chartOption" :option="chartOption" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'
import axios from 'axios'

const props = defineProps({
  show: { type: Boolean, default: false },
  zoneId: { type: Number, required: true },
  defaultRecipeId: { type: Number, default: null },
})

const emit = defineEmits(['close'])

const form = reactive({
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

const loading = ref(false)
const error = ref(null)
const results = ref(null)

const chartOption = computed(() => {
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
      textStyle: { color: '#d1d5db' },
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
      nameTextStyle: { color: '#9ca3af' },
      axisLabel: { color: '#9ca3af' },
      splitLine: { lineStyle: { color: '#374151' } },
    },
    yAxis: [
      {
        type: 'value',
        name: 'pH / EC',
        nameTextStyle: { color: '#9ca3af' },
        axisLabel: { color: '#9ca3af' },
        splitLine: { lineStyle: { color: '#374151' } },
      },
      {
        type: 'value',
        name: 'Temp (°C)',
        nameTextStyle: { color: '#9ca3af' },
        axisLabel: { color: '#9ca3af' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'pH',
        type: 'line',
        data: phData,
        smooth: true,
        lineStyle: { color: '#3b82f6' },
        itemStyle: { color: '#3b82f6' },
      },
      {
        name: 'EC',
        type: 'line',
        data: ecData,
        smooth: true,
        lineStyle: { color: '#10b981' },
        itemStyle: { color: '#10b981' },
      },
      {
        name: 'Temp Air',
        type: 'line',
        yAxisIndex: 1,
        data: tempData,
        smooth: true,
        lineStyle: { color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
      },
    ],
  }
})

async function onSubmit() {
  loading.value = true
  error.value = null
  results.value = null
  
  try {
    const payload = {
      duration_hours: form.duration_hours,
      step_minutes: form.step_minutes,
    }
    
    if (form.recipe_id) {
      payload.recipe_id = form.recipe_id
    }
    
    // Фильтруем initial_state, убирая null значения
    const initialState = {}
    if (form.initial_state.ph !== null) initialState.ph = form.initial_state.ph
    if (form.initial_state.ec !== null) initialState.ec = form.initial_state.ec
    if (form.initial_state.temp_air !== null) initialState.temp_air = form.initial_state.temp_air
    if (form.initial_state.temp_water !== null) initialState.temp_water = form.initial_state.temp_water
    if (form.initial_state.humidity_air !== null) initialState.humidity_air = form.initial_state.humidity_air
    
    if (Object.keys(initialState).length > 0) {
      payload.initial_state = initialState
    }
    
    const response = await axios.post(
      `/api/zones/${props.zoneId}/simulate`,
      payload,
      {
        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }
    )
    
    if (response.data?.status === 'ok' && response.data?.data) {
      results.value = response.data.data
    } else {
      error.value = 'Unexpected response format'
    }
  } catch (err) {
    console.error('Simulation error:', err)
    error.value = err.response?.data?.message || err.message || 'Failed to run simulation'
  } finally {
    loading.value = false
  }
}
</script>

