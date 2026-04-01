<template>
  <Card>
    <div class="flex items-center justify-between mb-2">
      <div class="text-sm font-semibold">
        Рецепт
      </div>
      <Button
        v-if="canManageRecipe"
        size="sm"
        :variant="hasCycle ? 'secondary' : 'primary'"
        data-testid="recipe-attach-btn"
        @click="handleAction"
      >
        <span v-if="!hasCycle" data-testid="zone-start-btn">Запустить цикл</span>
        <span v-else-if="hasDetailedCycle">Сменить ревизию</span>
        <span v-else>Обновить данные</span>
      </Button>
    </div>

    <!-- Активный цикл с данными рецепта -->
    <template v-if="growCycle?.recipeRevision?.recipe">
      <div class="text-sm text-[color:var(--text-muted)]">
        <div class="font-semibold">
          {{ growCycle.recipeRevision.recipe.name }}
        </div>
        <div class="text-xs text-[color:var(--text-dim)]">
          Фаза {{ (growCycle.currentPhase?.phase_index ?? 0) + 1 }}
          из {{ growCycle.phases?.length || 0 }}
          <span v-if="growCycle.currentPhase?.name">
            — {{ growCycle.currentPhase.name }}
          </span>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <Badge
            :variant="cycleStatusVariant"
            class="text-[10px] px-2 py-0.5"
          >
            {{ cycleStatusLabel }}
          </Badge>
          <span
            v-if="phaseTimeLeftLabel"
            class="text-[11px] text-[color:var(--text-dim)]"
          >
            {{ phaseTimeLeftLabel }}
          </span>
        </div>
      </div>
    </template>

    <!-- Цикл активен, но данные фаз ещё не синхронизированы -->
    <template v-else-if="hasCycle">
      <div class="space-y-2">
        <div class="text-sm text-[color:var(--text-dim)]">
          Цикл уже активен, но данные фаз ещё не синхронизированы
        </div>
        <div class="text-xs text-[color:var(--text-dim)]">
          Нажмите «Обновить данные», чтобы подтянуть активный цикл, фазы и таргеты.
        </div>
      </div>
    </template>

    <!-- Нет активного цикла -->
    <template v-else>
      <div class="space-y-2">
        <div class="text-sm text-[color:var(--text-dim)]">
          Цикл выращивания не запущен
        </div>
        <div
          v-if="canManageRecipe"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Запустите цикл выращивания, чтобы применить рецепт и отслеживать фазы
        </div>
      </div>
    </template>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { GrowCycle } from '@/types/GrowCycle'

interface Props {
  growCycle: GrowCycle | null | undefined
  /** true если зона RUNNING/PAUSED, но growCycle ещё не загружен */
  zoneHasCycle: boolean
  cycleStatusLabel: string
  cycleStatusVariant: BadgeVariant
  phaseTimeLeftLabel: string
  canManageRecipe: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'run-cycle'): void
  (e: 'change-recipe'): void
  (e: 'refresh-cycle'): void
}>()

const hasDetailedCycle = computed(() => Boolean(props.growCycle))
const hasCycle = computed(() => hasDetailedCycle.value || props.zoneHasCycle)

function handleAction(): void {
  if (!hasCycle.value) {
    emit('run-cycle')
    return
  }
  if (hasDetailedCycle.value) {
    emit('change-recipe')
    return
  }
  emit('refresh-cycle')
}
</script>
