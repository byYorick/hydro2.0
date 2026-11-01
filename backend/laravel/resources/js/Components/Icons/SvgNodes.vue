<template>
  <component
    :is="node.tag"
    v-for="(node, index) in nodes"
    :key="index"
    v-bind="svgNodeAttrs(node)"
  />
</template>

<script setup lang="ts">
import { svgNodeAttrs, type SvgNode } from './svgNode'

defineProps<{
  nodes: SvgNode[]
}>()
</script>
