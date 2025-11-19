<template>
  <div ref="el" :class="containerClass" :style="containerStyle"></div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import type { EChartsOption } from 'echarts'

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
let chart

onMounted(() => {
  if (!el.value) return
  
  chart = echarts.init(el.value, props.dark ? 'dark' : undefined, {
    renderer: 'canvas',
    useDirtyRect: false, // Отключаем для стабильности
  })
  
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
  
  // Улучшаем опции для предотвращения выхода за границы
  const safeOption = {
    ...props.option,
    grid: {
      left: props.option.grid?.left ?? 40,
      right: props.option.grid?.right ?? 16,
      top: props.option.grid?.top ?? 16,
      bottom: props.option.grid?.bottom ?? 32,
      containLabel: props.option.grid?.containLabel ?? false,
      ...(props.option.grid || {}), // Сохраняем все настройки grid из опций
    },
  }
  
  chart.setOption(safeOption)
  
  const onResize = () => {
    if (chart && el.value) {
      chart.resize()
    }
  }
  
  window.addEventListener('resize', onResize)
  
  // Используем ResizeObserver для более точного отслеживания изменений размера
  if (window.ResizeObserver && el.value) {
    const resizeObserver = new ResizeObserver(() => {
      onResize()
    })
    resizeObserver.observe(el.value)
    onBeforeUnmount(() => {
      resizeObserver.disconnect()
      window.removeEventListener('resize', onResize)
    })
  } else {
    onBeforeUnmount(() => window.removeEventListener('resize', onResize))
  }
})

watch(
  () => props.option,
  (opt) => {
    if (chart) {
      // Улучшаем опции для предотвращения выхода за границы
      const safeOption = {
        ...opt,
        grid: {
          left: opt.grid?.left ?? 40,
          right: opt.grid?.right ?? 16,
          top: opt.grid?.top ?? 16,
          bottom: opt.grid?.bottom ?? 32,
          containLabel: opt.grid?.containLabel ?? false,
          ...(opt.grid || {}), // Сохраняем все настройки grid из опций
        },
      }
      chart.setOption(safeOption, { notMerge: true })
    }
  },
  { deep: true }
)

onBeforeUnmount(() => {
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

