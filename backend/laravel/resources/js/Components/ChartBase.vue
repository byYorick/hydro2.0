<template>
  <div ref="el" class="w-full h-64"></div>
</template>

<script setup>
import * as echarts from 'echarts'
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  option: { type: Object, required: true },
  dark: { type: Boolean, default: true },
})

const el = ref()
let chart

onMounted(() => {
  chart = echarts.init(el.value, props.dark ? 'dark' : undefined)
  chart.setOption(props.option)
  const onResize = () => chart && chart.resize()
  window.addEventListener('resize', onResize)
  onBeforeUnmount(() => window.removeEventListener('resize', onResize))
})

watch(
  () => props.option,
  (opt) => { chart && chart.setOption(opt, { notMerge: true }) },
  { deep: true }
)

onBeforeUnmount(() => {
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

