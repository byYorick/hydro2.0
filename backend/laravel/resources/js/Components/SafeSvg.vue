<template>
  <svg
    v-if="!bare"
    :class="svgClass"
    :viewBox="viewBox"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <component
      :is="node.tag"
      v-for="(node, index) in nodes"
      :key="index"
      v-bind="node.attrs"
    />
  </svg>
  <template v-else>
    <component
      :is="node.tag"
      v-for="(node, index) in nodes"
      :key="index"
      v-bind="node.attrs"
    />
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  markup: string
  viewBox?: string
  svgClass?: string
  bare?: boolean
}>(), {
  viewBox: '0 0 24 24',
  svgClass: '',
  bare: false,
})

const ALLOWED_TAGS = new Set(['path', 'circle', 'rect', 'polyline', 'line', 'polygon', 'ellipse'])
const ALLOWED_ATTRS = new Set([
  'd', 'cx', 'cy', 'r', 'x', 'y', 'width', 'height', 'rx', 'ry',
  'points', 'x1', 'y1', 'x2', 'y2', 'fill', 'stroke', 'stroke-width',
])

function parseMarkup(markup: string): Array<{ tag: string; attrs: Record<string, string> }> {
  let body = markup.trim()
  const wrapped = body.match(/^<svg\b[^>]*>([\s\S]*)<\/svg>$/i)
  if (wrapped?.[1]) {
    body = wrapped[1]
  }
  const nodes: Array<{ tag: string; attrs: Record<string, string> }> = []
  const tagRe = /<(\w+)\b([^>]*)\/?>/g
  let match: RegExpExecArray | null
  while ((match = tagRe.exec(body))) {
    const tag = match[1].toLowerCase()
    if (!ALLOWED_TAGS.has(tag)) {
      continue
    }
    const attrs: Record<string, string> = {}
    const attrRe = /([\w:-]+)="([^"]*)"/g
    let attr: RegExpExecArray | null
    while ((attr = attrRe.exec(match[2]))) {
      const key = attr[1].toLowerCase()
      if (ALLOWED_ATTRS.has(key)) {
        attrs[key] = attr[2]
      }
    }
    nodes.push({ tag, attrs })
  }
  return nodes
}

const nodes = computed(() => parseMarkup(props.markup))
</script>
