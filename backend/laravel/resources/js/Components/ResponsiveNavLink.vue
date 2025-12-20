<script setup>
import { computed } from 'vue';
import { Link } from '@inertiajs/vue3';

const props = defineProps({
    href: {
        type: String,
        required: true,
    },
    active: {
        type: Boolean,
    },
});

const classes = computed(() =>
    props.active
        ? 'block w-full ps-3 pe-4 py-2 border-l-4 border-[color:var(--accent-green)] text-start text-base font-medium text-[color:var(--text-primary)] bg-[color:var(--badge-success-bg)] focus:outline-none focus:text-[color:var(--text-primary)] focus:bg-[color:var(--badge-success-bg)] focus:border-[color:var(--accent-green)] transition duration-150 ease-in-out'
        : 'block w-full ps-3 pe-4 py-2 border-l-4 border-transparent text-start text-base font-medium text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)] hover:border-[color:var(--border-strong)] focus:outline-none focus:text-[color:var(--text-primary)] focus:bg-[color:var(--bg-elevated)] focus:border-[color:var(--border-strong)] transition duration-150 ease-in-out',
);
</script>

<template>
    <Link :href="href" :class="classes">
        <slot />
    </Link>
</template>
