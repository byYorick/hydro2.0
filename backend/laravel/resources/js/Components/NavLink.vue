<template>
  <Link
    :href="href"
    :prefetch="true"
    class="block rounded-md px-3 py-2 text-sm transition-colors"
    :class="isActive ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-300 hover:bg-neutral-850 hover:text-neutral-100'"
  >
    {{ label }}
  </Link>
</template>

<script setup>
import { computed } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'

const props = defineProps({
  href: { type: String, required: true },
  label: { type: String, required: true },
})

const page = usePage()
const isActive = computed(() => {
  const current = page.url || '/'
  return current === props.href || (props.href !== '/' && current.startsWith(props.href))
})
</script>
