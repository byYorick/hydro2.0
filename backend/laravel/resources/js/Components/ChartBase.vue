<template>
  <div
    ref="el"
    :class="containerClass"
    :style="containerStyle"
  ></div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import type { ECharts, EChartsOption } from 'echarts'

interface Props {
  option: EChartsOption
  dark?: boolean
  height?: string
  fullHeight?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  dark: true,
  height: '256px',
  fullHeight: false
})

const containerClass = computed(() => {
  // Используем overflow-hidden для canvas, но tooltip будет в body
  const base = 'w-full relative overflow-hidden'
  if (props.fullHeight) {
    return `${base} h-full`
  }
  return base
})

const containerStyle = computed(() => {
  if (props.fullHeight) {
    return {}
  }
  return { height: props.height }
})

const el = ref()
let chart: ECharts | undefined
let resizeObserver: ResizeObserver | undefined

const buildSafeOption = (option: EChartsOption): EChartsOption => {
  const gridOption = Array.isArray(option.grid) ? option.grid[0] : option.grid
  return {
    ...option,
    grid: {
      left: gridOption?.left ?? 40,
      right: gridOption?.right ?? 16,
      top: gridOption?.top ?? 16,
      bottom: gridOption?.bottom ?? 32,
      containLabel: gridOption?.containLabel ?? false,
      ...(gridOption || {}),
    },
  }
}

const initChart = (): void => {
  if (!el.value) {
    return
  }

  if (chart) {
    chart.dispose()
    chart = undefined
  }

  chart = echarts.init(el.value, props.dark ? 'dark' : undefined, {
    renderer: 'canvas',
    useDirtyRect: false,
  })

  chart.setOption(buildSafeOption(props.option))
}

const onResize = () => {
  if (chart && el.value) {
    chart.resize()
  }
}

onMounted(() => {
  if (!el.value) return

  initChart()

  // Настраиваем глобальные стили для tooltip (только один раз)
  if (!window.__echartsTooltipStyleAdded) {
    const tooltipStyle = document.createElement('style')
    tooltipStyle.id = 'echarts-tooltip-global-style'
    tooltipStyle.textContent = `
      .echarts-tooltip {
        z-index: 99999 !important;
        pointer-events: none !important;
        position: fixed !important;
      }
      .echarts-tooltip * {
        pointer-events: none !important;
      }
    `
    document.head.appendChild(tooltipStyle)
    window.__echartsTooltipStyleAdded = true
  }

  window.addEventListener('resize', onResize)

  // Используем ResizeObserver для более точного отслеживания изменений размера
  if (window.ResizeObserver && el.value) {
    resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(el.value)
  }
})

watch(
  () => props.option,
  (opt) => {
    if (chart) {
      chart.setOption(buildSafeOption(opt), { notMerge: false, lazyUpdate: false })
    }
  },
  { deep: true }
)

watch(
  () => props.dark,
  () => {
    initChart()
  }
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = undefined
  }
  if (chart) {
    chart.dispose()
    chart = undefined
  }
})
</script>

