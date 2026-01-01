<template>
  <EnhancedToast
    :toasts="toasts"
    @close="handleClose"
    @action="handleAction"
  />
</template>

<script setup lang="ts">
import { useToast } from '@/composables/useToast'
import EnhancedToast from './EnhancedToast.vue'

const { toasts, removeToast } = useToast()

function handleClose(id: number) {
  removeToast(id)
}

function handleAction(_id: number, action: { handler: () => void }) {
  action.handler()
  // Можно автоматически закрыть toast после действия
  // removeToast(id)
}
</script>

