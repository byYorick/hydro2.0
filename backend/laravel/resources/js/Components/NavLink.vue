<template>
  <Link
    :href="href"
    :prefetch="true"
    :class="[
      mobile 
        ? 'flex flex-col items-center justify-center text-xs transition-colors'
        : 'block rounded-md px-3 py-2 text-sm transition-colors',
      mobile
        ? isActive ? 'text-neutral-100' : 'text-neutral-400'
        : isActive ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-300 hover:bg-neutral-850 hover:text-neutral-100'
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
