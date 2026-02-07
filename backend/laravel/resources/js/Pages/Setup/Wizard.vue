<template>
  <!-- eslint-disable vue/singleline-html-element-content-newline -->
  <AppLayout>
    <div class="space-y-5">
      <section class="ui-hero p-6">
        <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">
          Мастер настройки системы
        </h1>
        <p class="text-sm text-[color:var(--text-muted)] mt-2">
          Пошаговая настройка теплицы, зоны, культуры, устройств и автоматики.
        </p>

        <div class="mt-4 h-2 rounded-full bg-[color:var(--border-muted)] overflow-hidden">
          <div
            class="h-full bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] transition-all duration-500"
            :style="{ width: `${progressPercent}%` }"
          ></div>
        </div>

        <div class="mt-3 text-xs text-[color:var(--text-dim)]">
          Прогресс: {{ progressPercent }}% ({{ completedSteps }}/6)
        </div>
      </section>

      <section
        v-if="!canConfigure"
        class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-4 text-sm text-[color:var(--badge-warning-text)]"
      >
        Режим только для просмотра. Полная настройка доступна агроному или администратору.
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <h2 class="text-sm font-semibold text-[color:var(--text-primary)] mb-3">
          Сценарий запуска
        </h2>
        <ul class="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          <li
            v-for="step in stepItems"
            :key="step.id"
            class="rounded-lg border px-3 py-2 text-xs"
            :class="step.done
              ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
              : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--text-muted)]'"
          >
            <div class="font-semibold">
              {{ step.title }}
            </div>
            <div class="mt-1">
              {{ step.hint }}
            </div>
          </li>
        </ul>

        <div class="mt-4 text-xs text-[color:var(--text-muted)]">
          <span
            v-for="item in launchChecklist"
            :key="item.id"
            class="inline-flex items-center mr-3"
          >
            <span class="mr-1">{{ item.done ? '✓' : '•' }}</span>{{ item.label }}
          </span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            1. Теплица
          </h3>
          <Badge :variant="stepGreenhouseDone ? 'success' : 'neutral'">
            {{ stepGreenhouseDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div
          v-if="greenhouseMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedGreenhouseId"
            class="input-select"
            :disabled="!canConfigure || loading.greenhouses"
            @change="selectGreenhouse"
          >
            <option :value="null">
              Выберите теплицу
            </option>
            <option
              v-for="greenhouse in availableGreenhouses"
              :key="greenhouse.id"
              :value="greenhouse.id"
            >
              {{ greenhouse.name }} ({{ greenhouse.uid }})
            </option>
          </select>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canConfigure"
            @click="greenhouseMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-else
          class="grid gap-3 md:grid-cols-3"
        >
          <input
            v-model="greenhouseForm.name"
            type="text"
            placeholder="Название теплицы"
            class="input-field"
            :disabled="!canConfigure"
          />
          <input
            :value="generatedGreenhouseUid"
            type="text"
            class="input-field"
            disabled
          />
          <select
            v-model.number="greenhouseForm.greenhouse_type_id"
            class="input-select"
            :disabled="!canConfigure"
          >
            <option :value="null">
              Выберите тип теплицы
            </option>
            <option
              v-for="greenhouseType in availableGreenhouseTypes"
              :key="greenhouseType.id"
              :value="greenhouseType.id"
            >
              {{ greenhouseType.name }}
            </option>
          </select>
          <textarea
            v-model="greenhouseForm.description"
            class="input-field md:col-span-2"
            rows="2"
            placeholder="Описание"
            :disabled="!canConfigure"
          ></textarea>
          <Button
            size="sm"
            :disabled="!canConfigure || !greenhouseForm.name.trim() || loading.stepGreenhouse"
            @click="createGreenhouse"
          >
            {{ loading.stepGreenhouse ? 'Создание...' : 'Создать теплицу' }}
          </Button>
        </div>

        <div
          v-if="selectedGreenhouse"
          class="text-sm text-[color:var(--text-muted)]"
        >
          Выбрано: <span class="font-semibold text-[color:var(--text-primary)]">{{ selectedGreenhouse.name }}</span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            2. Зона
          </h3>
          <Badge :variant="stepZoneDone ? 'success' : 'neutral'">
            {{ stepZoneDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div
          v-if="zoneMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedZoneId"
            class="input-select"
            :disabled="!canConfigure || loading.zones || !stepGreenhouseDone"
            @change="selectZone"
          >
            <option :value="null">
              Выберите зону
            </option>
            <option
              v-for="zone in availableZones"
              :key="zone.id"
              :value="zone.id"
            >
              {{ zone.name }}
            </option>
          </select>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canConfigure || !stepGreenhouseDone"
            @click="zoneMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-if="zoneMode === 'create'"
          class="grid gap-3 md:grid-cols-4"
        >
          <input
            v-model="zoneForm.name"
            type="text"
            placeholder="Название зоны"
            class="input-field"
            :disabled="!canConfigure || !stepGreenhouseDone"
          />
          <input
            v-model="zoneForm.description"
            type="text"
            placeholder="Описание зоны"
            class="input-field"
            :disabled="!canConfigure || !stepGreenhouseDone"
          />
          <input
            :value="generatedZoneUid"
            type="text"
            class="input-field"
            disabled
          />
          <Button
            size="sm"
            :disabled="!canConfigure || !stepGreenhouseDone || !zoneForm.name.trim() || loading.stepZone"
            @click="createZone"
          >
            {{ loading.stepZone ? 'Создание...' : 'Создать зону' }}
          </Button>
        </div>

        <div
          v-if="selectedZone"
          class="text-sm text-[color:var(--text-muted)]"
        >
          Выбрано: <span class="font-semibold text-[color:var(--text-primary)]">{{ selectedZone.name }}</span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            3. Культура и рецепт
          </h3>
          <Badge :variant="stepPlantDone ? 'success' : 'neutral'">
            {{ stepPlantDone && stepRecipeDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="flex gap-2">
          <Button
            size="sm"
            :variant="plantMode === 'select' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="plantMode = 'select'"
          >
            Выбрать
          </Button>
          <Button
            size="sm"
            :variant="plantMode === 'create' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="plantMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-if="plantMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedPlantId"
            class="input-select"
            :disabled="!canConfigure || loading.plants"
          >
            <option :value="null">Выберите растение</option>
            <option
              v-for="plant in availablePlants"
              :key="plant.id"
              :value="plant.id"
            >
              {{ plant.name }}
            </option>
          </select>
          <Button
            size="sm"
            :disabled="!canConfigure || !selectedPlantId || loading.stepPlant"
            @click="selectPlant"
          >
            Применить
          </Button>
        </div>

        <div
          v-else
          class="space-y-3"
        >
          <p class="text-sm text-[color:var(--text-muted)]">
            Создание культуры выполняется через мастер с одновременным созданием рецепта.
          </p>
          <Button
            size="sm"
            :disabled="!canConfigure"
            @click="showPlantCreateWizard = true"
          >
            Открыть мастер культуры и рецепта
          </Button>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
          <div class="text-xs text-[color:var(--text-muted)] mb-1">
            Рецепт по выбранной культуре
          </div>
          <div
            v-if="loading.stepRecipe"
            class="text-sm text-[color:var(--text-muted)]"
          >
            Подбираем и привязываем рецепт...
          </div>
          <div
            v-else-if="selectedRecipe"
            class="text-sm text-[color:var(--text-primary)]"
          >
            Используется рецепт: <span class="font-semibold">{{ selectedRecipe.name }}</span>
          </div>
          <div
            v-else
            class="text-sm text-[color:var(--badge-warning-text)]"
          >
            Выберите или создайте культуру, чтобы автоматически назначить рецепт.
          </div>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            4. Устройства
          </h3>
          <Badge :variant="stepDevicesDone ? 'success' : 'neutral'">
            {{ stepDevicesDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          <label
            v-for="node in availableNodes"
            :key="node.id"
            class="rounded-lg border border-[color:var(--border-muted)] p-2 text-sm"
          >
            <input
              v-model="selectedNodeIds"
              type="checkbox"
              :value="node.id"
              class="mr-2"
              :disabled="!canConfigure || !stepZoneDone"
            />
            {{ node.name || node.uid || `Node #${node.id}` }}
          </label>
        </div>

        <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-muted)]">
          <span>Привязано: {{ attachedNodesCount }}</span>
          <Button
            size="sm"
            :disabled="!canConfigure || !stepZoneDone || selectedNodeIds.length === 0 || loading.stepDevices"
            @click="attachNodesToZone"
          >
            {{ loading.stepDevices ? 'Привязка...' : 'Привязать выбранные узлы' }}
          </Button>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            5. Логика автоматики
          </h3>
          <Badge :variant="stepAutomationDone ? 'success' : 'neutral'">
            {{ stepAutomationDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="grid gap-3 md:grid-cols-3">
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs text-[color:var(--text-muted)]">Система (из рецепта)</div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ automationSystemLabel }}</div>
          </div>
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs text-[color:var(--text-muted)]">pH target (из рецепта)</div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ automationForm.targetPh.toFixed(2) }}</div>
          </div>
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs text-[color:var(--text-muted)]">EC target (из рецепта)</div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ automationForm.targetEc.toFixed(2) }}</div>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <label class="flex items-center gap-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-sm text-[color:var(--text-primary)]">
            <input
              v-model="automationForm.manageClimate"
              type="checkbox"
              :disabled="!canConfigure"
            />
            Управлять климатом
          </label>
          <label class="flex items-center gap-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-sm text-[color:var(--text-primary)]">
            <input
              v-model="automationForm.manageLighting"
              type="checkbox"
              :disabled="!canConfigure"
            />
            Управлять освещением
          </label>
        </div>

        <div class="text-xs text-[color:var(--text-muted)]">
          Топология воды: {{ waterTopologyLabel }}
        </div>
        <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)] space-y-2">
          <div class="font-semibold text-[color:var(--text-primary)]">Логика автоматики (полностью из рецепта):</div>
          <div>1. Выбирается культура, для неё автоматически назначается рецепт и активная фаза.</div>
          <div>2. Из фазы берутся тип системы, pH/EC, интервалы и длительность полива.</div>
          <div>3. Водный узел работает по схеме: набор чистой воды → подготовка раствора через узел коррекции pH/EC → полив по target с обратной связью.</div>
          <div>4. При 3-баках включается контроль дренажа, при 2-баках работает схема без дренажного бака.</div>
          <div>5. Климат и освещение управляются по целям фазы и переключателям управления.</div>
          <div>6. Форточки управляются по внутренней/внешней телеметрии и ограничениям открытия.</div>
          <div>7. При публикации нового рецепта параметры шага автоматики обновляются автоматически.</div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :disabled="!canConfigure || !stepZoneDone || loading.stepAutomation"
            @click="applyAutomation"
          >
            {{ loading.stepAutomation ? 'Отправка...' : 'Применить логику автоматики' }}
          </Button>
          <span class="text-xs text-[color:var(--text-muted)]">
            <span v-if="automationAppliedAt">Последнее применение: {{ formatDateTime(automationAppliedAt) }}</span>
            <span v-else>Ещё не применено</span>
          </span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            6. Запуск и контроль
          </h3>
          <Badge :variant="canLaunch ? 'success' : 'warning'">
            {{ canLaunch ? 'Можно запускать' : 'Есть незавершённые шаги' }}
          </Badge>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :disabled="!canLaunch || loading.stepLaunch"
            @click="openCycleWizard"
          >
            {{ loading.stepLaunch ? 'Открытие...' : 'Открыть мастер запуска цикла' }}
          </Button>

          <Link
            v-if="selectedZone"
            :href="`/zones/${selectedZone.id}`"
            class="text-xs text-[color:var(--accent-cyan)]"
          >
            Перейти к зоне
          </Link>
        </div>
      </section>
    </div>

    <PlantCreateModal
      :show="showPlantCreateWizard"
      @close="showPlantCreateWizard = false"
      @created="handlePlantCreated"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import PlantCreateModal from '@/Components/PlantCreateModal.vue'
import { useSetupWizard } from '@/composables/useSetupWizard'

const {
  canConfigure,
  loading,
  greenhouseMode,
  zoneMode,
  plantMode,
  availableGreenhouses,
  availableGreenhouseTypes,
  availableZones,
  availablePlants,
  availableNodes,
  selectedGreenhouseId,
  selectedZoneId,
  selectedPlantId,
  selectedGreenhouse,
  selectedZone,
  selectedRecipe,
  selectedNodeIds,
  attachedNodesCount,
  greenhouseForm,
  zoneForm,
  automationForm,
  automationAppliedAt,
  stepGreenhouseDone,
  stepZoneDone,
  stepPlantDone,
  stepRecipeDone,
  stepDevicesDone,
  stepAutomationDone,
  completedSteps,
  progressPercent,
  canLaunch,
  launchChecklist,
  stepItems,
  waterTopologyLabel,
  generatedGreenhouseUid,
  generatedZoneUid,
  createGreenhouse,
  selectGreenhouse,
  createZone,
  selectZone,
  selectPlant,
  attachNodesToZone,
  applyAutomation,
  openCycleWizard,
  formatDateTime,
} = useSetupWizard()

const showPlantCreateWizard = ref<boolean>(false)

const automationSystemLabel = computed<string>(() => {
  if (automationForm.systemType === 'drip') {
    return 'Капельный полив (drip)'
  }
  if (automationForm.systemType === 'substrate_trays') {
    return 'Лотки/субстрат (substrate trays)'
  }
  if (automationForm.systemType === 'nft') {
    return 'NFT (рециркуляция)'
  }

  return automationForm.systemType
})

function handlePlantCreated(plant: { id?: number; name?: string } | null): void {
  showPlantCreateWizard.value = false

  if (!plant?.id) {
    return
  }

  const exists = availablePlants.value.some((item) => item.id === plant.id)
  if (!exists) {
    availablePlants.value = [
      ...availablePlants.value,
      { id: plant.id, name: plant.name ?? `Plant #${plant.id}` },
    ]
  }

  selectedPlantId.value = plant.id
  plantMode.value = 'select'
  selectPlant()
}
</script>
