<template>
  <Link
    :href="href"
    :prefetch="true"
    :class="[
      mobile
        ? 'flex flex-col items-center justify-center text-xs transition-colors px-2 py-2'
        : 'nav-link text-sm',
      mobile
        ? isActive ? 'text-white' : 'text-slate-400'
        : isActive ? 'nav-link--active' : ''
    ]"
  >
    <slot>
      {{ label }}
    </slot>
  </Link>
</template>

<script setup>
import { computed } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'

const props = defineProps({
  href: { type: String, required: true },
  label: { type: String, required: true },
  mobile: { type: Boolean, default: false },
})

const page = usePage()
const isActive = computed(() => {
  const current = page.url || '/'
  return current === props.href || (props.href !== '/' && current.startsWith(props.href))
})
</script>
