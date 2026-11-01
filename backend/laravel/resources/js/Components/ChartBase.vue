<template>
  <div
    ref="el"
    :class="containerClass"
    :style="containerStyle"
    :aria-label="label || undefined"
  ></div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import type { ECharts, EChartsOption } from 'echarts'
import { useTheme } from '@/composables/useTheme'
import { mergeChartOption } from '@/theme/chartTheme'

interface Props {
  option: EChartsOption
  dark?: boolean
  height?: string
  fullHeight?: boolean
  label?: string
}

const props = withDefaults(defineProps<Props>(), {
  dark: true,
  height: '256px',
  fullHeight: false,
  label: '',
})

const { theme } = useTheme()

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
  const themed = mergeChartOption(option)
  const gridOption = Array.isArray(themed.grid) ? themed.grid[0] : themed.grid
  return {
    ...themed,
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

  // Цвета берутся из CSS-переменных темы, а не из встроенной темы ECharts `dark`.
  chart = echarts.init(el.value, undefined, {
    renderer: 'canvas',
    useDirtyRect: false,
  })

  chart.setOption(buildSafeOption(props.option))
}

const onResize = () => {
  // rAF снимает ложные «ResizeObserver loop» при каскаде resize → setOption
  requestAnimationFrame(() => {
    if (chart && el.value) {
      chart.resize()
    }
  })
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

watch(theme, () => {
  if (chart) {
    chart.setOption(buildSafeOption(props.option), { notMerge: false, lazyUpdate: false })
  }
})

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

