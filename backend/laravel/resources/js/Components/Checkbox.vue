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
        type="checkbox"
        :value="value"
        v-model="proxyChecked"
        class="rounded border-gray-300 text-indigo-600 shadow-sm focus:ring-indigo-500"
    />
</template>
