<template>
  <AppLayout>
    <Head :title="plant.name" />
    <div class="flex flex-col gap-4">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex-1 min-w-0">
          <div class="text-lg font-semibold truncate">
            {{ plant.name }}
          </div>
          <div class="text-xs text-[color:var(--text-muted)] mt-1">
            <span v-if="plant.species">{{ plant.species }}</span>
            <span v-if="plant.variety"> · {{ plant.variety }}</span>
            <span
              v-if="plant.description"
              class="block sm:inline sm:ml-1"
            >
              <span
                v-if="plant.species || plant.variety"
                class="hidden sm:inline"
              >·</span>
              {{ plant.description }}
            </span>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Link href="/plants">
            <Button
              size="sm"
              variant="secondary"
            >
              Назад к списку
            </Button>
          </Link>
          <Button
            size="sm"
            variant="outline"
            @click="openEditModal"
          >
            Редактировать
          </Button>
          <Button
            size="sm"
            variant="danger"
            :disabled="deleting"
            @click="deletePlant"
          >
            Удалить
          </Button>
        </div>
      </div>
      <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card class="xl:col-span-2">
          <div class="text-sm font-semibold mb-3">
            Основная информация
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Вид
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.species || "—" }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Сорт
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.variety || "—" }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Субстрат
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.substrate_type ? taxonomyLabel("substrate_type", plant.substrate_type) : "—" }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Система выращивания
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.growing_system ? taxonomyLabel("growing_system", plant.growing_system) : "—" }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Фотопериод
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.photoperiod_preset ? taxonomyLabel("photoperiod_preset", plant.photoperiod_preset) : "—" }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Сезонность
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ seasonalityLabel(plant.seasonality) }}
              </div>
            </div>
          </div>
          <div
            v-if="plant.description"
            class="mt-4"
          >
            <div class="text-xs text-[color:var(--text-muted)] mb-1">
              Описание
            </div>
            <div class="text-sm text-[color:var(--text-muted)] leading-relaxed">
              {{ plant.description }}
            </div>
          </div>
        </Card>
        <Card v-if="plant.profitability?.has_pricing">
          <div class="text-sm font-semibold mb-3">
            Экономика
          </div>
          <div class="space-y-3">
            <div>
              <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
                Себестоимость
              </div>
              <div class="text-lg font-semibold text-[color:var(--text-primary)]">
                {{ formatCurrency(plant.profitability.total_cost, plant.profitability.currency) }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
                Оптовая цена
              </div>
              <div class="text-lg font-semibold text-[color:var(--accent-green)]">
                {{ formatCurrency(plant.profitability.wholesale_price, plant.profitability.currency) }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                Маржа: {{ formatCurrency(plant.profitability.margin_wholesale, plant.profitability.currency) }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
                Розничная цена
              </div>
              <div class="text-lg font-semibold text-[color:var(--accent-cyan)]">
                {{ formatCurrency(plant.profitability.retail_price, plant.profitability.currency) }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                Маржа: {{ formatCurrency(plant.profitability.margin_retail, plant.profitability.currency) }}
              </div>
            </div>
          </div>
        </Card>
      </div>
      <Card v-if="hasEnvironment">
        <div class="text-sm font-semibold mb-3">
          Диапазоны параметров
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div
            v-for="(range, metric) in plant.environment_requirements"
            :key="metric"
          >
            <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
              {{ metricLabel(metric) }}
            </div>
            <div class="text-sm text-[color:var(--text-primary)]">
              {{ formatRange(range) }}
            </div>
          </div>
        </div>
      </Card>
      <Card v-if="plant.growth_phases && plant.growth_phases.length > 0">
        <div class="text-sm font-semibold mb-3">
          Фазы роста
        </div>
        <div class="space-y-2">
          <div
            v-for="(phase, index) in plant.growth_phases"
            :key="index"
            class="text-sm text-[color:var(--text-muted)] p-2 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
            <div class="font-medium">
              {{ phase.name || `Фаза ${index + 1}` }}
            </div>
            <div
              v-if="phase.duration_days"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Длительность: {{ phase.duration_days }} {{ phase.duration_days === 1 ? "день" : "дней" }}
            </div>
          </div>
        </div>
      </Card>
      <Card v-if="plant.recipes && plant.recipes.length > 0">
        <div class="text-sm font-semibold mb-4">
          Рецепты выращивания
        </div>
        <div class="space-y-4">
          <Card
            v-for="recipe in plant.recipes"
            :key="recipe.id"
            class="p-4"
          >
            <div class="flex items-start justify-between mb-4">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-2">
                  <Link
                    :href="`/recipes/${recipe.id}`"
                    class="text-base font-semibold text-[color:var(--accent-cyan)] hover:underline"
                  >
                    {{ recipe.name }}
                  </Link>
                  <Badge
                    v-if="recipe.is_default"
                    size="xs"
                    variant="info"
                  >
                    По умолчанию
                  </Badge>
                </div>
                <div
                  v-if="recipe.description"
                  class="text-sm text-[color:var(--text-muted)] mb-1"
                >
                  {{ recipe.description }}
                </div>
                <div
                  v-if="recipe.season || recipe.site_type"
                  class="text-xs text-[color:var(--text-dim)]"
                >
                  <span v-if="recipe.season">Сезон: {{ recipe.season }}</span>
                  <span
                    v-if="recipe.site_type"
                    class="ml-2"
                  >Тип: {{ recipe.site_type }}</span>
                </div>
              </div>
            </div>
            <div
              v-if="recipe.phases && recipe.phases.length > 0"
              class="mt-3"
            >
              <div class="text-xs text-[color:var(--text-muted)] mb-3">
                Фазы ({{ recipe.phases.length }}):
              </div>
              <div class="space-y-4">
                <Card
                  v-for="phase in recipe.phases"
                  :key="phase.id"
                  class="p-4"
                >
                  <div class="flex items-center justify-between mb-4">
                    <div class="font-semibold text-base text-[color:var(--text-primary)]">
                      {{ phase.phase_index + 1 }}. {{ phase.name }}
                    </div>
                    <div class="text-sm text-[color:var(--text-muted)]">
                      Длительность: {{ formatDuration(phase.duration_hours) }}
                    </div>
                  </div>
                  <div
                    v-if="hasPhaseTargets(phase.targets)"
                    class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
                  >
                    <div
                      v-if="hasTargetValue(phase.targets?.ph)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        pH
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ formatTargetRange(phase.targets?.ph) }}
                      </div>
                    </div>
                    <div
                      v-if="hasTargetValue(phase.targets?.ec)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        EC (мСм/см)
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ formatTargetRange(phase.targets?.ec) }}
                      </div>
                    </div>
                    <div
                      v-if="hasTargetValue(phase.targets?.temp_air)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Температура воздуха
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.temp_air }}°C
                      </div>
                    </div>
                    <div
                      v-if="hasTargetValue(phase.targets?.humidity_air)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Влажность воздуха
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.humidity_air }}%
                      </div>
                    </div>
                    <div
                      v-if="hasTargetValue(phase.targets?.light_hours)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Световой день
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.light_hours }} ч
                      </div>
                    </div>
                    <div
                      v-if="hasTargetValue(phase.targets?.irrigation_interval_sec)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Интервал полива
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ formatIrrigationInterval(phase.targets?.irrigation_interval_sec) }}
                      </div>
                    </div>
                    <div
                      v-if="hasTargetValue(phase.targets?.irrigation_duration_sec)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Длительность полива
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.irrigation_duration_sec }} сек
                      </div>
                    </div>
                  </div>
                  <div
                    v-else
                    class="text-xs text-[color:var(--text-dim)] text-center py-2"
                  >
                    Параметры не заданы
                  </div>
                </Card>
              </div>
            </div>
            <div
              v-else
              class="text-xs text-[color:var(--text-dim)] mt-2"
            >
              Нет фаз в рецепте
            </div>
          </Card>
        </div>
      </Card>
      <Modal
        :open="showEditModal"
        title="Редактирование растения"
        size="large"
        @close="closeEditModal"
      >
        <form
          class="space-y-4"
          @submit.prevent="handleSubmit"
        >
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="md:col-span-2">
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Название</label>
              <input
                v-model="form.name"
                type="text"
                class="input-field"
              />
              <p
                v-if="form.errors.name"
                class="text-xs text-[color:var(--badge-danger-text)] mt-1"
              >
                {{ form.errors.name }}
              </p>
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Вид</label>
              <input
                v-model="form.species"
                type="text"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Сорт</label>
              <input
                v-model="form.variety"
                type="text"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Субстрат</label>
              <select
                v-model="form.substrate_type"
                class="input-select"
              >
                <option value="">
                  Не выбрано
                </option>
                <option
                  v-for="option in taxonomies.substrate_type"
                  :key="option.id"
                  :value="option.id"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Система</label>
              <select
                v-model="form.growing_system"
                class="input-select"
              >
                <option value="">
                  Не выбрано
                </option>
                <option
                  v-for="option in taxonomies.growing_system"
                  :key="option.id"
                  :value="option.id"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Фотопериод</label>
              <select
                v-model="form.photoperiod_preset"
                class="input-select"
              >
                <option value="">
                  Не выбрано
                </option>
                <option
                  v-for="option in taxonomies.photoperiod_preset"
                  :key="option.id"
                  :value="option.id"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Сезонность</label>
              <select
                v-model="form.seasonality"
                class="input-select"
              >
                <option value="">
                  Не выбрано
                </option>
                <option
                  v-for="option in seasonOptions"
                  :key="option.id"
                  :value="option.id"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Описание</label>
              <textarea
                v-model="form.description"
                rows="4"
                class="input-field h-auto"
              ></textarea>
            </div>
            <div class="md:col-span-2">
              <p class="text-sm font-semibold text-[color:var(--text-primary)] mb-2">
                Диапазоны
              </p>
              <div
                v-for="metric in rangeMetrics"
                :key="metric.key"
                class="grid grid-cols-2 gap-3"
              >
                <label class="text-xs text-[color:var(--text-muted)] col-span-2">{{ metric.label }}</label>
                <input
                  v-model="form.environment_requirements[metric.key].min"
                  type="number"
                  step="0.1"
                  class="input-field h-8 text-xs"
                  placeholder="Мин"
                />
                <input
                  v-model="form.environment_requirements[metric.key].max"
                  type="number"
                  step="0.1"
                  class="input-field h-8 text-xs"
                  placeholder="Макс"
                />
              </div>
            </div>
          </div>
        </form>
        <template #footer>
          <Button
            type="button"
            variant="secondary"
            :disabled="form.processing"
            @click="closeEditModal"
          >
            Отмена
          </Button>
          <Button
            type="button"
            :disabled="form.processing"
            @click="handleSubmit"
          >
            Сохранить
          </Button>
        </template>
      </Modal>
      <ConfirmModal
        :open="deleteModalOpen"
        title="Удалить растение"
        :message="plant?.name ? `Удалить растение '${plant.name}'?` : 'Удалить растение?'"
        confirm-text="Удалить"
        confirm-variant="danger"
        :loading="deleting"
        @close="deleteModalOpen = false"
        @confirm="confirmDeletePlant"
      />
    </div>
  </AppLayout>
</template>
<script setup lang="ts">
import { Head, Link } from "@inertiajs/vue3";
import AppLayout from "@/Layouts/AppLayout.vue";
import Card from "@/Components/Card.vue";
import Button from "@/Components/Button.vue";
import Badge from "@/Components/Badge.vue";
import Modal from "@/Components/Modal.vue";
import ConfirmModal from "@/Components/ConfirmModal.vue";
import { usePlantShowPage } from "@/composables/usePlantShowPage";

const {
    plant,
    taxonomies,
    showEditModal,
    openEditModal,
    closeEditModal,
    deleting,
    deleteModalOpen,
    seasonOptions,
    rangeMetrics,
    form,
    hasEnvironment,
    taxonomyLabel,
    seasonalityLabel,
    metricLabel,
    handleSubmit,
    deletePlant,
    confirmDeletePlant,
    formatCurrency,
    formatDuration,
    formatIrrigationInterval,
    formatRange,
    formatTargetRange,
    hasPhaseTargets,
    hasTargetValue,
} = usePlantShowPage();
</script>
