<template>
  <div
    v-if="showEngage || showRelease"
    class="flex flex-col items-stretch gap-1.5"
    data-testid="zone-estop-control"
  >
    <Button
      v-if="showEngage"
      variant="danger"
      size="lg"
      type="button"
      class="w-full font-semibold ring-2 ring-[color:var(--status-critical)] sm:w-auto"
      data-testid="zone-estop-engage"
      :disabled="busy"
      @click="confirmOpen = true"
    >
      Аварийная остановка
    </Button>
    <Button
      v-if="showRelease"
      variant="outline"
      size="md"
      type="button"
      class="w-full sm:w-auto"
      data-testid="zone-estop-release"
      :disabled="busy"
      @click="openRelease"
    >
      Снять аварийную остановку
    </Button>
    <p
      v-if="solutionLabel"
      class="text-xs text-[color:var(--text-muted)]"
      data-testid="zone-estop-solution"
    >
      {{ solutionLabel }}
    </p>

    <Modal
      :open="confirmOpen"
      title="Аварийная остановка"
      data-testid="zone-estop-confirm-modal"
      @close="confirmOpen = false"
    >
      <p class="text-sm text-[color:var(--text-primary)]">
        Включающие команды зоны будут заблокированы. Насосы и реле останутся выключенными, пока остановку не снимут.
      </p>
      <template #footer>
        <Button
          variant="danger"
          size="sm"
          type="button"
          data-testid="zone-estop-confirm"
          :disabled="busy"
          @click="confirmEngage"
        >
          Остановить
        </Button>
      </template>
    </Modal>

    <Modal
      :open="releaseOpen"
      title="Снять аварийную остановку"
      data-testid="zone-estop-release-modal"
      @close="releaseOpen = false"
    >
      <div class="space-y-2">
        <p class="text-sm text-[color:var(--text-primary)]">
          Укажите, почему остановку можно снять. Насосы и реле сами не включатся.
        </p>
        <label class="block text-sm text-[color:var(--text-primary)]">
          Причина
          <textarea
            v-model="reason"
            class="input-field mt-1 min-h-24 w-full"
            maxlength="500"
            data-testid="zone-estop-release-reason"
            @input="reasonTouched = true"
          ></textarea>
        </label>
        <p
          v-if="reasonTouched && !reasonValid"
          class="text-xs text-[color:var(--status-critical)]"
          data-testid="zone-estop-release-error"
        >
          Укажите причину не короче 3 символов.
        </p>
      </div>
      <template #footer>
        <Button
          variant="danger"
          size="sm"
          type="button"
          data-testid="zone-estop-release-confirm"
          :disabled="busy || !reasonValid"
          @click="confirmRelease"
        >
          Снять остановку
        </Button>
      </template>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'

interface Props {
  active: boolean
  busy?: boolean
  canEngage: boolean
  canRelease: boolean
  solutionLabel?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  busy: false,
  solutionLabel: null,
})

const emit = defineEmits<{
  engage: []
  release: [reason: string]
}>()

const confirmOpen = ref(false)
const releaseOpen = ref(false)
const reason = ref('')
const reasonTouched = ref(false)

const showEngage = computed(() => props.canEngage && !props.active)
const showRelease = computed(() => props.canRelease && props.active)
const reasonValid = computed(() => reason.value.trim().length >= 3)

function confirmEngage(): void {
  confirmOpen.value = false
  emit('engage')
}

function openRelease(): void {
  reason.value = ''
  reasonTouched.value = false
  releaseOpen.value = true
}

function confirmRelease(): void {
  reasonTouched.value = true
  if (!reasonValid.value) return
  const nextReason = reason.value.trim()
  releaseOpen.value = false
  emit('release', nextReason)
}
</script>
