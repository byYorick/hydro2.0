<template>
  <section class="grid gap-4 items-start lg:[grid-template-columns:1fr_360px]">
    <div class="flex flex-col gap-3">
      <ShellCard title="Растение">
        <template #actions>
          <Button
            size="sm"
            :variant="creatingPlantOpen ? 'primary' : 'secondary'"
            @click="creatingPlantOpen = !creatingPlantOpen"
          >
            + Создать
          </Button>
        </template>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field
            label="Растение"
            required
          >
            <Select
              :model-value="plantId ?? ''"
              :options="plantOptions"
              placeholder="— выберите —"
              @update:model-value="(v: string) => onPlantSelect(v ? Number(v) : null)"
            />
          </Field>
          <Field
            v-if="errors['plant_id']"
            label=" "
            :error="errors['plant_id']"
          >
            <span></span>
          </Field>

          <div
            v-if="creatingPlantOpen"
            class="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-[var(--border-muted)]"
          >
            <Field
              label="Название"
              required
            >
              <TextInput
                v-model="newPlantName"
                placeholder="Томат"
                maxlength="255"
              />
            </Field>
            <Field label="Сорт">
              <TextInput
                v-model="newPlantVariety"
                placeholder="Cherry"
                maxlength="255"
              />
            </Field>
            <div class="md:col-span-2 flex justify-end gap-2">
              <Button
                size="sm"
                variant="secondary"
                @click="creatingPlantOpen = false"
              >
                Отмена
              </Button>
              <Button
                size="sm"
                variant="primary"
                :disabled="!newPlantName.trim() || creatingPlant"
                @click="createPlant"
              >
                {{ creatingPlant ? 'Создание…' : 'Создать растение' }}
              </Button>
            </div>
          </div>
        </div>
      </ShellCard>

      <ShellCard
        v-if="plantId"
        title="Рецепт"
      >
        <template #actions>
          <Button
            size="sm"
            variant="secondary"
            @click="$emit('refresh-recipes')"
          >
            ↻ Обновить
          </Button>
          <Button
            size="sm"
            variant="primary"
            @click="openCreateRecipeInNewTab"
          >
            + Создать (новая вкладка)
          </Button>
        </template>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field
            label="Рецепт и ревизия"
            required
          >
            <Select
              :model-value="selectedRecipeId ?? ''"
              :options="recipeOptions"
              :placeholder="filteredRecipes.length ? '— выберите —' : '— нет рецептов —'"
              :disabled="filteredRecipes.length === 0"
              @update:model-value="(v: string) => onRecipeSelect(v ? Number(v) : null)"
            />
          </Field>
          <Field label="Доступная ревизия">
            <Stat
              :label="''"
              :value="selectedRecipeRevisionLabel"
              :tone="selectedRecipe?.latest_published_revision_id ? 'growth' : 'default'"
              mono
            />
          </Field>

          <Field
            v-if="errors['recipe_revision_id']"
            label=" "
            :error="errors['recipe_revision_id']"
          >
            <span></span>
          </Field>
        </div>
      </ShellCard>

      <ShellCard
        v-if="plantId && selectedRecipeId"
        title="Дата и партия"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field
            label="Дата и время посадки"
            required
          >
            <div class="flex gap-2">
              <input
                type="datetime-local"
                class="block w-full h-8 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none focus-visible:ring-2 focus-visible:ring-brand"
                :value="plantingLocalValue"
                @input="onPlantingChange(($event.target as HTMLInputElement).value)"
              />
              <Button
                size="sm"
                variant="secondary"
                @click="setPlantingToNow"
              >
                Сейчас
              </Button>
            </div>
          </Field>
          <Field
            label="Метка партии"
            hint="например batch-2026-04"
          >
            <TextInput
              :model-value="batchLabel ?? ''"
              placeholder="batch-2026-04"
              maxlength="100"
              @update:model-value="onBatchChange"
            />
          </Field>
          <Field
            label="Заметки"
            class="md:col-span-2"
          >
            <textarea
              class="block w-full min-h-[72px] rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-brand resize-y"
              :value="notes ?? ''"
              maxlength="2000"
              rows="3"
              @input="onNotesChange(($event.target as HTMLTextAreaElement).value)"
            ></textarea>
          </Field>
        </div>
      </ShellCard>
    </div>

    <aside class="flex flex-col gap-3 lg:sticky lg:top-[108px] lg:self-start">
      <Hint :show="showHints">
        Целевые pH/EC, система выращивания и расписание берутся из <b>рецепта</b>.
        На шаге «Автоматика» они read-only — чтобы изменить, отредактируйте
        рецепт. PID на шаге «Калибровка» инициализируется из целей выбранной
        фазы.
      </Hint>

      <ShellCard title="Активная ревизия">
        <KV
          :rows="[
            ['recipe id', selectedRecipe?.id ?? '—'],
            ['ревизия', recipeRevisionId ? `r${recipeRevisionId}` : '—'],
            ['всего фаз', recipePhases.length || '—'],
          ]"
        />
      </ShellCard>

      <ShellCard
        title="Превью фаз"
        :pad="false"
      >
        <PhaseStrip
          :phases="phasePreviews"
          expanded
        />
      </ShellCard>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import Button from '@/Components/Button.vue'
import TextInput from '@/Components/TextInput.vue'
import {
  Field,
  Select,
  Stat,
  Hint,
  KV,
} from '@/Components/Shared/Primitives'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import PhaseStrip, {
  type PhasePreview,
} from '@/Components/Launch/Recipe/PhaseStrip.vue'

interface PlantOption {
  id: number
  name: string
}

interface RecipeOption {
  id: number
  name: string
  latest_published_revision_id?: number | null
  plants?: Array<{ id: number; name: string }>
}

interface RawRecipePhase {
  id?: number
  name?: string | null
  duration_hours?: number | null
  duration_days?: number | null
  ph_target?: number | null
  ec_target?: number | null
}

const props = withDefaults(
  defineProps<{
    recipeRevisionId?: number
    plantId?: number
    plantingAt?: string
    batchLabel?: string
    notes?: string
    recipes?: RecipeOption[]
    plants?: PlantOption[]
    recipePhases?: readonly RawRecipePhase[]
    errors?: Record<string, string>
  }>(),
  {
    recipeRevisionId: undefined,
    plantId: undefined,
    plantingAt: undefined,
    batchLabel: undefined,
    notes: undefined,
    recipes: () => [],
    plants: () => [],
    recipePhases: () => [],
    errors: () => ({}),
  },
)

const emit = defineEmits<{
  (e: 'update:recipeRevisionId', value: number | undefined): void
  (e: 'update:plantId', value: number | undefined): void
  (e: 'update:plantingAt', value: string | undefined): void
  (e: 'update:batchLabel', value: string | undefined): void
  (e: 'update:notes', value: string | undefined): void
  (e: 'refresh-plants'): void
  (e: 'refresh-recipes'): void
}>()

const { showToast } = useToast()
const { showHints } = useLaunchPreferences()

const selectedRecipeId = ref<number | null>(null)
const creatingPlantOpen = ref(false)
const newPlantName = ref('')
const newPlantVariety = ref('')
const creatingPlant = ref(false)

const plantOptions = computed(() =>
  props.plants.map((p) => ({ value: p.id, label: p.name })),
)

const filteredRecipes = computed<RecipeOption[]>(() => {
  if (!props.plantId) return []
  return props.recipes.filter((r) =>
    (r.plants ?? []).some((p) => p.id === props.plantId),
  )
})

const recipeOptions = computed(() =>
  filteredRecipes.value.map((r) => ({
    value: r.id,
    label: r.latest_published_revision_id
      ? `${r.name} · r${r.latest_published_revision_id} · published`
      : `${r.name} · нет published`,
  })),
)

const selectedRecipe = computed(
  () => filteredRecipes.value.find((r) => r.id === selectedRecipeId.value) ?? null,
)

const selectedRecipeRevisionLabel = computed(() => {
  if (!selectedRecipe.value) return '—'
  return selectedRecipe.value.latest_published_revision_id
    ? `r${selectedRecipe.value.latest_published_revision_id}`
    : 'нет published'
})

const phasePreviews = computed<PhasePreview[]>(() =>
  (props.recipePhases ?? []).map((p) => ({
    id: p.id,
    name: p.name ?? null,
    days: phaseDays(p),
    ph: p.ph_target ?? null,
    ec: p.ec_target ?? null,
  })),
)

function phaseDays(p: RawRecipePhase): number | null {
  if (typeof p.duration_days === 'number') return p.duration_days
  if (typeof p.duration_hours === 'number') return Math.max(1, Math.round(p.duration_hours / 24))
  return null
}

const plantingLocalValue = computed(() => {
  if (!props.plantingAt) return ''
  const d = new Date(props.plantingAt)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
})

function onPlantSelect(id: number | null): void {
  emit('update:plantId', id ?? undefined)
  // Если выбранный рецепт больше не подходит к новому plantId — сбрасываем.
  if (selectedRecipeId.value) {
    const stillValid = props.recipes
      .find((r) => r.id === selectedRecipeId.value)
      ?.plants?.some((p) => p.id === id)
    if (!stillValid) {
      selectedRecipeId.value = null
      emit('update:recipeRevisionId', undefined)
    }
  }
}

function onRecipeSelect(id: number | null): void {
  selectedRecipeId.value = id
  if (!id) {
    emit('update:recipeRevisionId', undefined)
    return
  }
  const recipe = filteredRecipes.value.find((r) => r.id === id)
  emit('update:recipeRevisionId', recipe?.latest_published_revision_id ?? undefined)
}

async function createPlant(): Promise<void> {
  const name = newPlantName.value.trim()
  if (!name) return
  creatingPlant.value = true
  try {
    const created = (await api.plants.create({
      name,
      variety: newPlantVariety.value.trim() || null,
    } as unknown as Parameters<typeof api.plants.create>[0])) as unknown as PlantOption
    creatingPlantOpen.value = false
    newPlantName.value = ''
    newPlantVariety.value = ''
    emit('refresh-plants')
    emit('update:plantId', created.id)
    showToast(`Растение «${created.name}» создано`, 'success')
  } catch (error) {
    showToast((error as Error).message || 'Ошибка создания растения', 'error')
  } finally {
    creatingPlant.value = false
  }
}

function openCreateRecipeInNewTab(): void {
  const params = new URLSearchParams()
  if (props.plantId) params.set('plant_id', String(props.plantId))
  const url = `/recipes/create${params.toString() ? '?' + params.toString() : ''}`
  window.open(url, '_blank', 'noopener')
}

function onPlantingChange(value: string): void {
  emit('update:plantingAt', value ? new Date(value).toISOString() : undefined)
}

function setPlantingToNow(): void {
  emit('update:plantingAt', new Date().toISOString())
}

function onBatchChange(value: string): void {
  emit('update:batchLabel', value.trim() || undefined)
}

function onNotesChange(value: string): void {
  emit('update:notes', value.trim() || undefined)
}
</script>
