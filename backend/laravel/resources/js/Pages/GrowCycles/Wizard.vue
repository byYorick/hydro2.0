<template>
  <AppLayout>
    <div class="max-w-4xl mx-auto">
      <div class="mb-6">
        <h1 class="text-2xl font-bold mb-2">Мастер запуска цикла выращивания</h1>
        <p class="text-sm text-[color:var(--text-muted)]">Пошаговая настройка цикла от посадки до сбора</p>
      </div>

      <!-- Прогресс шагов -->
      <div class="mb-6">
        <div class="flex items-center justify-between">
          <div
            v-for="(step, index) in steps"
            :key="index"
            class="flex items-center flex-1"
          >
            <div class="flex items-center">
              <div
                :class="[
                  'w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold',
                  currentStep > index
                    ? 'bg-[color:var(--accent-green)] text-[color:var(--btn-primary-text)]'
                    : currentStep === index
                    ? 'bg-[color:var(--accent-cyan)] text-[color:var(--btn-primary-text)] ring-2 ring-[color:var(--focus-ring)]'
                    : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'
                ]"
              >
                <span v-if="currentStep > index">✓</span>
                <span v-else>{{ index + 1 }}</span>
              </div>
              <span
                :class="[
                  'ml-2 text-xs',
                  currentStep >= index ? 'text-[color:var(--text-primary)]' : 'text-[color:var(--text-dim)]'
                ]"
              >
                {{ step.title }}
              </span>
            </div>
            <div
              v-if="index < steps.length - 1"
              :class="[
                'flex-1 h-0.5 mx-2',
                currentStep > index ? 'bg-[color:var(--accent-cyan)]' : 'bg-[color:var(--border-muted)]'
              ]"
            />
          </div>
        </div>
      </div>

      <Card>
        <!-- Шаг 1: Greenhouse → Zone -->
        <div v-if="currentStep === 0" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Теплица и Зона</h2>
            
            <div class="mb-6">
              <label class="block text-sm font-medium mb-2">Теплица</label>
              <div class="flex gap-2 mb-3">
                <Button
                  size="sm"
                  :variant="greenhouseMode === 'select' ? 'primary' : 'secondary'"
                  @click="greenhouseMode = 'select'"
                >
                  Выбрать существующую
                </Button>
                <Button
                  size="sm"
                  :variant="greenhouseMode === 'create' ? 'primary' : 'secondary'"
                  @click="greenhouseMode = 'create'"
                >
                  Создать новую
                </Button>
              </div>

              <div v-if="greenhouseMode === 'select'">
                <select
                  v-model="selectedGreenhouseId"
                  class="input-select w-full"
                  @change="loadZonesForGreenhouse"
                >
                  <option :value="null">Выберите теплицу</option>
                  <option
                    v-for="gh in wizardData.greenhouses"
                    :key="gh.id"
                    :value="gh.id"
                  >
                    {{ gh.name }} ({{ gh.uid }})
                  </option>
                </select>
              </div>

              <div v-else class="space-y-3">
                <input
                  v-model="newGreenhouse.name"
                  type="text"
                  placeholder="Название теплицы"
                  class="input-field w-full"
                />
                <Button size="sm" @click="createGreenhouse" :disabled="!newGreenhouse.name.trim() || loading.createGreenhouse">
                  {{ loading.createGreenhouse ? 'Создание...' : 'Создать' }}
                </Button>
              </div>
            </div>

            <div v-if="selectedGreenhouseId || createdGreenhouseId">
              <label class="block text-sm font-medium mb-2">Зона</label>
              <div class="flex gap-2 mb-3">
                <Button
                  size="sm"
                  :variant="zoneMode === 'select' ? 'primary' : 'secondary'"
                  @click="zoneMode = 'select'"
                >
                  Выбрать существующую
                </Button>
                <Button
                  size="sm"
                  :variant="zoneMode === 'create' ? 'primary' : 'secondary'"
                  @click="zoneMode = 'create'"
                >
                  Создать новую
                </Button>
              </div>

              <div v-if="zoneMode === 'select'">
                <select
                  v-model="selectedZoneId"
                  class="input-select w-full"
                  @change="loadZoneData"
                >
                  <option :value="null">Выберите зону</option>
                  <option
                    v-for="zone in availableZones"
                    :key="zone.id"
                    :value="zone.id"
                  >
                    {{ zone.name }} ({{ zone.uid }})
                  </option>
                </select>
              </div>

              <div v-else class="space-y-3">
                <input
                  v-model="newZone.name"
                  type="text"
                  placeholder="Название зоны"
                  class="input-field w-full"
                />
                <Button size="sm" @click="createZone" :disabled="!newZone.name.trim() || loading.createZone">
                  {{ loading.createZone ? 'Создание...' : 'Создать' }}
                </Button>
              </div>
            </div>
          </div>

          <div class="flex justify-end">
            <Button
              @click="nextStep"
              :disabled="!selectedZoneId && !createdZoneId"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 2: Plant -->
        <div v-if="currentStep === 1" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Растение</h2>

            <div class="mb-4">
              <label class="block text-sm font-medium mb-2">Выберите растение</label>
              <div class="flex gap-2 mb-3">
                <Button
                  size="sm"
                  :variant="plantMode === 'select' ? 'primary' : 'secondary'"
                  @click="plantMode = 'select'"
                >
                  Из каталога
                </Button>
                <Button
                  size="sm"
                  :variant="plantMode === 'create' ? 'primary' : 'secondary'"
                  @click="plantMode = 'create'"
                >
                  Создать новое
                </Button>
              </div>

              <div v-if="plantMode === 'select'">
                <select
                  v-model="selectedPlantId"
                  class="input-select w-full"
                  @change="onPlantSelected"
                >
                  <option :value="null">Выберите растение</option>
                  <option
                    v-for="plant in wizardData.plants"
                    :key="plant.id"
                    :value="plant.id"
                  >
                    {{ plant.name }} {{ plant.variety ? `(${plant.variety})` : '' }}
                  </option>
                </select>
              </div>
            </div>

            <div v-if="selectedPlantId" class="space-y-4">
              <h3 class="text-sm font-semibold">Партия</h3>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="block text-xs text-[color:var(--text-muted)] mb-1">Количество</label>
                  <input
                    v-model.number="batch.quantity"
                    type="number"
                    placeholder="Количество растений"
                    class="input-field w-full"
                  />
                </div>
                <div>
                  <label class="block text-xs text-[color:var(--text-muted)] mb-1">Плотность (шт/м²)</label>
                  <input
                    v-model.number="batch.density"
                    type="number"
                    step="0.1"
                    placeholder="Плотность"
                    class="input-field w-full"
                  />
                </div>
                <div>
                  <label class="block text-xs text-[color:var(--text-muted)] mb-1">Субстрат</label>
                  <input
                    v-model="batch.substrate"
                    type="text"
                    placeholder="Тип субстрата"
                    class="input-field w-full"
                  />
                </div>
                <div>
                  <label class="block text-xs text-[color:var(--text-muted)] mb-1">Система</label>
                  <input
                    v-model="batch.system"
                    type="text"
                    placeholder="Система выращивания"
                    class="input-field w-full"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="nextStep"
              :disabled="!selectedPlantId"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 3: Recipe → StageMap -->
        <div v-if="currentStep === 2" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Рецепт и маппинг стадий</h2>

            <div class="mb-4">
              <label class="block text-sm font-medium mb-2">Выберите рецепт</label>
              <select
                v-model="selectedRecipeId"
                class="input-select w-full"
                @change="onRecipeSelected"
              >
                <option :value="null">Выберите рецепт</option>
                <option
                  v-for="recipe in availableRecipes"
                  :key="recipe.id"
                  :value="recipe.id"
                >
                  {{ recipe.name }}
                </option>
              </select>
            </div>

            <div v-if="selectedRecipeId && selectedRecipe">
              <StageMapEditor
                :recipe-id="selectedRecipeId"
                :phases="selectedRecipe.phases"
                ref="stageMapEditorRef"
              />
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="nextStep"
              :disabled="!selectedRecipeId"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 4: Infrastructure -->
        <div v-if="currentStep === 3" class="space-y-6">
          <InfrastructurePlanner
            v-model="selectedInfrastructure"
            :zone-id="selectedZoneId"
          />
          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button @click="nextStep">Далее</Button>
          </div>
        </div>

        <!-- Шаг 5: Channel Binding -->
        <div v-if="currentStep === 4" class="space-y-6">
          <ChannelBinder
            :nodes="zoneData?.nodes || []"
            v-model="channelBindings"
          />
          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button @click="nextStep">Далее</Button>
          </div>
        </div>

        <!-- Шаг 6: Dates -->
        <div v-if="currentStep === 5" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Даты запуска</h2>

            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium mb-2">Дата посадки</label>
                <input
                  v-model="plantingDate"
                  type="datetime-local"
                  class="input-field w-full"
                />
              </div>

              <div>
                <label class="block text-sm font-medium mb-2">Дата старта автоматики</label>
                <input
                  v-model="automationStartDate"
                  type="datetime-local"
                  class="input-field w-full"
                />
                <p class="text-xs text-[color:var(--text-muted)] mt-1">
                  Может совпадать с датой посадки или быть позже
                </p>
              </div>

              <div>
                <label class="block text-sm font-medium mb-2">Прогноз сбора</label>
                <input
                  v-model="estimatedHarvestDate"
                  type="datetime-local"
                  class="input-field w-full"
                />
                <p class="text-xs text-[color:var(--text-muted)] mt-1">
                  Автоматически рассчитано на основе длительности фаз рецепта
                </p>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="nextStep"
              :disabled="!plantingDate || !automationStartDate"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 7: Readiness Checklist -->
        <div v-if="currentStep === 6" class="space-y-6">
          <ReadinessChecklist
            :zone-id="selectedZoneId"
            :readiness="zoneReadiness"
            :loading="loading.readiness"
          />
          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="createGrowCycle"
              :disabled="!zoneReadiness?.ready || loading.createCycle"
            >
              {{ loading.createCycle ? 'Создание...' : 'Запустить цикл' }}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import StageMapEditor from '@/Components/GrowCycle/StageMapEditor.vue'
import InfrastructurePlanner from '@/Components/Infrastructure/InfrastructurePlanner.vue'
import ChannelBinder from '@/Components/Infrastructure/ChannelBinder.vue'
import ReadinessChecklist from '@/Components/GrowCycle/ReadinessChecklist.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { logger } from '@/utils/logger'

const { showToast } = useToast()
const { api } = useApi(showToast)

const steps = [
  { title: 'Теплица/Зона' },
  { title: 'Растение' },
  { title: 'Рецепт' },
  { title: 'Инфраструктура' },
  { title: 'Каналы' },
  { title: 'Даты' },
  { title: 'Проверка' },
]

const currentStep = ref(0)
const greenhouseMode = ref<'select' | 'create'>('select')
const zoneMode = ref<'select' | 'create'>('select')
const plantMode = ref<'select' | 'create'>('select')

const wizardData = reactive({
  greenhouses: [] as any[],
  zones: [] as any[],
  plants: [] as any[],
  recipes: [] as any[],
})

const selectedGreenhouseId = ref<number | null>(null)
const createdGreenhouseId = ref<number | null>(null)
const availableZones = ref<any[]>([])
const selectedZoneId = ref<number | null>(null)
const createdZoneId = ref<number | null>(null)
const zoneData = ref<any>(null)
const zoneReadiness = ref<any>(null)

const newGreenhouse = reactive({ name: '' })
const newZone = reactive({ name: '' })

const selectedPlantId = ref<number | null>(null)
const batch = reactive({
  quantity: null as number | null,
  density: null as number | null,
  substrate: '',
  system: '',
})

const selectedRecipeId = ref<number | null>(null)
const selectedInfrastructure = ref<string[]>([])
const channelBindings = ref<any[]>([])

const plantingDate = ref('')
const automationStartDate = ref('')
const estimatedHarvestDate = ref('')

const stageMapEditorRef = ref<InstanceType<typeof StageMapEditor> | null>(null)

const loading = reactive({
  wizardData: false,
  createGreenhouse: false,
  createZone: false,
  zoneData: false,
  readiness: false,
  createCycle: false,
})

// Computed
const selectedPlant = computed(() => {
  if (selectedPlantId.value) {
    return wizardData.plants.find(p => p.id === selectedPlantId.value)
  }
  return null
})

const selectedRecipe = computed(() => {
  if (selectedRecipeId.value) {
    return wizardData.recipes.find(r => r.id === selectedRecipeId.value)
  }
  return null
})

const availableRecipes = computed(() => {
  if (selectedPlant.value?.recommended_recipes) {
    const recommendedIds = selectedPlant.value.recommended_recipes.map((r: any) => r.id || r)
    return wizardData.recipes.filter(r => recommendedIds.includes(r.id))
  }
  return wizardData.recipes
})

// Methods
onMounted(async () => {
  await loadWizardData()
  setDefaultDates()
})

function setDefaultDates() {
  const now = new Date()
  now.setMinutes(0, 0, 0)
  plantingDate.value = now.toISOString().slice(0, 16)
  automationStartDate.value = now.toISOString().slice(0, 16)
}

async function loadWizardData() {
  loading.wizardData = true
  try {
    const response = await api.get('/grow-cycle-wizard/data')
    if (response.data?.status === 'ok') {
      Object.assign(wizardData, response.data.data)
    }
  } catch (error) {
    logger.error('Failed to load wizard data:', error)
  } finally {
    loading.wizardData = false
  }
}

async function loadZonesForGreenhouse() {
  if (!selectedGreenhouseId.value) return
  const greenhouse = wizardData.greenhouses.find(gh => gh.id === selectedGreenhouseId.value)
  if (greenhouse) {
    availableZones.value = greenhouse.zones || []
  }
}

async function loadZoneData() {
  if (!selectedZoneId.value) return
  loading.zoneData = true
  loading.readiness = true
  try {
    const response = await api.get(`/grow-cycle-wizard/zone/${selectedZoneId.value}`)
    if (response.data?.status === 'ok') {
      zoneData.value = response.data.data
      zoneReadiness.value = response.data.data.readiness
    }
  } catch (error) {
    logger.error('Failed to load zone data:', error)
  } finally {
    loading.zoneData = false
    loading.readiness = false
  }
}

async function createGreenhouse() {
  if (!newGreenhouse.name.trim()) return
  loading.createGreenhouse = true
  try {
    const response = await api.post('/greenhouses', { name: newGreenhouse.name })
    if (response.data?.status === 'ok' || response.data?.id) {
      createdGreenhouseId.value = response.data.id || response.data.data?.id
      selectedGreenhouseId.value = createdGreenhouseId.value
      await loadWizardData()
      await loadZonesForGreenhouse()
      showToast('Теплица создана', 'success')
    }
  } catch (error) {
    logger.error('Failed to create greenhouse:', error)
  } finally {
    loading.createGreenhouse = false
  }
}

async function createZone() {
  if (!newZone.name.trim() || !selectedGreenhouseId.value) return
  loading.createZone = true
  try {
    const response = await api.post('/zones', {
      name: newZone.name,
      greenhouse_id: selectedGreenhouseId.value,
    })
    if (response.data?.status === 'ok' || response.data?.id) {
      createdZoneId.value = response.data.id || response.data.data?.id
      selectedZoneId.value = createdZoneId.value
      await loadWizardData()
      await loadZoneData()
      showToast('Зона создана', 'success')
    }
  } catch (error) {
    logger.error('Failed to create zone:', error)
  } finally {
    loading.createZone = false
  }
}

function onPlantSelected() {
  if (selectedPlant.value?.recommended_recipes && selectedPlant.value.recommended_recipes.length > 0) {
    const firstRecommended = selectedPlant.value.recommended_recipes[0]
    selectedRecipeId.value = firstRecommended.id || firstRecommended
    onRecipeSelected()
  }
}

function onRecipeSelected() {
  if (selectedRecipe.value) {
    const totalHours = selectedRecipe.value.phases.reduce((sum: number, phase: any) => sum + (phase.duration_hours || 0), 0)
    const planting = new Date(plantingDate.value)
    const harvest = new Date(planting.getTime() + totalHours * 60 * 60 * 1000)
    estimatedHarvestDate.value = harvest.toISOString().slice(0, 16)
  }
}

function nextStep() {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++
    
    if (currentStep.value === 4 && selectedZoneId.value && !zoneData.value) {
      loadZoneData()
    }
    
    if (currentStep.value === 6 && selectedZoneId.value) {
      loadZoneData()
    }
  }
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

async function createGrowCycle() {
  if (!selectedZoneId.value || !selectedPlantId.value || !selectedRecipeId.value) {
    showToast('Заполните все обязательные поля', 'error')
    return
  }

  // Получаем stage-map
  const stageMap = stageMapEditorRef.value?.getStageMap() || []

  // Сохраняем инфраструктуру
  if (selectedInfrastructure.value.length > 0) {
    try {
      const infrastructureData = selectedInfrastructure.value.map(assetType => {
        const required = ['PUMP', 'TANK_CLEAN', 'TANK_NUTRIENT', 'DRAIN'].includes(assetType)
        return {
          asset_type: assetType,
          label: getAssetLabel(assetType),
          required: required,
        }
      })
      
      await api.put(`/zones/${selectedZoneId.value}/infrastructure`, {
        infrastructure: infrastructureData,
      })
    } catch (error) {
      logger.error('Failed to save infrastructure:', error)
    }
  }

  loading.createCycle = true
  try {
    const response = await api.post('/grow-cycle-wizard/create', {
      zone_id: selectedZoneId.value,
      plant_id: selectedPlantId.value,
      recipe_id: selectedRecipeId.value,
      planting_date: new Date(plantingDate.value).toISOString(),
      automation_start_date: new Date(automationStartDate.value).toISOString(),
      batch: batch,
      channel_bindings: channelBindings.value,
      stage_map: stageMap,
    })

    if (response.data?.status === 'ok') {
      showToast('Цикл выращивания успешно создан!', 'success')
      router.visit(`/zones/${selectedZoneId.value}`)
    }
  } catch (error: any) {
    logger.error('Failed to create grow cycle:', error)
    
    // Если 422 с деталями готовности, показываем их
    if (error.response?.status === 422 && error.response?.data?.readiness_errors) {
      zoneReadiness.value = {
        ready: false,
        errors: error.response.data.readiness_errors,
      }
      showToast('Зона не готова к запуску. Проверьте список проблем.', 'error')
    } else {
      showToast(error.response?.data?.message || 'Ошибка при создании цикла', 'error')
    }
  } finally {
    loading.createCycle = false
  }
}

function getAssetLabel(assetType: string): string {
  const labels: Record<string, string> = {
    PUMP: 'Помпа',
    TANK_CLEAN: 'Бак чистой воды',
    TANK_NUTRIENT: 'Бак раствора',
    DRAIN: 'Дренаж',
    LIGHT: 'Свет',
    VENT: 'Вентиляция',
    HEATER: 'Отопление',
    MISTER: 'Туман',
  }
  return labels[assetType] || assetType
}

// Watchers
watch(selectedZoneId, (newId) => {
  if (newId) {
    loadZoneData()
  }
})

watch(plantingDate, () => {
  if (selectedRecipe.value) {
    onRecipeSelected()
  }
})
</script>
