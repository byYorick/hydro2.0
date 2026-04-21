<template>
    <section class="launch-step">
        <header class="launch-step__header">
            <h3 class="launch-step__title">Подтверждение запуска</h3>
            <p class="launch-step__desc">
                Проверьте итоговые значения. Если есть overrides — сравните текущее и новое в diff.
            </p>
        </header>

        <div class="preview-summary">
            <dl class="preview-summary__grid">
                <dt>Зона</dt>
                <dd>{{ payloadPreview.zone_id ?? '—' }}</dd>

                <dt>Ревизия рецепта</dt>
                <dd>{{ payloadPreview.recipe_revision_id ?? '—' }}</dd>

                <dt>Растение</dt>
                <dd>{{ payloadPreview.plant_id ?? '—' }}</dd>

                <dt>Дата посадки</dt>
                <dd>{{ payloadPreview.planting_at ?? '—' }}</dd>

                <dt>Метка партии</dt>
                <dd>{{ payloadPreview.batch_label || '—' }}</dd>
            </dl>
        </div>

        <RecipePhasesSummary v-if="recipePhases.length" :phases="recipePhases as never" />

        <slot name="diff-preview" />

        <div v-if="errors.length" class="preview-errors">
            <h4>Валидация не пройдена</h4>
            <ul>
                <li v-for="err in errors" :key="err.path">
                    <code>{{ err.path || '(root)' }}</code>: {{ err.message }}
                </li>
            </ul>
        </div>
    </section>
</template>

<script setup lang="ts">
import type { GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch';
import RecipePhasesSummary from '@/Components/Launch/RecipePhasesSummary.vue';

interface Props {
    payloadPreview: Partial<GrowCycleLaunchPayload>;
    errors: Array<{ path: string; message: string }>;
    recipePhases?: unknown[];
}

withDefaults(defineProps<Props>(), {
    payloadPreview: () => ({}),
    errors: () => [],
    recipePhases: () => [],
});
</script>

<style scoped>
.launch-step { display: flex; flex-direction: column; gap: 1rem; }
.launch-step__title { font-size: 1rem; font-weight: 600; margin: 0 0 0.25rem; }
.launch-step__desc { margin: 0; opacity: 0.75; font-size: 0.875rem; }

.preview-summary {
    padding: 0.75rem 1rem;
    background: rgba(148, 163, 184, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
}

.preview-summary__grid {
    display: grid;
    grid-template-columns: max-content 1fr;
    column-gap: 1rem;
    row-gap: 0.25rem;
    margin: 0;
}
.preview-summary__grid dt { font-weight: 600; opacity: 0.75; font-size: 0.8rem; }
.preview-summary__grid dd { margin: 0; font-size: 0.9rem; }

.preview-errors {
    padding: 0.75rem 1rem;
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 0.5rem;
}
.preview-errors h4 { margin: 0 0 0.25rem; font-size: 0.875rem; }
.preview-errors ul { margin: 0; padding-left: 1rem; font-size: 0.8rem; }
.preview-errors code { font-family: ui-monospace, monospace; }
</style>
