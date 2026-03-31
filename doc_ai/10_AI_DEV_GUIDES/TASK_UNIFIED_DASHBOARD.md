# TASK: Объединённый зоноцентричный дашборд (Вариант Б)

**Дата:** 2026-03-31  
**Статус:** Спецификация задачи для ИИ-агента  
**Роль:** Senior frontend-разработчик + Laravel backend  
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

---

## 0. Контекст и мотивация

Две страницы с 80% пересечением данных:

| Страница | URL | Файл | Данные |
|----------|-----|-------|--------|
| Dashboard | `/` | `Pages/Dashboard/Index.vue` | KPI, теплицы, проблемные зоны, мини-телеметрия ECharts, events sidebar, 5 ролевых вариантов |
| Центр циклов | `/cycles` | `Pages/Cycles/Center.vue` | KPI циклов, карточки зон с прогрессом цикла + телеметрия + фильтры + действия |

**Проблема:** оператор/агроном вынужден переключаться. Дублируются KPI, телеметрия зон, алерты, quick actions.

**Решение:** Единая страница `/`, каждая зона — карточка mini command center с gauge (pH/EC/T°), sparkline, прогрессом цикла и действиями. Страница `/cycles` → redirect на `/`.

---

## 1. Целевой wireframe

```
┌──────────────────────────────────────────────────────────────────┐
│ Hero: «Операционный центр» + кнопки [Рецепты] [Запустить цикл]   │
│ KPI: 6 метрик (зоны run/warn/alarm, циклы, устройства, алерты)   │
├──────────────────────────────────────────────────────────────────┤
│ Фильтры: [Поиск...] [Статус зоны ▼] [Теплица ▼]                 │
│          [Только алерты] [Компактный/Стандартный вид]             │
├──────────────────────────────────┬───────────────────────────────┤
│ Сетка карточек зон (1–3 колонки) │ Sidebar: лента событий (Live) │
│ ┌──────────────────────────────┐ │ ┌───────────────────────────┐ │
│ │ «Рассада-1» ● RUNNING       │ │ │ [ALL][ALERT][WARN][INFO]   │ │
│ │ Салат · ТП-1 · Устр: 4/4    │ │ │                           │ │
│ │ Фаза: Вегетация д.12/28 67% │ │ │ 14:32 ALERT pH drift z3  │ │
│ │ ┌─pH──┐ ┌─EC──┐ ┌─T°─┐     │ │ │ 14:28 INFO irrigation z1 │ │
│ │ │gauge│ │gauge│ │gau │     │ │ │ 14:15 WARN node offline  │ │
│ │ └─────┘ └─────┘ └────┘     │ │ │ ...                       │ │
│ │ ▂▃▅▆▇ sparkline pH 24h     │ │ └───────────────────────────┘ │
│ │ ⚡ AI: pH стабилен           │ │                               │
│ │ [💧Полив] [⏸Пауза] [↗Зона] │ │                               │
│ └──────────────────────────────┘ │                               │
│ ... ещё карточки + пагинация     │                               │
├──────────────────────────────────┴───────────────────────────────┤
│ Модалки: ZoneActionModal, ConfirmModal (harvest), ConfirmModal   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Пошаговый план

### Шаг 1. Backend: `UnifiedDashboardService.php`

**Создать файл:** `app/Services/UnifiedDashboardService.php`

Объединяет данные из замыкания дашборда (`routes/web.php:327-623`) и `CycleCenterService.php`.

**Зависимости (inject):**
- `GrowCyclePresenter` — DTO цикла (метод `buildCycleDto($cycle)`)
- `ZoneFrontendTelemetryService` — телеметрия зон (метод `getZoneSnapshots($zoneIds, true)`)
- `EffectiveTargetsService` — targets для gauge (метод `getEffectiveTargets($growCycleId)`)

**Главный метод `getData(User $user): array`:**

```php
public function getData($user): array
{
    $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);

    // 1. Загрузить зоны с eager load
    $zones = Zone::query()
        ->with([
            'greenhouse:id,name',
            'activeGrowCycle.currentPhase',
            'activeGrowCycle.recipeRevision.recipe:id,name',
            'activeGrowCycle.plant:id,name',
        ])
        ->withCount([
            'alerts as alerts_count' => fn ($q) => $q->where('status', 'ACTIVE'),
            'nodes as nodes_total',
            'nodes as nodes_online' => fn ($q) => $q->where('status', 'online'),
        ])
        ->when(!$user?->isAdmin(), fn ($q) => $q->whereIn('id', $accessibleZoneIds ?: [0]))
        ->orderByRaw("CASE status WHEN 'ALARM' THEN 1 WHEN 'WARNING' THEN 2 WHEN 'RUNNING' THEN 3 WHEN 'PAUSED' THEN 4 ELSE 5 END")
        ->orderBy('name')
        ->get();

    $zoneIds = $zones->pluck('id')->toArray();

    // 2. Телеметрия
    $telemetryByZone = $this->zoneFrontendTelemetry->getZoneSnapshots($zoneIds, true);

    // 3. Алерты (preview: top-2 на зону)
    $alertsByZone = $this->getAlertsByZone($zoneIds); // как в CycleCenterService

    // 4. Targets из EffectiveTargetsService
    $targetsByZone = $this->getTargetsByZone($zones);

    // 5. Последние алерты для sidebar
    $latestAlerts = $this->getLatestAlerts($user, $accessibleZoneIds);

    // 6. KPI summary
    $summary = $this->buildSummary($zones);

    // 7. Форматировать зоны
    $zonesData = $this->formatZones($zones, $telemetryByZone, $alertsByZone, $targetsByZone);

    // 8. Теплицы для фильтра
    $greenhouses = $this->getGreenhouses($zones);

    return compact('summary', 'zonesData', 'greenhouses', 'latestAlerts');
}
```

**Метод `getTargetsByZone`** — ключевое новое:

```php
private function getTargetsByZone(Collection $zones): array
{
    $targetsByZone = [];
    foreach ($zones as $zone) {
        $cycle = $zone->activeGrowCycle;
        if (!$cycle) {
            $targetsByZone[$zone->id] = ['ph' => null, 'ec' => null, 'temperature' => null];
            continue;
        }
        try {
            $effective = $this->effectiveTargetsService->getEffectiveTargets($cycle->id);
            $targets = $effective['targets'] ?? [];
            $targetsByZone[$zone->id] = [
                'ph' => isset($targets['ph']) ? ['min' => $targets['ph']['min'] ?? null, 'max' => $targets['ph']['max'] ?? null] : null,
                'ec' => isset($targets['ec']) ? ['min' => $targets['ec']['min'] ?? null, 'max' => $targets['ec']['max'] ?? null] : null,
                'temperature' => isset($targets['climate_request']['temp_air_target'])
                    ? ['min' => ($targets['climate_request']['temp_air_target'] - 2), 'max' => ($targets['climate_request']['temp_air_target'] + 2)]
                    : null,
            ];
        } catch (\Exception $e) {
            $targetsByZone[$zone->id] = ['ph' => null, 'ec' => null, 'temperature' => null];
        }
    }
    return $targetsByZone;
}
```

**Контракт `summary`:**

```php
[
    'zones_total'       => int,
    'zones_running'     => int,
    'zones_warning'     => int,
    'zones_alarm'       => int,
    'cycles_running'    => int,
    'cycles_paused'     => int,
    'cycles_planned'    => int,
    'cycles_none'       => int,
    'devices_online'    => int,
    'devices_total'     => int,
    'alerts_active'     => int,
    'greenhouses_count' => int,
]
```

**Контракт `zonesData` (каждый элемент):**

```php
[
    'id'              => int,
    'name'            => string,
    'status'          => string,     // RUNNING|PAUSED|ALARM|WARNING|IDLE|NEW
    'greenhouse'      => ['id' => int, 'name' => string] | null,
    'telemetry'       => ['ph' => ?float, 'ec' => ?float, 'temperature' => ?float, 'humidity' => ?float, 'co2' => ?float, 'updated_at' => ?string],
    'targets'         => ['ph' => ['min' => ?float, 'max' => ?float], 'ec' => [...], 'temperature' => [...]],
    'alerts_count'    => int,
    'alerts_preview'  => [['id' => int, 'type' => string, 'details' => string, 'created_at' => string]],
    'devices'         => ['total' => int, 'online' => int],
    'recipe'          => ['id' => int, 'name' => string] | null,
    'plant'           => ['id' => int, 'name' => string] | null,
    'cycle'           => GrowCycleDto | null,  // из GrowCyclePresenter::buildCycleDto()
    'crop'            => string | null,
]
```

**Кэширование:** `Cache::remember("unified_dashboard_{$user->id}", 30, ...)`

**Паттерн скопировать из:** `CycleCenterService.php` (методы `getZones`, `getAlertsByZone`, `buildSummary`, `formatZonesData`, `getGreenhouses` — адаптировать).

---

### Шаг 2. Backend: `UnifiedDashboardController.php`

**Создать файл:** `app/Http/Controllers/UnifiedDashboardController.php`

```php
<?php

namespace App\Http\Controllers;

use App\Services\UnifiedDashboardService;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

class UnifiedDashboardController extends Controller
{
    public function __construct(
        private UnifiedDashboardService $service
    ) {}

    public function index(Request $request): Response
    {
        $user = $request->user();
        $data = $this->service->getData($user);

        return Inertia::render('Dashboard/Index', [
            'auth'         => ['user' => ['role' => $user?->role ?? 'viewer']],
            'summary'      => $data['summary'],
            'zones'        => $data['zonesData'],
            'greenhouses'  => $data['greenhouses'],
            'latestAlerts' => $data['latestAlerts'],
        ]);
    }
}
```

---

### Шаг 3. Backend: Обновить `routes/web.php`

**Заменить замыкание** на строках 327-623:

```php
// Было: Route::get('/', function () { ... 300 строк ... })->name('dashboard');
// Стало:
Route::get('/', [UnifiedDashboardController::class, 'index'])->name('dashboard');
```

**Добавить redirect** (вместо маршрута `cycles.center`):

```php
// Было: Route::get('/cycles', [CycleCenterController::class, 'index'])->name('cycles.center');
// Стало:
Route::redirect('/cycles', '/');
```

**Не забыть:** добавить `use App\Http\Controllers\UnifiedDashboardController;` в импорты.

---

### Шаг 4. Frontend: `composables/useUnifiedDashboard.ts`

**Создать файл:** `resources/js/composables/useUnifiedDashboard.ts`

Объединяет логику из трёх composables:
- `useCycleCenterView.ts` — фильтрация, пагинация, форматтеры
- `useCycleCenterActions.ts` — действия с циклами (pause/resume/harvest/abort/irrigate)
- `useDashboardRealtimeFeed.ts` — лента событий (подключить as-is)

**Типы:**

```typescript
export interface UnifiedSummary {
  zones_total: number
  zones_running: number
  zones_warning: number
  zones_alarm: number
  cycles_running: number
  cycles_paused: number
  cycles_planned: number
  cycles_none: number
  devices_online: number
  devices_total: number
  alerts_active: number
  greenhouses_count: number
}

export interface ZoneTargetRange {
  min: number | null
  max: number | null
}

export interface UnifiedZone {
  id: number
  name: string
  status: string
  greenhouse: { id: number; name: string } | null
  telemetry: {
    ph: number | null
    ec: number | null
    temperature: number | null
    humidity: number | null
    co2: number | null
    updated_at: string | null
  }
  targets: {
    ph: ZoneTargetRange | null
    ec: ZoneTargetRange | null
    temperature: ZoneTargetRange | null
  }
  alerts_count: number
  alerts_preview: Array<{ id: number; type: string; details: string; created_at: string }>
  devices: { total: number; online: number }
  recipe: { id: number; name: string } | null
  plant: { id: number; name: string } | null
  cycle: {
    id: number
    status: string
    planting_at?: string | null
    expected_harvest_at?: string | null
    current_stage?: { code?: string; name?: string; started_at?: string | null } | null
    progress?: { overall_pct?: number; stage_pct?: number }
    stages?: Array<{ code: string; name: string; from: string; to?: string | null; pct: number; state: string }>
  } | null
  crop: string | null
}

export interface Greenhouse {
  id: number
  name: string
}
```

**Функционал (объединение):**

Из `useCycleCenterView`:
- `query`, `statusFilter`, `greenhouseFilter`, `showOnlyAlerts`, `denseView` — refs
- `filteredZones`, `pagedZones` — computed
- `currentPage`, `perPage`, `toggleDense`
- `formatMetric`, `formatDate`, `formatTime`, `getZoneStatusVariant`

Из `useCycleCenterActions` (взять целиком, переименовать options):
- `harvestModal`, `abortModal`, `actionModal`
- `isActionLoading`, `pauseCycle`, `resumeCycle`
- `openHarvestModal`, `closeHarvestModal`, `confirmHarvest`
- `openAbortModal`, `closeAbortModal`, `confirmAbort`
- `openActionModal`, `closeActionModal`, `submitAction`

Из `useDashboardRealtimeFeed` — подключить для sidebar:
- `eventFilter`, `filteredEvents`

**Sparklines** (паттерн из `AgronomistDashboard`):

```typescript
const sparklines = ref<Record<number, number[]>>({})
const { fetchHistory } = useTelemetry()

function loadSparklines(zones: UnifiedZone[]) {
  zones.forEach((zone, i) => {
    if (sparklines.value[zone.id]) return
    setTimeout(async () => {
      try {
        const now = new Date()
        const from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
        const history = await fetchHistory(zone.id, 'PH', {
          from: from.toISOString(),
          to: now.toISOString(),
        })
        if (history.length > 0) {
          sparklines.value = { ...sparklines.value, [zone.id]: history.map(p => p.value) }
        }
      } catch { /* non-critical */ }
    }, i * 200)
  })
}

// watch pagedZones → loadSparklines(newPagedZones)
```

---

### Шаг 5. Frontend: `Components/ZoneDashboardCard.vue`

**Создать файл:** `resources/js/Components/ZoneDashboardCard.vue`

Объединяет лучшее из `AgronomistDashboard` (карточка с gauge/sparkline/AI) и `Cycles/Center.vue` (прогресс цикла, действия).

**Props:**

```typescript
interface Props {
  zone: UnifiedZone
  canManageCycle: boolean
  canIssueCommands: boolean
  sparklineData: number[] | null
  isActionLoading: (zoneId: number, action: string) => boolean
}
```

**Emits:** `'pause'`, `'resume'`, `'irrigate'`, `'flush'`, `'harvest'`, `'abort'`

**Структура template:**

1. **Header** — имя зоны (Link на `/zones/{id}`), Badge статуса, Badge цикла. Подзаголовок: теплица, культура/рецепт, устройства `online/total`. Чип алертов справа.

2. **Phase progress strip** (v-if zone.cycle) — имя стадии, дни elapsed/total, progress bar. Скопировать из `AgronomistDashboard:140-156`.

3. **Gauges row** — `ZoneHealthGauge` × 3 (pH, EC, T°C) с target ranges из `zone.targets`. Скопировать layout из `AgronomistDashboard:159-193`.

4. **Sparkline + AI** — `Sparkline` (v-if sparklineData) + `ZoneAIPredictionHint`. Скопировать из `AgronomistDashboard:197-223`.

5. **Alerts preview** (v-if zone.alerts_preview.length) — компактный список. Скопировать из `Cycles/Center.vue:292-306`.

6. **Actions footer** — кнопки по условиям. Скопировать логику из `Cycles/Center.vue:308-378`.

**Используемые компоненты (все существующие, без изменений):**
- `ZoneHealthGauge` — props: `value`, `targetMin`, `targetMax`, `globalMin`, `globalMax`, `label`, `unit`, `decimals`
- `Sparkline` — props: `data: number[]`, `width`, `height`, `color`, `showArea`, `strokeWidth`
- `ZoneAIPredictionHint` — props: `zoneId`, `metricType`, `targetMin`, `targetMax`, `horizonMinutes`
- `Badge`, `Button`, `Link`

---

### Шаг 6. Frontend: Переписать `Pages/Dashboard/Index.vue`

**Полная замена содержимого.** Новые props:

```typescript
interface Props {
  summary: UnifiedSummary
  zones: UnifiedZone[]
  greenhouses: Greenhouse[]
  latestAlerts: Alert[]
}
```

**Template — три секции внутри `<AppLayout>`:**

**`#default` slot:**

1. **Hero section** (`section.ui-hero.p-6`):
   - Заголовок «Операционный центр»
   - Кнопки: «Фазы и рецепты» → `/recipes` (roles: admin, agronomist), «Запустить цикл» → `/grow-cycle-wizard` (roles: admin, agronomist, operator)
   - KPI grid (`ui-kpi-grid`, 6 карточек): zones_running, zones_warning, zones_alarm, cycles_running, devices_online/total, alerts_active
   - Стили KPI: скопировать из `Cycles/Center.vue:35-84`

2. **Фильтры** (`section.surface-card`):
   - Скопировать из `Cycles/Center.vue:87-148`, добавить фильтр по статусу зоны (RUNNING/PAUSED/WARNING/ALARM) вместо статуса цикла

3. **Пустое состояние** (v-if summary.zones_total === 0): карточка «Создайте теплицу» с Link на `/greenhouses`

4. **Сетка карточек** (`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4`):
   - `ZoneDashboardCard` × pagedZones

5. **Пагинация**: `Pagination` (из `Cycles/Center.vue:389-394`)

6. **Модалки**: `ZoneActionModal`, 2× `ConfirmModal` (harvest, abort) — скопировать из `Cycles/Center.vue:397-449`

**`#context` slot** — лента событий:
- Скопировать из текущего `Dashboard/Index.vue:473-551` (фильтры ALL/ALERT/WARNING/INFO + список событий)

**Что убрать:**
- Все импорты ролевых дашбордов (`AgronomistDashboard`, `AdminDashboard`, `EngineerDashboard`, `OperatorDashboard`, `ViewerDashboard`)
- Всю логику `useRole()` для выбора ролевого дашборда
- Секции: теплицы, проблемные зоны, мини-телеметрия ECharts, heatmap
- Импорты: `MetricIndicator`, `StatusIndicator`, `MiniTelemetryChart`, `ZonesHeatmap`
- Composable `useDashboardPage` — заменить на `useUnifiedDashboard`

---

### Шаг 7. Frontend: Обновить навигацию

**`Components/RoleBasedNavigation.vue`** (строка 26-27):

```typescript
// Было:
{ href: '/', label: 'Дашборд' },
{ href: '/cycles', label: 'Центр циклов' },

// Стало:
{ href: '/', label: 'Операционный центр' },
```

**`Components/MobileNavigation.vue`** (строки 33-52):

Убрать NavLink на `/cycles` (блок с svg-иконкой и label «Циклы»).

---

### Шаг 8. Проверка

```bash
# Внутри контейнера laravel:
php artisan test --filter=Dashboard
php artisan test --filter=CycleCenter

# Frontend:
cd backend/laravel
npm run typecheck
npm run lint

# Проверить в браузере:
# 1. Открыть / — должна быть объединённая страница
# 2. Открыть /cycles — должен редиректить на /
# 3. Проверить фильтры, пагинацию, действия
# 4. Проверить мобильную навигацию
```

---

## 3. Ограничения

- **НЕ менять** MQTT протокол, форматы команд, схемы БД, Python-сервисы
- **НЕ менять** существующие API endpoints (только Inertia routes)
- **НЕ удалять** файлы: `Cycles/Center.vue`, `Dashboards/*.vue`, старые composables, `CycleCenterService.php`, `CycleCenterController.php` — убрать только импорты/маршруты
- **НЕ менять** компоненты: `ZoneHealthGauge`, `Sparkline`, `ZoneAIPredictionHint`, `Badge`, `Button`, `AppLayout`
- Действия с циклами: те же API endpoints (`POST /api/grow-cycles/{id}/pause|resume|harvest|abort`, `POST /api/zones/{id}/start-irrigation`)

---

## 4. Критерии приёмки

1. `/` — объединённая страница; каждая карточка зоны: gauge pH/EC/T°, sparkline, прогресс цикла, действия
2. `/cycles` → redirect на `/`
3. Фильтры работают: поиск, статус зоны, теплица, только алерты
4. Пагинация работает; переключатель компактный/стандартный вид
5. Actions: пауза/возобновить цикл, полив, промывка, сбор, аварийный стоп
6. Sidebar «Последние события» с live-обновлениями
7. Навигация: нет пункта «Центр циклов» (desktop + mobile)
8. `npm run typecheck` — ОК
9. `npm run lint` — ОК
10. Работает для всех ролей: admin, agronomist, operator, engineer, viewer
11. AI prediction hints загружаются (graceful degradation если API недоступен)
12. Targets в gauge берутся из `EffectiveTargetsService` (через бэкенд)

---

## 5. Входные файлы

### Backend (читать обязательно):

| Файл | Зачем |
|------|-------|
| `routes/web.php:327-623` | Замыкание дашборда — заменить на контроллер |
| `routes/web.php:761` | Маршрут cycle center — заменить на redirect |
| `app/Services/CycleCenterService.php` | **Шаблон**: методы `getZones`, `getAlertsByZone`, `buildSummary`, `formatZonesData`, `getGreenhouses` |
| `app/Services/EffectiveTargetsService.php` | Метод `getEffectiveTargets($growCycleId)` → targets.ph, targets.ec, targets.climate_request |
| `app/Services/GrowCyclePresenter.php` | Метод `buildCycleDto($cycle)` → DTO цикла с progress/stages |
| `app/Services/ZoneFrontendTelemetryService.php` | Метод `getZoneSnapshots($zoneIds, true)` → телеметрия |
| `app/Helpers/ZoneAccessHelper.php` | `getAccessibleZoneIds($user)` — фильтрация доступа |
| `app/Http/Controllers/CycleCenterController.php` | Шаблон контроллера |

### Frontend (читать обязательно):

| Файл | Зачем |
|------|-------|
| `Pages/Dashboard/Index.vue` | Текущий дашборд — **полностью переписать** |
| `Pages/Cycles/Center.vue` | Текущий Cycle Center — **скопировать**: фильтры, карточки, модалки, actions |
| `Pages/Dashboard/Dashboards/AgronomistDashboard.vue` | **Скопировать**: карточка с gauge/sparkline/AI, phase progress, zone sorting |
| `composables/useCycleCenterView.ts` | **Скопировать**: фильтрация, пагинация, форматтеры |
| `composables/useCycleCenterActions.ts` | **Скопировать**: все действия с циклами |
| `composables/useDashboardRealtimeFeed.ts` | **Подключить as-is**: eventFilter, filteredEvents |
| `composables/useTelemetry.ts` | Метод `fetchHistory()` для sparklines |
| `Components/ZoneHealthGauge.vue` | Props: value, targetMin, targetMax, globalMin, globalMax, label, unit, decimals |
| `Components/Sparkline.vue` | Props: data, width, height, color, showArea, strokeWidth |
| `Components/ZoneAIPredictionHint.vue` | Props: zoneId, metricType, targetMin, targetMax, horizonMinutes |
| `Components/RoleBasedNavigation.vue` | Убрать пункт `/cycles` |
| `Components/MobileNavigation.vue` | Убрать NavLink `/cycles` |
| `utils/growCycleStatus.ts` | Утилиты `getCycleStatusLabel`, `getCycleStatusVariant` |
| `utils/i18n.ts` | Утилита `translateStatus` |

### Документация (контекст):

| Файл | Зачем |
|------|-------|
| `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` | Структура targets: `ph.target/min/max`, `ec.target/min/max`, `climate_request.temp_air_target` |
| `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md` | Архитектура UI |

---

## 6. Диаграмма потока данных

```
PostgreSQL
  ├── zones (status, greenhouse_id)
  ├── grow_cycles + grow_cycle_phases + recipe_revision_phases (targets)
  ├── telemetry_last + sensors (ph, ec, temperature, humidity, co2)
  ├── alerts (status=ACTIVE)
  └── nodes (status)
       │
       ▼
UnifiedDashboardService.php
  ├── Zone::query() + eager load
  ├── ZoneFrontendTelemetryService::getZoneSnapshots()
  ├── EffectiveTargetsService::getEffectiveTargets() per cycle
  ├── Alert::query() grouped by zone_id
  ├── GrowCyclePresenter::buildCycleDto() per cycle
  └── Cache::remember(30s)
       │
       ▼
UnifiedDashboardController → Inertia::render('Dashboard/Index')
  Props: { summary, zones, greenhouses, latestAlerts }
       │
       ▼
Dashboard/Index.vue
  ├── useUnifiedDashboard(props)
  │   ├── фильтрация (query, status, greenhouse, alerts)
  │   ├── пагинация (currentPage, perPage, toggleDense)
  │   ├── sparklines (lazy load, staggered 200ms)
  │   ├── actions (pause/resume/harvest/abort/irrigate via API)
  │   └── events (useDashboardRealtimeFeed → WebSocket)
  │
  ├── ZoneDashboardCard.vue × N (pagedZones)
  │   ├── ZoneHealthGauge × 3 (pH, EC, T°C + target ranges)
  │   ├── Sparkline (pH 24h)
  │   ├── ZoneAIPredictionHint (AI forecast)
  │   ├── Phase progress bar
  │   ├── Alerts preview
  │   └── Action buttons
  │
  └── Events sidebar (#context slot, live via WebSocket)
```
