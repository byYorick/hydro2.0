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

<script setup>
import { computed } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: 'Подтверждение',
  },
  message: {
    type: String,
    required: true,
  },
  confirmText: {
    type: String,
    default: 'Подтвердить',
  },
  cancelText: {
    type: String,
    default: 'Отмена',
  },
  confirmVariant: {
    type: String,
    default: 'primary',
    validator: (value) => ['primary', 'danger', 'warning', 'secondary'].includes(value),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  loadingText: {
    type: String,
    default: 'Загрузка...',
  },
})

defineEmits(['close', 'confirm'])
</script>

