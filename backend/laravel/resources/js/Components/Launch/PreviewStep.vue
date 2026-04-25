<template>
  <section class="grid gap-4 items-start lg:[grid-template-columns:1.3fr_1fr]">
    <div class="flex flex-col gap-3">
      <ShellCard title="Сводка запуска">
        <template #actions>
          <Chip :tone="errors.length === 0 ? 'growth' : 'warn'">
            <template #icon>
              <span class="font-mono text-[11px]">{{ errors.length === 0 ? '✓' : '!' }}</span>
            </template>
            {{ errors.length === 0 ? 'готова' : `${errors.length} ошибок` }}
          </Chip>
        </template>

        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Stat
            label="Зона"
            :value="payloadPreview.zone_id ?? '—'"
            mono
          />
          <Stat
            label="Ревизия рецепта"
            :value="payloadPreview.recipe_revision_id ?? '—'"
            mono
          />
          <Stat
            label="Растение"
            :value="payloadPreview.plant_id ?? '—'"
            mono
          />
          <Stat
            label="Дата посадки"
            :value="formatPlanting(payloadPreview.planting_at)"
            mono
          />
          <Stat
            label="Метка партии"
            :value="payloadPreview.batch_label || '—'"
            mono
          />
          <Stat
            label="Заметки"
            :value="payloadPreview.notes ? `${(payloadPreview.notes as string).length} симв.` : '—'"
            mono
          />
        </div>
      </ShellCard>

      <ShellCard
        v-if="recipePhases.length"
        title="Фазы рецепта"
        :pad="false"
      >
        <RecipePhasesSummary :phases="recipePhases as never" />
      </ShellCard>

      <ShellCard title="Diff · zone.logic_profile">
        <template #actions>
          <Chip tone="brand">
            <span class="font-mono">overrides</span>
          </Chip>
        </template>
        <slot name="diff-preview"></slot>
      </ShellCard>
    </div>

    <aside class="flex flex-col gap-3 lg:sticky lg:top-[108px] lg:self-start">
      <ShellCard title="Readiness">
        <div
          v-if="errors.length === 0"
          class="flex items-center gap-2 text-sm text-growth"
        >
          <span class="font-mono">✓</span>
          <span>Все проверки пройдены — готово к запуску.</span>
        </div>
        <ul
          v-else
          class="flex flex-col gap-1.5 text-xs"
        >
          <li
            v-for="err in errors"
            :key="err.path"
            class="flex items-start gap-2 px-2 py-1.5 rounded-md bg-alert-soft text-alert"
          >
            <span class="font-mono shrink-0">×</span>
            <span class="flex-1 min-w-0">
              <span class="font-mono text-[11px] block break-all">{{ err.path || '(root)' }}</span>
              <span class="text-[var(--text-primary)]">{{ err.message }}</span>
            </span>
          </li>
        </ul>
      </ShellCard>

      <div
        class="rounded-md border border-brand bg-gradient-to-b from-[var(--bg-surface)] to-brand-soft p-4 flex flex-col gap-2.5"
      >
        <div
          class="text-[11px] font-bold uppercase tracking-widest text-brand-ink"
        >
          Запуск цикла
        </div>
        <div class="text-lg font-semibold leading-tight text-[var(--text-primary)]">
          <template v-if="errors.length === 0">
            Готово. Нажмите «Запустить цикл» в нижней панели.
          </template>
          <template v-else>
            Исправьте ошибки выше — затем кнопка станет активной.
          </template>
        </div>
      </div>

      <Hint :show="showHints">
        После «Запустить цикл» вызывается <span class="font-mono">POST /api/zones/{id}/grow-cycles</span>
        с overrides. AE3 создаёт grow cycle, инициализирует стартовую фазу
        и планирует первый полив через scheduler-dispatch.
      </Hint>
    </aside>
  </section>
</template>

<script setup lang="ts">
import type { GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch'
import RecipePhasesSummary from '@/Components/Launch/RecipePhasesSummary.vue'
import { Chip, Stat, Hint } from '@/Components/Shared/Primitives'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'

withDefaults(
  defineProps<{
    payloadPreview: Partial<GrowCycleLaunchPayload>
    errors: Array<{ path: string; message: string }>
    recipePhases?: unknown[]
  }>(),
  {
    payloadPreview: () => ({}),
    errors: () => [],
    recipePhases: () => [],
  },
)

const { showHints } = useLaunchPreferences()

function formatPlanting(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>
