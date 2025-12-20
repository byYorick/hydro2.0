<script setup>
import ApplicationLogo from '@/Components/ApplicationLogo.vue';
import { Link } from '@inertiajs/vue3';
</script>

<template>
    <div
        class="flex min-h-screen flex-col items-center bg-[color:var(--bg-main)] pt-6 text-[color:var(--text-primary)] sm:justify-center sm:pt-0"
    >
        <div>
            <Link href="/">
                <ApplicationLogo class="h-20 w-20 fill-current text-[color:var(--accent-green)]" />
            </Link>
        </div>

        <div
            class="mt-6 w-full overflow-hidden bg-[color:var(--bg-surface)] px-6 py-4 shadow-[var(--shadow-card)] sm:max-w-md sm:rounded-lg border border-[color:var(--border-muted)]"
        >
            <slot />
        </div>
    </div>
</template>
