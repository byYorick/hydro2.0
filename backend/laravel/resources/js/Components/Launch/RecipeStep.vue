<template>
    <section class="launch-step">
        <header class="launch-step__header">
            <h3 class="launch-step__title">Растение, рецепт и дата посадки</h3>
            <p class="launch-step__desc">
                Сначала выберите растение, затем подходящий рецепт. Если нужного нет — создайте новое.
            </p>
        </header>

        <div class="launch-step__section">
            <h4 class="launch-step__subtitle">1. Растение</h4>
            <div v-if="plants.length > 0 && !showCreatePlant" class="launch-step__grid">
                <button
                    v-for="plant in plants"
                    :key="plant.id"
                    type="button"
                    class="launch-step__option"
                    :class="{ 'is-selected': plantId === plant.id }"
                    @click="selectPlant(plant.id)"
                >
                    <span class="launch-step__option-title">{{ plant.name }}</span>
                </button>
            </div>
            <div v-else-if="!showCreatePlant" class="launch-step__empty">
                Нет созданных растений — создайте первое.
            </div>
            <button
                v-if="!showCreatePlant"
                type="button"
                class="launch-step__add-btn"
                @click="showCreatePlant = true"
            >
                + Создать растение
            </button>
            <div v-if="showCreatePlant" class="launch-step__form">
                <label class="launch-field">
                    <span class="launch-field__label">Название</span>
                    <input
                        v-model="newPlantName"
                        type="text"
                        class="launch-field__control"
                        placeholder="Напр.: Томат"
                        maxlength="255"
                    />
                </label>
                <label class="launch-field">
                    <span class="launch-field__label">Сорт (опционально)</span>
                    <input
                        v-model="newPlantVariety"
                        type="text"
                        class="launch-field__control"
                        maxlength="255"
                    />
                </label>
                <div class="launch-step__form-actions">
                    <button
                        type="button"
                        class="launch-step__btn launch-step__btn--primary"
                        :disabled="!newPlantName.trim() || creatingPlant"
                        @click="createPlant"
                    >
                        {{ creatingPlant ? 'Создание…' : 'Создать' }}
                    </button>
                    <button
                        type="button"
                        class="launch-step__btn launch-step__btn--ghost"
                        @click="showCreatePlant = false"
                    >
                        Отмена
                    </button>
                </div>
            </div>
        </div>

        <div v-if="plantId" class="launch-step__section">
            <h4 class="launch-step__subtitle">2. Рецепт</h4>
            <div v-if="filteredRecipes.length > 0" class="launch-step__grid">
                <button
                    v-for="recipe in filteredRecipes"
                    :key="recipe.id"
                    type="button"
                    class="launch-step__option"
                    :class="{ 'is-selected': selectedRecipeId === recipe.id }"
                    :disabled="!recipe.latest_published_revision_id"
                    :title="!recipe.latest_published_revision_id ? 'У рецепта нет опубликованной ревизии' : ''"
                    @click="selectRecipe(recipe)"
                >
                    <span class="launch-step__option-title">{{ recipe.name }}</span>
                    <span v-if="recipe.latest_published_revision_id" class="launch-step__option-meta">
                        published · rev #{{ recipe.latest_published_revision_id }}
                    </span>
                    <span v-else class="launch-step__option-meta launch-step__option-meta--warn">
                        нет published revision
                    </span>
                </button>
            </div>
            <div v-else class="launch-step__empty">
                Для выбранного растения нет рецептов — создайте новый.
            </div>
            <div class="launch-step__form-actions">
                <button
                    type="button"
                    class="launch-step__add-btn"
                    @click="openCreateRecipeInNewTab"
                >
                    + Создать рецепт (в новой вкладке)
                </button>
                <button
                    type="button"
                    class="launch-step__add-btn"
                    @click="$emit('refresh-recipes')"
                >
                    ↻ Обновить список
                </button>
            </div>
        </div>

        <div v-if="plantId && selectedRecipeId" class="launch-step__section">
            <h4 class="launch-step__subtitle">3. Дата посадки и метаданные</h4>
            <div class="launch-step__grid">
                <label class="launch-field">
                    <span class="launch-field__label">Дата и время посадки</span>
                    <div class="launch-field__row">
                        <input
                            type="datetime-local"
                            class="launch-field__control launch-field__control--grow"
                            :value="plantingLocalValue"
                            @input="onPlantingChange(($event.target as HTMLInputElement).value)"
                        />
                        <button
                            type="button"
                            class="launch-field__now-btn"
                            title="Установить текущую дату и время"
                            @click="setPlantingToNow"
                        >
                            <span class="launch-field__now-dot" aria-hidden="true"></span>
                            Сейчас
                        </button>
                    </div>
                </label>
                <label class="launch-field">
                    <span class="launch-field__label">Метка партии (опционально)</span>
                    <input
                        type="text"
                        class="launch-field__control"
                        :value="batchLabel ?? ''"
                        maxlength="100"
                        placeholder="batch-2026-04"
                        @input="onBatchChange(($event.target as HTMLInputElement).value)"
                    />
                </label>
                <label class="launch-field launch-field--full">
                    <span class="launch-field__label">Заметки</span>
                    <textarea
                        class="launch-field__control launch-field__control--textarea"
                        :value="notes ?? ''"
                        rows="3"
                        maxlength="2000"
                        @input="onNotesChange(($event.target as HTMLTextAreaElement).value)"
                    />
                </label>
            </div>
        </div>
    </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { api } from '@/services/api';
import { useToast } from '@/composables/useToast';

interface PlantOption {
    id: number;
    name: string;
}

interface RecipeOption {
    id: number;
    name: string;
    latest_published_revision_id?: number | null;
    plants?: Array<{ id: number; name: string }>;
}

interface Props {
    recipeRevisionId?: number;
    plantId?: number;
    plantingAt?: string;
    batchLabel?: string;
    notes?: string;
    recipes: RecipeOption[];
    plants: PlantOption[];
    errors: Record<string, string>;
}

const props = withDefaults(defineProps<Props>(), {
    recipeRevisionId: undefined,
    plantId: undefined,
    plantingAt: undefined,
    batchLabel: undefined,
    notes: undefined,
    recipes: () => [],
    plants: () => [],
    errors: () => ({}),
});

const emit = defineEmits<{
    (event: 'update:recipeRevisionId', value: number | undefined): void;
    (event: 'update:plantId', value: number | undefined): void;
    (event: 'update:plantingAt', value: string | undefined): void;
    (event: 'update:batchLabel', value: string | undefined): void;
    (event: 'update:notes', value: string | undefined): void;
    (event: 'refresh-plants'): void;
    (event: 'refresh-recipes'): void;
}>();

const { showToast } = useToast();

const selectedRecipeId = ref<number | null>(null);

const filteredRecipes = computed<RecipeOption[]>(() => {
    if (!props.plantId) return [];
    return props.recipes.filter((recipe) =>
        (recipe.plants ?? []).some((p) => p.id === props.plantId),
    );
});

const plantingLocalValue = computed(() => {
    if (!props.plantingAt) return '';
    const date = new Date(props.plantingAt);
    if (Number.isNaN(date.getTime())) return '';
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
});

const showCreatePlant = ref(false);
const newPlantName = ref('');
const newPlantVariety = ref('');
const creatingPlant = ref(false);

function selectPlant(id: number) {
    emit('update:plantId', id);
    if (selectedRecipeId.value) {
        const stillValid = props.recipes
            .find((r) => r.id === selectedRecipeId.value)
            ?.plants?.some((p) => p.id === id);
        if (!stillValid) {
            selectedRecipeId.value = null;
            emit('update:recipeRevisionId', undefined);
        }
    }
}

function selectRecipe(recipe: RecipeOption) {
    if (!recipe.latest_published_revision_id) return;
    selectedRecipeId.value = recipe.id;
    emit('update:recipeRevisionId', recipe.latest_published_revision_id);
}

async function createPlant() {
    const name = newPlantName.value.trim();
    if (!name) return;
    creatingPlant.value = true;
    try {
        const created = await api.plants.create({
            name,
            variety: newPlantVariety.value.trim() || null,
        } as unknown as Parameters<typeof api.plants.create>[0]);
        const record = created as unknown as PlantOption;
        showCreatePlant.value = false;
        newPlantName.value = '';
        newPlantVariety.value = '';
        showToast(`Растение «${record.name}» создано`, 'success');
        emit('refresh-plants');
        emit('update:plantId', record.id);
    } catch (error) {
        showToast((error as Error).message || 'Ошибка создания растения', 'error');
    } finally {
        creatingPlant.value = false;
    }
}

function openCreateRecipeInNewTab() {
    const params = new URLSearchParams();
    if (props.plantId) params.set('plant_id', String(props.plantId));
    const url = `/recipes/create${params.toString() ? '?' + params.toString() : ''}`;
    window.open(url, '_blank', 'noopener');
}

function onPlantingChange(value: string) {
    emit('update:plantingAt', value ? new Date(value).toISOString() : undefined);
}

function setPlantingToNow() {
    emit('update:plantingAt', new Date().toISOString());
}
function onBatchChange(value: string) {
    emit('update:batchLabel', value.trim() || undefined);
}
function onNotesChange(value: string) {
    emit('update:notes', value.trim() || undefined);
}
</script>

<style scoped>
.launch-step {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
}
.launch-step__title { font-size: 1rem; font-weight: 600; margin: 0 0 0.25rem; }
.launch-step__desc { margin: 0; opacity: 0.75; font-size: 0.875rem; }
.launch-step__subtitle {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    opacity: 0.8;
    margin: 0;
}
.launch-step__section { display: flex; flex-direction: column; gap: 0.6rem; }
.launch-step__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 0.5rem;
}
.launch-step__option {
    background: rgba(148, 163, 184, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    padding: 0.75rem;
    color: inherit;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    text-align: left;
}
.launch-step__option:disabled { cursor: not-allowed; opacity: 0.55; }
.launch-step__option.is-selected {
    border-color: rgba(56, 189, 248, 0.7);
    background: rgba(56, 189, 248, 0.1);
}
.launch-step__option-title { font-weight: 600; }
.launch-step__option-meta { font-size: 0.75rem; opacity: 0.65; }
.launch-step__option-meta--warn { color: rgb(251, 191, 36); }
.launch-step__empty {
    padding: 0.75rem;
    background: rgba(251, 191, 36, 0.08);
    border: 1px solid rgba(251, 191, 36, 0.35);
    border-radius: 0.5rem;
    font-size: 0.85rem;
}
.launch-step__add-btn {
    align-self: flex-start;
    padding: 0.4rem 0.8rem;
    background: transparent;
    border: 1px dashed rgba(148, 163, 184, 0.45);
    border-radius: 0.375rem;
    color: inherit;
    cursor: pointer;
    font-size: 0.85rem;
}
.launch-step__add-btn:hover { background: rgba(148, 163, 184, 0.08); }
.launch-step__form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    background: rgba(148, 163, 184, 0.04);
}
.launch-step__form-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.launch-step__btn {
    padding: 0.4rem 0.8rem;
    border-radius: 0.375rem;
    border: 1px solid transparent;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.85rem;
}
.launch-step__btn:disabled { cursor: not-allowed; opacity: 0.55; }
.launch-step__btn--primary { background: rgb(56, 189, 248); color: #0f172a; }
.launch-step__btn--ghost { background: transparent; color: inherit; }
.launch-field { display: flex; flex-direction: column; gap: 0.25rem; min-width: 0; }
.launch-field--full { grid-column: 1 / -1; }
.launch-field__label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    opacity: 0.8;
}
.launch-field__control {
    padding: 0.5rem 0.625rem;
    border-radius: 0.375rem;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(15, 23, 42, 0.35);
    color: inherit;
    font-size: 0.9rem;
}
.launch-field__control--textarea { resize: vertical; min-height: 80px; }
.launch-field__row {
    display: flex;
    gap: 0.5rem;
    align-items: stretch;
    min-width: 0;
}
.launch-field__control--grow {
    flex: 1 1 auto;
    min-width: 0;
}
.launch-field__now-btn {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0 0.9rem;
    border-radius: 0.375rem;
    border: 1px solid rgba(56, 189, 248, 0.55);
    background: rgba(56, 189, 248, 0.12);
    color: rgb(56, 189, 248);
    cursor: pointer;
    font-weight: 600;
    font-size: 0.8rem;
    letter-spacing: 0.02em;
    white-space: nowrap;
    transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
}
.launch-field__now-btn:hover {
    background: rgba(56, 189, 248, 0.22);
    border-color: rgba(56, 189, 248, 0.8);
    color: rgb(125, 211, 252);
}
.launch-field__now-btn:active {
    transform: translateY(1px);
}
.launch-field__now-dot {
    width: 6px;
    height: 6px;
    border-radius: 9999px;
    background: currentColor;
    box-shadow: 0 0 8px currentColor;
}
</style>
