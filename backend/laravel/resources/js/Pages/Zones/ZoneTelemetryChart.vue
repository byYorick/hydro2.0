<template>
  <Card>
    <div class="flex items-center justify-between mb-2">
      <div class="text-sm font-semibold">{{ title }}</div>
      <div class="flex gap-1">
        <Button 
          size="sm" 
          :variant="timeRange === '1H' ? 'default' : 'secondary'" 
          @click="setRange('1H')"
        >
          1H
        </Button>
        <Button 
          size="sm" 
          :variant="timeRange === '24H' ? 'default' : 'secondary'" 
          @click="setRange('24H')"
        >
          24H
        </Button>
        <Button 
          size="sm" 
          :variant="timeRange === '7D' ? 'default' : 'secondary'" 
          @click="setRange('7D')"
        >
          7D
        </Button>
        <Button 
          size="sm" 
          :variant="timeRange === '30D' ? 'default' : 'secondary'" 
          @click="setRange('30D')"
        >
          30D
        </Button>
        <Button 
          size="sm" 
          :variant="timeRange === 'ALL' ? 'default' : 'secondary'" 
          @click="setRange('ALL')"
        >
          ALL
        </Button>
      </div>
    </div>
    <ChartBase :option="option" />
  </Card>
</template>

<script setup>
import { computed, watch } from 'vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'

const props = defineProps({
  title: { type: String, required: true },
  seriesName: { type: String, default: 'value' },
  data: { type: Array, default: () => [] }, // [{ts, value}]
  timeRange: { type: String, default: '24H' },
})

const emit = defineEmits(['time-range-change'])

const setRange = (r) => {
  emit('time-range-change', r)
}

const option = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 16, bottom: 32 },
  xAxis: {
    type: 'time',
    axisLabel: { color: '#9ca3af' },
    axisLine: { lineStyle: { color: '#374151' } },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#9ca3af' },
    splitLine: { lineStyle: { color: '#1f2937' } },
  },
  series: [
    {
      name: props.seriesName,
      type: 'line',
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2 },
      data: props.data.map(p => [p.ts, p.value]),
    },
  ],
}))
</script>

