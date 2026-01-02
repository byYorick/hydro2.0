<script setup lang="ts">
import { computed } from 'vue';

interface Props {
    checked: boolean | unknown[]
    value?: unknown
}

const props = defineProps<Props>();

const emit = defineEmits<{
    'update:checked': [value: boolean | unknown[]]
}>();

const proxyChecked = computed({
    get() {
        return props.checked;
    },

    set(val: boolean | unknown[]) {
        emit('update:checked', val);
    },
});
</script>

<template>
  <input
    v-model="proxyChecked"
    type="checkbox"
    :value="value"
    class="h-4 w-4 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--accent-green)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--focus-ring)]"
  />
</template>
