<template>
  <Modal :open="open" :title="title" @close="$emit('close')">
    <div class="text-sm text-neutral-300">{{ message }}</div>
    <template #footer>
      <Button size="sm" variant="secondary" @click="$emit('close')">
        {{ cancelText }}
      </Button>
      <Button 
        size="sm" 
        :variant="confirmVariant"
        @click="$emit('confirm')"
        :disabled="loading"
      >
        {{ loading ? loadingText : confirmText }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'

type ButtonVariant = 'primary' | 'danger' | 'warning' | 'secondary'

interface Props {
  open?: boolean
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  confirmVariant?: ButtonVariant
  loading?: boolean
  loadingText?: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  title: 'Подтверждение',
  confirmText: 'Подтвердить',
  cancelText: 'Отмена',
  confirmVariant: 'primary',
  loading: false,
  loadingText: 'Загрузка...'
})

defineEmits<{
  close: []
  confirm: []
}>()
</script>

