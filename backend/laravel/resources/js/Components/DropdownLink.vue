<script setup>
import { Link } from '@inertiajs/vue3';

defineProps({
    href: {
        type: String,
        required: true,
    },
});
</script>

<template>
  <Link
    :href="href"
    class="block w-full px-4 py-2 text-start text-sm leading-5 text-[color:var(--text-primary)] transition duration-150 ease-in-out hover:bg-[color:var(--bg-elevated)] focus:bg-[color:var(--bg-elevated)] focus:outline-none"
  >
    <slot></slot>
  </Link>
</template>
