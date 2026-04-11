<template>
  <div
    v-if="hasAnyData"
    class="space-y-1"
  >
    <div class="flex items-center justify-between text-[9px] uppercase tracking-wider text-[color:var(--text-dim)]">
      <span>Телеметрия · 24 часа</span>
      <div class="flex items-center gap-2 normal-case tracking-normal">
        <span
          v-for="item in legendSeries"
          :key="item.key"
          class="inline-flex items-center gap-1 text-[9px]"
        >
          <span
            class="inline-block h-0.5 w-2 rounded-full"
            :style="{ backgroundColor: item.color }"
          ></span>
          {{ item.label }}
        </span>
      </div>
    </div>
    <svg
      :width="width"
      :height="height"
      class="block max-w-full"
      :viewBox="`0 0 ${width} ${height}`"
    >
      <path
        v-for="item in renderedSeries"
        :key="item.key"
        :d="item.path"
        :stroke="item.color"
        :stroke-width="1.5"
        fill="none"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </div>
  <div
    v-else
    class="text-[9px] text-[color:var(--text-dim)]"
  >
    Телеметрия · нет данных за 24 часа
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface TelemetrySeries {
  key: 'ph' | 'ec' | 'temperature'
  label: string
  color: string
  data: number[] | null
}

interface Props {
  series: TelemetrySeries[]
  width?: number
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  width: 240,
  height: 34,
})

const nonEmpty = computed(() =>
  props.series.filter((s): s is TelemetrySeries & { data: number[] } =>
    Array.isArray(s.data) && s.data.length > 0
  )
)

const hasAnyData = computed(() => nonEmpty.value.length > 0)

const legendSeries = computed(() => nonEmpty.value.map((s) => ({
  key: s.key,
  label: s.label,
  color: s.color,
})))

/**
 * Каждая серия нормализуется независимо (свой min/max), чтобы на одном графике
 * можно было видеть форму колебаний pH/EC/T°C в одинаковой амплитуде.
 */
const renderedSeries = computed(() => {
  const padding = 2
  const chartWidth = props.width - padding * 2
  const chartHeight = props.height - padding * 2

  return nonEmpty.value.map((s) => {
    const values = s.data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v))
    if (values.length === 0) {
      return { key: s.key, color: s.color, path: '' }
    }
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1

    const points = values.map((value, index) => {
      const x = padding + (index / Math.max(1, values.length - 1)) * chartWidth
      const y = padding + chartHeight - ((value - min) / range) * chartHeight
      return `${x.toFixed(1)} ${y.toFixed(1)}`
    })

    return {
      key: s.key,
      color: s.color,
      path: points.length ? `M ${points.join(' L ')}` : '',
    }
  })
})
</script>
