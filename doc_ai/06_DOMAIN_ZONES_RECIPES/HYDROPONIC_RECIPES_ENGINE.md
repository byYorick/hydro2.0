# HYDROPONIC_RECIPES_ENGINE.md
# Полная спецификация рецептов (Росовых фаз), целей и параметров зоны
# Инструкция для ИИ‑агентов, backend Laravel, Python‑контроллеров и UI

Документ описывает систему **рецептов выращивания** (phases/recipes),
которые определяют цели pH, EC, климат, полив и свет в каждой зоне.

---

# 1. Общая концепция рецептов (Recipes)

Рецепт — это программа роста культуры, состоящая из фаз.

Каждая **фаза** содержит:
- цели pH, EC,
- климатические параметры,
- расписание света и фотопериод,
- режимы полива,
- длительность фазы (в часах или днях).

Pipeline рецепта:

```
Recipe → Phases → Zone_Recipe_Instance → Zone Controllers
```

---

# 2. Структура в PostgreSQL

## 2.1. recipes

```sql
CREATE TABLE recipes (
 id BIGSERIAL PRIMARY KEY,
 name VARCHAR(128) NOT NULL,
 description TEXT,
 created_at TIMESTAMP DEFAULT now()
);
```

## 2.2. recipe_phases

```sql
CREATE TABLE recipe_phases (
 id BIGSERIAL PRIMARY KEY,
 recipe_id BIGINT REFERENCES recipes(id) ON DELETE CASCADE,
 phase_index INT NOT NULL,
 name VARCHAR(128),
 duration_hours INT NOT NULL,
 targets JSONB NOT NULL,
 created_at TIMESTAMP DEFAULT now()
);
```

### targets JSON пример:

```json
{
 "ph": 5.8,
 "ec": 1.4,
 "temp_air": 23,
 "humidity_air": 65,
 "light_hours": 16,
 "irrigation_interval_sec": 900,
 "irrigation_duration_sec": 8
}
```

## 2.3. zone_recipe_instances

```sql
CREATE TABLE zone_recipe_instances (
 id BIGSERIAL PRIMARY KEY,
 zone_id BIGINT REFERENCES zones(id) ON DELETE CASCADE,
 recipe_id BIGINT REFERENCES recipes(id),
 current_phase_index INT NOT NULL DEFAULT 0,
 started_at TIMESTAMP NOT NULL,
 updated_at TIMESTAMP NOT NULL DEFAULT now()
);
```

---

# 3. Как рассчитывается текущая фаза

На основе:

```
phase_start_time = started_at + Σ(previous phase durations)
```

Если:

```
now >= phase_start_time + current_phase.duration
```

→ переход к следующей фазе.

Python-сервис выполняет каждые 60 сек:

```python
check_phase_progress(zone)
```

Transition event:

```
RECIPE_PHASE_CHANGED { from: X, to: X+1 }
```

Laravel отображает фазу на UI.

---

# 4. Targets: цели контроллеров по фазам

Каждый контроллер получает свои цели из `targets` текущей фазы.

## 4.1. PH targets

```
target_ph = targets["ph"]
```

Используется pH controller.

## 4.2. EC targets

```
target_ec = targets["ec"]
```

Используется EC controller.

## 4.3. Climate targets

```
temp_air
humidity_air
```

Используются Climate controller.

## 4.4. Lighting targets

```
light_hours
photoperiod_start
(optional) sunrise_gradual_minutes
(optional) sunset_gradual_minutes
```

## 4.5. Irrigation targets

```
irrigation_interval_sec
irrigation_duration_sec
```

---

# 5. Как работают рецепты с контроллерами

Pipeline:

1. Python читает `zone_recipe_instances`
2. Находит текущую фазу по времени
3. Берёт targets из `recipe_phases`
4. Передаёт эти цели в контроллеры:
 - pH Controller
 - EC Controller
 - Climate Controller
 - Irrigation Controller
 - Lighting Controller
5. Контроллеры сравнивают фактические данные с targets

Контроллеры **не знают про рецепты** напрямую. 
Они получают уже готовые targets.

---

# 6. Логика перехода фаз (Phase Engine)

## 6.1. Условия перехода

Фаза завершается, если:

```
now >= started_at + Σ(durations)
```

## 6.2. Действия при переходе

Python:

- обновляет `current_phase_index`
- создаёт событие:
 ```
 RECIPE_PHASE_CHANGED
 ```
- обновляет все контроллеры

Laravel:

- обновляет UI
- показывает новую фазу
- может отправлять Push/Telegram уведомление (опционально)

---

# 7. Создание пользовательских рецептов (UI)

Laravel Inertia → Vue интерфейс должен обеспечивать:

- создание рецептов,
- добавление фаз,
- настройку параметров:

UI panels:

1. **Описание рецепта**
2. **Фазы**
3. **На каждый параметр:**
 - pH
 - EC
 - Температура
 - Влажность
 - Свет
 - Полив
 - Дополнительные параметры климата
4. **Клонирование рецептов**
5. **Экспорт/импорт рецептов (JSON)**

---

# 8. Advanced параметры рецептов (опционально)

Для 2.0 можно добавить:

### 8.1. VPD targets (vapor pressure deficit)

Цель `vpd_target` помогает точному климат-контролю.

### 8.2. Dynamic EC

EC при росте можно повышать плавно:

```
ec(t) = ec_base + (ec_final - ec_base) * (t / duration)
```

### 8.3. Adaptive irrigation

Полив может зависеть от:

- интенсивности света,
- возраста растения,
- фактического расхода воды,
- температуры.

ИИ может предложить адаптивные модели.

---

# 9. Правила для ИИ

ИИ может:

- добавлять новые параметры в `targets`,
- улучшать расчёты текущей фазы,
- вводить ML-модели адаптивного роста,
- создавать новые UI-редакторы фаз,
- делать экспорт/импорт JSON рецептов.

ИИ не может:

- менять структуру таблиц без backward-compatibility,
- менять смысл ключей (например, light_hours = часы света),
- нарушать переход фаз.

---

# 10. Чек-лист перед редактированием Recipes Engine

1. Все фазы имеют duration_hours > 0? 
2. Все targets содержат pH/EC/климат? 
3. Контроллеры получают корректные данные? 
4. Переход фаз не нарушает график? 
5. В UI значения отображаются корректно? 
6. Новые параметры поддерживаются на всех уровнях: 
 - PostgreSQL 
 - Python 
 - Laravel 
 - Vue 
7. Нет break-change в структуре targets? 

---

# Конец файла HYDROPONIC_RECIPES_ENGINE.md
