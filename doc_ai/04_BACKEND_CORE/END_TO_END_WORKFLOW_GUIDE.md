# END_TO_END_WORKFLOW_GUIDE.md
# Полное пошаговое руководство по созданию теплицы, зон, рецептов и привязке узлов

Этот документ описывает **конкретные шаги, API endpoints, payload'ы и UI компоненты** для полного workflow создания и настройки системы выращивания от начала до конца.

**Целевая аудитория:** Разработчики, реализующие функциональность создания теплиц, зон, рецептов и привязку узлов.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## Содержание

1. [Обзор workflow](#1-обзор-workflow)
2. [Шаг 1: Создание теплицы (Greenhouse)](#2-шаг-1-создание-теплицы-greenhouse)
3. [Шаг 2: Создание рецепта выращивания (Recipe)](#3-шаг-2-создание-рецепта-выращивания-recipe)
4. [Шаг 3: Добавление фаз ревизии рецепта (Recipe Revision Phases)](#4-шаг-3-добавление-фаз-ревизии-рецепта-recipe-revision-phases)
5. [Шаг 4: Создание зоны (Zone)](#5-шаг-4-создание-зоны-zone)
6. [Шаг 5: Привязка рецепта к зоне](#6-шаг-5-привязка-рецепта-к-зоне)
7. [Шаг 6: Регистрация и привязка узлов (Nodes)](#7-шаг-6-регистрация-и-привязка-узлов-nodes)
8. [Шаг 7: Настройка каналов узлов (Node Channels)](#8-шаг-7-настройка-каналов-узлов-node-channels)
9. [Шаг 8: Запуск зоны и начало цикла](#9-шаг-8-запуск-зоны-и-начало-цикла)
10. [UI компоненты и их подключение](#10-ui-компоненты-и-их-подключение)
11. [Полный пример payload'ов](#11-полный-пример-payloadов)

---

## 1. Обзор workflow

Полный workflow состоит из следующих этапов:

```
1. Greenhouse (Теплица)
   ↓
2. Recipe + Recipe Phases (Рецепт с фазами)
   ↓
3. Zone (Зона)
   ↓
4. Attach Recipe to Zone (Привязка рецепта)
   ↓
5. Register Nodes (Регистрация узлов)
   ↓
6. Bind Nodes to Zone (Привязка узлов к зоне)
   ↓
7. Configure Node Channels (Настройка каналов)
   ↓
8. Start Zone (Запуск зоны)
```

---

## 2. Шаг 1: Создание теплицы (Greenhouse)

### API Endpoint

```
POST /api/greenhouses
```

### Request Headers

```http
Content-Type: application/json
Accept: application/json
X-Requested-With: XMLHttpRequest
```

### Request Payload

```json
{
  "uid": "gh-main",
  "name": "Main Greenhouse",
  "timezone": "Europe/Moscow",
  "type": "indoor",
  "coordinates": {
    "lat": 55.7558,
    "lng": 37.6173
  },
  "description": "Main indoor greenhouse facility"
}
```

### Response (201 Created)

```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "uid": "gh-main",
    "name": "Main Greenhouse",
    "timezone": "Europe/Moscow",
    "type": "indoor",
    "coordinates": {
      "lat": 55.7558,
      "lng": 37.6173
    },
    "description": "Main indoor greenhouse facility",
    "created_at": "2025-11-21T10:00:00.000000Z",
    "updated_at": "2025-11-21T10:00:00.000000Z"
  }
}
```

### Валидация

- `uid` - обязательное, уникальное, максимум 64 символа
- `name` - обязательное, максимум 255 символов
- `timezone` - опциональное, максимум 128 символов
- `type` - опциональное, максимум 64 символа
- `coordinates` - опциональное, массив
- `description` - опциональное, текст

### UI Компонент (Vue 3)

```vue
<template>
  <Card>
    <h2>Create Greenhouse</h2>
    <form @submit.prevent="onSubmit">
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label>UID</label>
          <input 
            v-model="form.uid" 
            type="text" 
            required 
            placeholder="gh-main"
          />
        </div>
        <div>
          <label>Name</label>
          <input 
            v-model="form.name" 
            type="text" 
            required 
            placeholder="Main Greenhouse"
          />
        </div>
        <div>
          <label>Timezone</label>
          <input 
            v-model="form.timezone" 
            type="text" 
            placeholder="Europe/Moscow"
          />
        </div>
        <div>
          <label>Type</label>
          <select v-model="form.type">
            <option value="indoor">Indoor</option>
            <option value="outdoor">Outdoor</option>
          </select>
        </div>
      </div>
      <button type="submit">Create</button>
    </form>
  </Card>
</template>

<script setup>
import { reactive } from 'vue'
import axios from 'axios'

const form = reactive({
  uid: '',
  name: '',
  timezone: 'Europe/Moscow',
  type: 'indoor',
  coordinates: null,
  description: ''
})

async function onSubmit() {
  try {
    const response = await axios.post('/api/greenhouses', form, {
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    console.log('Greenhouse created:', response.data.data)
    // Redirect или обновление списка
  } catch (error) {
    console.error('Error creating greenhouse:', error.response?.data)
  }
}
</script>
```

---

## 3. Шаг 2: Создание рецепта выращивания (Recipe)

### API Endpoint

```
POST /api/recipes
```

### Request Payload

```json
{
  "name": "Lettuce NFT Recipe",
  "description": "Standard NFT recipe for lettuce cultivation"
}
```

### Response (201 Created)

```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "name": "Lettuce NFT Recipe",
    "description": "Standard NFT recipe for lettuce cultivation",
    "created_at": "2025-11-21T10:05:00.000000Z",
    "updated_at": "2025-11-21T10:05:00.000000Z"
  }
}
```

### Валидация

- `name` - обязательное, максимум 255 символов
- `description` - опциональное, текст

---

## 4. Шаг 3: Добавление фаз ревизии рецепта (Recipe Revision Phases)

Для каждого этапа роста нужно создать фазу ревизии рецепта.
Сначала создается DRAFT-ревизия рецепта через `POST /api/recipes/{recipe_id}/revisions`,
после чего фазы добавляются в эту ревизию.

### API Endpoint

```
POST /api/recipe-revisions/{recipe_revision_id}/phases
```

### Request Payload для фазы "Vegetative"

```json
{
  "phase_index": 0,
  "name": "Seedling",
  "duration_hours": 168,
  "targets": {
    "ph": 5.8,
    "ec": 1.2,
    "temp_air": 22,
    "humidity_air": 65,
    "light_hours": 18,
    "irrigation_interval_sec": 900,
    "irrigation_duration_sec": 10
  }
}
```

### Request Payload для фазы "Flowering"

```json
{
  "phase_index": 1,
  "name": "Vegetative",
  "duration_hours": 336,
  "targets": {
    "ph": 5.8,
    "ec": 1.4,
    "temp_air": 23,
    "humidity_air": 60,
    "light_hours": 16,
    "irrigation_interval_sec": 720,
    "irrigation_duration_sec": 12
  }
}
```

### Request Payload для фазы "Harvest"

```json
{
  "phase_index": 2,
  "name": "Flowering",
  "duration_hours": 504,
  "targets": {
    "ph": 6.0,
    "ec": 1.6,
    "temp_air": 24,
    "humidity_air": 55,
    "light_hours": 12,
    "irrigation_interval_sec": 600,
    "irrigation_duration_sec": 15
  }
}
```

### Response (201 Created)

```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "recipe_id": 1,
    "phase_index": 0,
    "name": "Seedling",
    "duration_hours": 168,
    "targets": {
      "ph": 5.8,
      "ec": 1.2,
      "temp_air": 22,
      "humidity_air": 65,
      "light_hours": 18,
      "irrigation_interval_sec": 900,
      "irrigation_duration_sec": 10
    },
    "created_at": "2025-11-21T10:10:00.000000Z"
  }
}
```

### Валидация

- `phase_index` - обязательное, целое число >= 0
- `name` - обязательное, максимум 255 символов
- `duration_hours` - обязательное, целое число >= 1
- `targets` - обязательное, объект
  - `ph` - опциональное, 0-14
  - `ec` - опциональное, >= 0
  - `temp_air` - опциональное, число
  - `humidity_air` - опциональное, 0-100
  - `light_hours` - опциональное, 0-24
  - `irrigation_interval_sec` - опциональное, >= 1
  - `irrigation_duration_sec` - опциональное, >= 1

### UI Компонент для создания рецепта с фазами

```vue
<template>
  <Card>
    <h2>Create Recipe with Phases</h2>
    <form @submit.prevent="onSubmit">
      <div class="mb-4">
        <label>Recipe Name</label>
        <input v-model="recipeForm.name" required />
      </div>
      
      <div class="mb-4">
        <label>Description</label>
        <textarea v-model="recipeForm.description"></textarea>
      </div>

      <div class="mb-4">
        <h3>Phases</h3>
        <div 
          v-for="(phase, index) in phases" 
          :key="index" 
          class="border p-4 mb-2"
        >
          <h4>Phase {{ index }}</h4>
          <input v-model="phase.name" placeholder="Phase name" />
          <input 
            v-model.number="phase.duration_hours" 
            type="number" 
            placeholder="Duration (hours)" 
          />
          
          <div class="grid grid-cols-2 gap-2 mt-2">
            <input 
              v-model.number="phase.targets.ph" 
              type="number" 
              step="0.1" 
              placeholder="pH target" 
            />
            <input 
              v-model.number="phase.targets.ec" 
              type="number" 
              step="0.1" 
              placeholder="EC target" 
            />
            <input 
              v-model.number="phase.targets.temp_air" 
              type="number" 
              placeholder="Temperature" 
            />
            <input 
              v-model.number="phase.targets.humidity_air" 
              type="number" 
              placeholder="Humidity" 
            />
            <input 
              v-model.number="phase.targets.light_hours" 
              type="number" 
              placeholder="Light hours" 
            />
            <input 
              v-model.number="phase.targets.irrigation_interval_sec" 
              type="number" 
              placeholder="Irrigation interval (sec)" 
            />
            <input 
              v-model.number="phase.targets.irrigation_duration_sec" 
              type="number" 
              placeholder="Irrigation duration (sec)" 
            />
          </div>
        </div>
        <button type="button" @click="addPhase">Add Phase</button>
      </div>

      <button type="submit">Create Recipe</button>
    </form>
  </Card>
</template>

<script setup>
import { reactive } from 'vue'
import axios from 'axios'

const recipeForm = reactive({
  name: '',
  description: ''
})

const phases = reactive([
  {
    phase_index: 0,
    name: '',
    duration_hours: 0,
    targets: {
      ph: null,
      ec: null,
      temp_air: null,
      humidity_air: null,
      light_hours: null,
      irrigation_interval_sec: null,
      irrigation_duration_sec: null
    }
  }
])

function addPhase() {
  phases.push({
    phase_index: phases.length,
    name: '',
    duration_hours: 0,
    targets: {
      ph: null,
      ec: null,
      temp_air: null,
      humidity_air: null,
      light_hours: null,
      irrigation_interval_sec: null,
      irrigation_duration_sec: null
    }
  })
}

async function onSubmit() {
  try {
    // 1. Создать рецепт
    const recipeResponse = await axios.post('/api/recipes', recipeForm)
    const recipeId = recipeResponse.data.data.id

    // 2. Создать фазы
    for (const phase of phases) {
      await axios.post(`/api/recipes/${recipeId}/phases`, {
        ...phase,
        phase_index: phases.indexOf(phase)
      })
    }

    console.log('Recipe created with phases:', recipeId)
    // Redirect или обновление
  } catch (error) {
    console.error('Error creating recipe:', error.response?.data)
  }
}
</script>
```

---

## 5. Шаг 4: Создание зоны (Zone)

### API Endpoint

```
POST /api/zones
```

### Request Payload

```json
{
  "greenhouse_id": 1,
  "preset_id": null,
  "name": "Zone A - Lettuce",
  "description": "NFT system for lettuce cultivation",
  "status": "RUNNING"
}
```

### Response (201 Created)

```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "greenhouse_id": 1,
    "preset_id": null,
    "name": "Zone A - Lettuce",
    "description": "NFT system for lettuce cultivation",
    "status": "RUNNING",
    "health_score": null,
    "health_status": null,
    "created_at": "2025-11-21T10:15:00.000000Z",
    "updated_at": "2025-11-21T10:15:00.000000Z"
  }
}
```

### Валидация

- `greenhouse_id` - опциональное, должно существовать в таблице greenhouses
- `preset_id` - опциональное, должно существовать в таблице presets
- `name` - обязательное, максимум 255 символов
- `description` - опциональное, текст
- `status` - опциональное, максимум 32 символа (RUNNING, PAUSED, WARNING, ALARM)

---

## 6. Шаг 5: Привязка рецепта к зоне

### API Endpoint

```
POST /api/zones/{zone_id}/attach-recipe
```

### Request Payload

```json
{
  "recipe_id": 1,
  "start_at": "2025-11-21T10:20:00Z"
}
```

### Response (200 OK)

```json
{
  "status": "ok"
}
```

### Что происходит при привязке:

1. Создается запись `zone_recipe_instances` с начальной фазой (phase_index = 0)
2. Зона начинает использовать targets из первой фазы рецепта
3. automation-engine начинает отслеживать зону и применять контроллеры

### Валидация

- `recipe_id` - обязательное, должно существовать в таблице recipes
- `start_at` - опциональное, дата/время начала рецепта

---

## 7. Шаг 6: Регистрация и привязка узлов (Nodes)

### 7.1. Регистрация узла

Узлы могут регистрироваться автоматически через MQTT или вручную через API.

#### API Endpoint (автоматическая регистрация)

```
POST /api/nodes/register
```

#### Request Payload (от ESP32 узла)

```json
{
  "uid": "node-001",
  "hardware_id": "ESP32-ABC123",
  "type": "sensor",
  "fw_version": "2.0.1",
  "hardware_revision": "rev2"
}
```

#### Response (201 Created)

```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "uid": "node-001",
    "zone_id": null,
    "type": "sensor",
    "status": "offline",
    "lifecycle_state": "registered_backend",
    "created_at": "2025-11-21T10:25:00.000000Z"
  }
}
```

### 7.2. Привязка узла к зоне

#### API Endpoint

```
PATCH /api/nodes/{node_id}
```

#### Request Payload

```json
{
  "zone_id": 1,
  "name": "pH/EC Sensor Zone A"
}
```

#### Response (200 OK)

```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "uid": "node-001",
    "zone_id": 1,
    "name": "pH/EC Sensor Zone A",
    "type": "sensor",
    "status": "online",
    "lifecycle_state": "provisioned",
    "updated_at": "2025-11-21T10:30:00.000000Z"
  }
}
```

### Получение списка непривязанных узлов

#### API Endpoint

```
GET /api/nodes?unassigned=true
```

#### Response

```json
{
  "status": "ok",
  "data": {
    "data": [
      {
        "id": 1,
        "uid": "node-001",
        "zone_id": null,
        "type": "sensor",
        "status": "online",
        "channels": []
      }
    ]
  }
}
```

---

## 8. Шаг 7: NodeConfig (read-only)

Конфиг узла формируется в прошивке и отправляется на сервер через `config_report`.
Сервер **не генерирует и не редактирует** NodeConfig, а только хранит и использует для команд/телеметрии.

### Как происходит синхронизация:

1. Нода подключается к MQTT
2. Нода отправляет `config_report` в `hydro/{gh}/{zone}/{node}/config_report`
3. history-logger сохраняет конфиг в `nodes.config` и синхронизирует `node_channels`
4. Узел считается привязанным к зоне после получения `config_report`

### Получение конфигурации узла

#### API Endpoint

```
GET /api/nodes/{node_id}/config
```

#### Response

```json
{
  "status": "ok",
  "data": {
    "node_id": "nd-ph-1",
    "version": 3,
    "channels": [
      {
        "channel": "ph_sensor",
        "type": "sensor",
        "metric": "PH",
        "unit": "pH"
      },
      {
        "channel": "pump_A",
        "type": "actuator",
        "actuator_type": "PERISTALTIC_PUMP"
      }
    ]
  }
}
```

---

## 9. Шаг 8: Запуск зоны и начало цикла

После привязки рецепта и узлов зона готова к работе. automation-engine автоматически:

1. Получает конфигурацию зоны из Laravel API
2. Читает телеметрию из `telemetry_last`
3. Сравнивает с targets из текущей фазы рецепта
4. Генерирует команды для корректировки параметров
5. Отправляет команды через MQTT

### Проверка состояния зоны

#### API Endpoint

```
GET /api/zones/{zone_id}/health
```

#### Response

```json
{
  "status": "ok",
  "data": {
    "zone_id": 1,
    "health_score": 85.5,
    "health_status": "ok",
    "zone_status": "RUNNING",
    "active_alerts_count": 0,
    "nodes_online": 2,
    "nodes_total": 2
  }
}
```

### Получение информации о циклах зоны

#### API Endpoint

```
GET /api/zones/{zone_id}/cycles
```

#### Response

```json
{
  "status": "ok",
  "data": {
    "PH_CONTROL": {
      "type": "PH_CONTROL",
      "strategy": "periodic",
      "interval": 300,
      "last_run": "2025-11-21T10:45:00Z",
      "next_run": "2025-11-21T10:50:00Z"
    },
    "EC_CONTROL": {
      "type": "EC_CONTROL",
      "strategy": "periodic",
      "interval": 300,
      "last_run": "2025-11-21T10:45:00Z",
      "next_run": "2025-11-21T10:50:00Z"
    },
    "IRRIGATION": {
      "type": "IRRIGATION",
      "strategy": "periodic",
      "interval": 900,
      "last_run": "2025-11-21T10:30:00Z",
      "next_run": "2025-11-21T10:45:00Z"
    },
    "LIGHTING": {
      "type": "LIGHTING",
      "strategy": "periodic",
      "interval": 64800,
      "last_run": null,
      "next_run": "2025-11-21T18:00:00Z"
    },
    "CLIMATE": {
      "type": "CLIMATE",
      "strategy": "periodic",
      "interval": 300,
      "last_run": "2025-11-21T10:45:00Z",
      "next_run": "2025-11-21T10:50:00Z"
    }
  }
}
```

### Переход на следующую фазу

#### API Endpoint

```
POST /api/zones/{zone_id}/next-phase
```

#### Response (200 OK)

```json
{
  "status": "ok",
  "data": {
    "zone_id": 1,
    "recipe_instance_id": 1,
    "current_phase_index": 1,
    "current_phase_name": "Vegetative",
    "phase_started_at": "2025-11-21T11:00:00Z"
  }
}
```

---

## 10. UI компоненты и их подключение

### 10.1. Страница создания теплицы

**Файл:** `backend/laravel/resources/js/Pages/Greenhouses/Create.vue`

```vue
<template>
  <AppLayout>
    <h1>Create Greenhouse</h1>
    <GreenhouseForm @submit="handleSubmit" />
  </AppLayout>
</template>

<script setup>
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import GreenhouseForm from '@/Components/GreenhouseForm.vue'

function handleSubmit(formData) {
  router.post('/api/greenhouses', formData, {
    onSuccess: () => router.visit('/greenhouses')
  })
}
</script>
```

### 10.2. Компонент формы рецепта с фазами

**Файл:** `backend/laravel/resources/js/Components/RecipeForm.vue`

```vue
<template>
  <form @submit.prevent="onSubmit">
    <div class="space-y-4">
      <div>
        <label>Recipe Name</label>
        <input v-model="form.name" required />
      </div>

      <div v-for="(phase, index) in form.phases" :key="index">
        <PhaseForm 
          v-model="form.phases[index]" 
          :phase-index="index"
        />
      </div>

      <button type="button" @click="addPhase">Add Phase</button>
      <button type="submit">Save Recipe</button>
    </div>
  </form>
</template>

<script setup>
import { reactive } from 'vue'
import PhaseForm from './PhaseForm.vue'

const props = defineProps({
  recipe: Object
})

const emit = defineEmits(['submit'])

const form = reactive({
  name: props.recipe?.name || '',
  description: props.recipe?.description || '',
  phases: props.recipe?.phases || [createPhase(0)]
})

function createPhase(index) {
  return {
    phase_index: index,
    name: '',
    duration_hours: 0,
    targets: {
      ph: null,
      ec: null,
      temp_air: null,
      humidity_air: null,
      light_hours: null,
      irrigation_interval_sec: null,
      irrigation_duration_sec: null
    }
  }
}

function addPhase() {
  form.phases.push(createPhase(form.phases.length))
}

async function onSubmit() {
  emit('submit', form)
}
</script>
```

### 10.3. Страница управления зоной

**Файл:** `backend/laravel/resources/js/Pages/Zones/Show.vue`

```vue
<template>
  <AppLayout>
    <div class="grid grid-cols-2 gap-4">
      <Card>
        <h2>Zone Info</h2>
        <p>Name: {{ zone.name }}</p>
        <p>Status: {{ zone.status }}</p>
        <p>Health: {{ zone.health_score }}/100</p>
      </Card>

      <Card>
        <h2>Attached Recipe</h2>
        <select 
          v-model="selectedRecipeId" 
          @change="attachRecipe"
        >
          <option :value="null">Select recipe</option>
          <option 
            v-for="recipe in recipes" 
            :key="recipe.id" 
            :value="recipe.id"
          >
            {{ recipe.name }}
          </option>
        </select>
      </Card>

      <Card>
        <h2>Nodes</h2>
        <NodeList 
          :nodes="zone.nodes" 
          @attach="attachNode"
        />
      </Card>

      <Card>
        <h2>Available Nodes</h2>
        <NodeList 
          :nodes="availableNodes" 
          :show-attach="true"
          @attach="attachNode"
        />
      </Card>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import NodeList from '@/Components/NodeList.vue'

const props = defineProps({
  zone: Object
})

const recipes = ref([])
const availableNodes = ref([])
const selectedRecipeId = ref(props.zone.recipe_instance?.recipe_id || null)

onMounted(async () => {
  // Загрузить рецепты
  const recipesRes = await axios.get('/api/recipes')
  recipes.value = recipesRes.data.data.data || recipesRes.data.data

  // Загрузить доступные узлы
  const nodesRes = await axios.get('/api/nodes?unassigned=true')
  availableNodes.value = nodesRes.data.data.data || nodesRes.data.data
})

async function attachRecipe() {
  if (!selectedRecipeId.value) return
  await axios.post(`/api/zones/${props.zone.id}/attach-recipe`, {
    recipe_id: selectedRecipeId.value
  })
}

async function attachNode(nodeId) {
  await axios.patch(`/api/nodes/${nodeId}`, {
    zone_id: props.zone.id
  })
  // Обновить список
}
</script>
```

---

## 11. Полный пример payload'ов

### Сценарий: Создание полной системы выращивания

#### 1. Создать теплицу

```bash
POST /api/greenhouses
{
  "uid": "gh-001",
  "name": "Production Greenhouse",
  "timezone": "Europe/Moscow",
  "type": "indoor"
}
```

#### 2. Создать рецепт

```bash
POST /api/recipes
{
  "name": "Lettuce NFT Full Cycle",
  "description": "Complete lettuce cultivation recipe"
}
```

#### 3. Добавить фазы рецепта

```bash
POST /api/recipes/1/phases
{
  "phase_index": 0,
  "name": "Seedling",
  "duration_hours": 168,
  "targets": {
    "ph": 5.8,
    "ec": 1.2,
    "temp_air": 22,
    "humidity_air": 65,
    "light_hours": 18,
    "irrigation_interval_sec": 900,
    "irrigation_duration_sec": 10
  }
}

POST /api/recipes/1/phases
{
  "phase_index": 1,
  "name": "Vegetative",
  "duration_hours": 336,
  "targets": {
    "ph": 5.8,
    "ec": 1.4,
    "temp_air": 23,
    "humidity_air": 60,
    "light_hours": 16,
    "irrigation_interval_sec": 720,
    "irrigation_duration_sec": 12
  }
}

POST /api/recipes/1/phases
{
  "phase_index": 2,
  "name": "Harvest",
  "duration_hours": 168,
  "targets": {
    "ph": 6.0,
    "ec": 1.6,
    "temp_air": 24,
    "humidity_air": 55,
    "light_hours": 12,
    "irrigation_interval_sec": 600,
    "irrigation_duration_sec": 15
  }
}
```

#### 4. Создать зону

```bash
POST /api/zones
{
  "greenhouse_id": 1,
  "name": "Zone A",
  "description": "NFT system A",
  "status": "RUNNING"
}
```

#### 5. Привязать рецепт к зоне

```bash
POST /api/zones/1/attach-recipe
{
  "recipe_id": 1,
  "start_at": "2025-11-21T10:00:00Z"
}
```

#### 6. Зарегистрировать и привязать узлы

```bash
# Регистрация узла (обычно делается автоматически через MQTT)
POST /api/nodes/register
{
  "uid": "node-001",
  "hardware_id": "ESP32-ABC123",
  "type": "sensor",
  "fw_version": "2.0.1"
}

# Привязка к зоне
PATCH /api/nodes/1
{
  "zone_id": 1,
  "name": "pH/EC Sensor Zone A"
}

# Конфиг узла публикуется самой нодой (config_report)
GET /api/nodes/1/config
```

#### 7. Проверить состояние

```bash
GET /api/zones/1/health
GET /api/zones/1/cycles
GET /api/zones/1/telemetry/last
```

---

## Заключение

Этот документ описывает полный workflow создания и настройки системы выращивания от создания теплицы до запуска автоматизированной зоны с рецептом и узлами.

**Важные моменты:**

1. **Порядок операций важен:** Сначала создайте теплицу и рецепт, затем зону, затем привязывайте рецепт и узлы
2. **Рецепт должен иметь фазы:** Без фаз рецепт не может быть применен к зоне
3. **Узлы регистрируются автоматически:** ESP32 узлы регистрируются через MQTT при первом подключении
4. **Конфигурация узлов приходит от нод:** Сервер хранит `config_report`, редактирование отключено
5. **automation-engine работает автоматически:** После привязки рецепта automation-engine начинает управление зоной

**Следующие шаги для реализации:**

1. Создайте UI компоненты для каждого шага
2. Реализуйте валидацию на frontend
3. Добавьте обработку ошибок
4. Реализуйте realtime обновления через WebSocket (Laravel Reverb)
5. Добавьте визуализацию телеметрии и состояния зон
