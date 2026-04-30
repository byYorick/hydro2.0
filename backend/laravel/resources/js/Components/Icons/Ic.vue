<template>
  <svg
    :width="resolvedSize"
    :height="resolvedSize"
    viewBox="0 0 16 16"
    :fill="def.fill ?? 'none'"
    :stroke="def.fill === 'currentColor' ? undefined : 'currentColor'"
    :stroke-width="def.strokeWidth ?? 1.5"
    :stroke-linecap="def.strokeLinecap ?? 'round'"
    :stroke-linejoin="def.strokeLinejoin ?? 'round'"
    aria-hidden="true"
  >
    <!-- eslint-disable-next-line vue/no-v-html -->
    <g v-html="def.body" />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * Hydroflow iconset — 19 monochrome 16px stroke icons
 * (mirror `hydroflow/icons.jsx`). Используются через
 * `<Ic name="check" />`, `<Ic name="drop" size="lg" />`.
 *
 * Size: 'sm' = 12px, 'md' = 14px (default), 'lg' = 16px, 'xl' = 20px.
 * stroke берётся из currentColor, поэтому управление цветом
 * через `class="text-brand"` или style="color: …".
 */
export type IcName =
  | 'check' | 'x' | 'plus' | 'chev' | 'chevDown'
  | 'info' | 'warn' | 'play' | 'drop' | 'leaf'
  | 'chip' | 'gh' | 'grid' | 'beaker' | 'wave'
  | 'zap' | 'dot' | 'edit' | 'reload' | 'lock' | 'bookmark'

interface IconDef {
  body: string
  fill?: 'none' | 'currentColor'
  strokeWidth?: number
  strokeLinecap?: 'round' | 'butt'
  strokeLinejoin?: 'round' | 'miter'
}

const ICONS: Record<IcName, IconDef> = {
  check:    { body: '<path d="M3 8.5l3 3 7-7"/>', strokeWidth: 1.6 },
  x:        { body: '<path d="M4 4l8 8M12 4l-8 8"/>', strokeWidth: 1.6 },
  plus:     { body: '<path d="M8 3v10M3 8h10"/>', strokeWidth: 1.6 },
  chev:     { body: '<path d="M6 4l4 4-4 4"/>', strokeWidth: 1.6 },
  chevDown: { body: '<path d="M4 6l4 4 4-4"/>', strokeWidth: 1.6 },
  info:     { body: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 5.2v.2"/>' },
  warn:     { body: '<path d="M8 2l6.5 11.5h-13z"/><path d="M8 7v3.5M8 12v.3"/>' },
  play:     { body: '<path d="M4 3l9 5-9 5z"/>', fill: 'currentColor' },
  drop:     { body: '<path d="M8 2c2 3 5 5.5 5 8a5 5 0 01-10 0c0-2.5 3-5 5-8z"/>' },
  leaf:     { body: '<path d="M3 13s0-7 5-9c2.5-1 5 0 5 0s1 7-4 9-6 0-6 0z"/><path d="M3 13l7-7"/>' },
  chip:     { body: '<rect x="4" y="4" width="8" height="8" rx="1"/><path d="M6 2v2M10 2v2M6 12v2M10 12v2M2 6h2M2 10h2M12 6h2M12 10h2"/>', strokeWidth: 1.4 },
  gh:       { body: '<path d="M2 13V7l6-4 6 4v6z"/><path d="M6 13V9h4v4"/>', strokeWidth: 1.4 },
  grid:     { body: '<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/>', strokeWidth: 1.4 },
  beaker:   { body: '<path d="M6 2v5L3 13a1.5 1.5 0 001.3 2h7.4A1.5 1.5 0 0013 13L10 7V2"/><path d="M5 2h6"/>', strokeWidth: 1.4 },
  wave:     { body: '<path d="M2 9c1.5-2 3-2 4 0s2.5 2 4 0 2.5-2 4 0"/>', strokeWidth: 1.4 },
  zap:      { body: '<path d="M9 2l-5 8h4l-1 4 5-8H8z"/>', strokeWidth: 1.4 },
  dot:      { body: '<circle cx="8" cy="8" r="3"/>', fill: 'currentColor' },
  edit:     { body: '<path d="M3 13l.5-3L11 2.5l2.5 2.5L6 12.5z"/>', strokeWidth: 1.4 },
  reload:   { body: '<path d="M13 8a5 5 0 11-1.5-3.5L13 6"/><path d="M13 3v3h-3"/>', strokeWidth: 1.4 },
  lock:     { body: '<rect x="3.5" y="7.5" width="9" height="6" rx="1"/><path d="M5.5 7.5V5.5a2.5 2.5 0 015 0v2"/>', strokeWidth: 1.4 },
  bookmark: { body: '<path d="M4 2h8v12l-4-3-4 3z"/>', strokeWidth: 1.4 },
}

const SIZE_MAP: Record<string, number> = { sm: 12, md: 14, lg: 16, xl: 20 }

const props = withDefaults(
  defineProps<{
    name: IcName
    size?: 'sm' | 'md' | 'lg' | 'xl' | number
  }>(),
  { size: 'md' },
)

const def = computed<IconDef>(() => ICONS[props.name])

const resolvedSize = computed(() =>
  typeof props.size === 'number' ? props.size : SIZE_MAP[props.size] ?? 14,
)
</script>
