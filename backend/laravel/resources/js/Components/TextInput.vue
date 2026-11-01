<script setup lang="ts">
import { ref } from 'vue'
import TextField from '@/Components/TextField.vue'

defineOptions({ inheritAttrs: false })

const model = defineModel<string>({ required: true })
const field = ref<{ focus: () => void } | null>(null)

defineExpose({ focus: () => field.value?.focus() })
</script>

<template>
  <TextField
    ref="field"
    v-model="model"
    class="w-full"
    v-bind="$attrs"
  />
</template>
