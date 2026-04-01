<template>
  <Card v-if="isActive">
    <div class="space-y-3">
      <div class="text-sm font-semibold">
        Управление
      </div>

      <!-- Основные действия -->
      <div class="flex flex-wrap gap-2">
        <Button
          v-if="status === 'RUNNING'"
          size="sm"
          variant="secondary"
          :disabled="busy"
          data-testid="zone-pause-btn"
          @click="$emit('pause')"
        >
          <LoadingState
            v-if="loading"
            loading
            size="sm"
            :container-class="'inline-flex mr-2'"
          />
          Приостановить
        </Button>

        <Button
          v-if="status === 'PAUSED'"
          size="sm"
          variant="secondary"
          :disabled="busy"
          data-testid="zone-resume-btn"
          @click="$emit('resume')"
        >
          <LoadingState
            v-if="loading"
            loading
            size="sm"
            :container-class="'inline-flex mr-2'"
          />
          Возобновить
        </Button>

        <Button
          v-if="isActive"
          size="sm"
          variant="outline"
          :disabled="busy"
          @click="$emit('next-phase')"
        >
          <LoadingState
            v-if="loadingNextPhase"
            loading
            size="sm"
            :container-class="'inline-flex mr-2'"
          />
          Следующая фаза
        </Button>
      </div>

      <!-- Деструктивные действия: завершение цикла -->
      <template v-if="isActive">
        <div class="pt-2 border-t border-[color:var(--border-muted)]">
          <div class="text-xs text-[color:var(--text-dim)] mb-2">
            Завершить цикл
          </div>
          <div class="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="success"
              :disabled="busy"
              data-testid="zone-harvest-btn"
              @click="$emit('harvest')"
            >
              <LoadingState
                v-if="loading"
                loading
                size="sm"
                :container-class="'inline-flex mr-2'"
              />
              Собрать урожай
            </Button>

            <Button
              size="sm"
              variant="danger"
              :disabled="busy"
              @click="$emit('abort')"
            >
              <LoadingState
                v-if="loading"
                loading
                size="sm"
                :container-class="'inline-flex mr-2'"
              />
              Аварийная остановка
            </Button>
          </div>
        </div>
      </template>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import LoadingState from '@/Components/LoadingState.vue'
import type { GrowCycleStatus } from '@/types/GrowCycle'

interface Props {
  status: GrowCycleStatus
  loading?: boolean
  loadingNextPhase?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  loadingNextPhase: false,
})

defineEmits<{
  pause: []
  resume: []
  harvest: []
  abort: []
  'next-phase': []
}>()

const isActive = computed(() => props.status === 'RUNNING' || props.status === 'PAUSED')
const busy = computed(() => props.loading || props.loadingNextPhase)
</script>
