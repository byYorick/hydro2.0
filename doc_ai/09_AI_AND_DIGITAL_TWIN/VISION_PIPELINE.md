# VISION_PIPELINE.md
# План внедрения Computer Vision слоя для hydro2.0
# Мониторинг роста • Дефициты по цвету • Болезни и вредители • Подсчёт плодов/цветов
# Культура MVP: клубника · Обзор сверху · Инференс на сервере

**Статус:** DRAFT · предложение к внедрению
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/VISION_PIPELINE.md`
**Связанные документы:**
- `doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md` — ML-слой по pH/EC/телеметрии (основа)
- `doc_ai/05_DATA_AND_STORAGE/TELEMETRY_PIPELINE.md` — MQTT/Postgres инварианты
- `doc_ai/05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md` — политика хранения
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
**Breaking-change:** нет (additive DDL, новые сервисы, новый MQTT topic `.../camera/event`)

---

## 0. Назначение документа

Документ описывает, как добавить в hydro2.0 **визуальный канал** наблюдения за
растением — камеру на узле, сбор кадров, inference на сервере, витрины для ML,
интеграцию с существующим feature pipeline.

Для **человека** — дорожная карта с железом, фазами, стоимостью.
Для **ИИ-агента** — спецификация контрактов данных, таблиц и сервисов,
позволяющая генерировать миграции, обработчики и тесты.

Документ идеологически пристыкован к `ML_FEATURE_PIPELINE.md`: те же принципы
owner'ства витрин, versioning, point-in-time correctness, safety.

---

## 1. Цели

### 1.1. Бизнес-цели (клубника, гидропоника)

- Детектить **tip-burn** (Ca-дефицит из-за высокой EC) и другие дефициты
  минимум на 24–48 часов раньше, чем их заметит оператор глазами.
- Детектить **мучнистую росу** (Podosphaera aphanis) и **ботритис** с
  precision ≥ 0.85 на инфицированных листьях в течение 48 часов после
  появления первых признаков.
- Отслеживать **скорость роста** (площадь проекции, LAI-прокси) с точностью
  ±5% и строить кривую по циклу.
- Считать **цветы и плоды** по стадиям зрелости (flower / green / white /
  turning / ripe) для прогноза урожая на 7–14 дней.

### 1.2. Технические цели

- Один узел с камерой на зону публикует кадры раз в N минут (рекомендация: 15).
- Кадры попадают в object-storage, а в БД пишется только метаданные и ссылка.
- Сервис `vision-analyzer` извлекает признаки и складывает в ML-ready витрины.
- Визуальные фичи агрегируются в `plant_visual_features_1h` и
  **соединяются** с химическими фичами `zone_features_5m` из
  `ML_FEATURE_PIPELINE.md` через `zone_id + time_bucket`.
- Весь inference на сервере (выбор пользователя). Узел — тупой «глаз».

### 1.3. Не-цели (вне скоупа этого документа)

- Автоматическое распыление химии/биопрепаратов по данным CV (только alert'ы).
- Edge inference на узле (решено запускать на сервере).
- Обучение моделей (runbook'и в `tools/ml/vision/`, появятся в Phase 4).
- Анализ подземной части растения (корневая зона — отдельная тема).

---

## 2. Текущее состояние (ревизия `ae3`)

На момент написания в проекте **нет** визуального канала:
- нет camera-узлов ни в `firmware/`, ни в `tests/node_sim/`;
- нет `camera` в списках metric_type / channel;
- нет object storage в `infra/docker/`;
- `AI_ARCH_FULL.md` (§4.2) упоминает анализ pH/EC/климата, но не CV.

Что можем переиспользовать:
- MQTT-схема топиков (`hydro/{gh}/{zone}/{node}/{channel}/...`) — расширяется
  каналом `camera` без breaking change.
- Таблица `sensors` — добавляется новый `type='CAMERA'`.
- Python-сервисы по common-шаблону (логирование, метрики, asyncpg).
- `zone_events` — для событий вроде `VISION_DISEASE_DETECTED`,
  `VISION_CALIBRATION_NEEDED`.
- `automation-engine` advisory-паттерн (из §12 ML_FEATURE_PIPELINE) — для
  рекомендаций от CV.

---

## 3. Гэпы и уникальные сложности (клубника + top-down)

| # | Проблема | Решение в плане |
|---|---|---|
| V1 | **Плоды закрыты листьями** при top-down | MVP: считаем то, что видно; заявляем что этот KPI имеет lower bound, не точную цифру. Roadmap: угловая/боковая камера в Phase 6 |
| V2 | **Цвет нестабилен** без калибровки (LED, белый баланс, возраст ламп) | Обязательный X-Rite ColorChecker Passport или 24-патч цветовая карта в кадре. Auto-WB по карте при каждом снимке |
| V3 | **Пиксели ≠ миллиметры** без геометрической калибровки | ArUco-маркеры (4 угла зоны) → homography → реальная площадь в см² |
| V4 | **LED цикл** меняет спектр в кадре | Снимки строго в окно «lights-on +2h / -1h перед выключением», синхронизированы с `automation-engine` |
| V5 | **Tip-burn клубники** легко спутать с K-дефицитом по цвету | Анализировать **позицию** повреждения: tip-burn → на молодых листьях, K → на старых. Через per-plant сегментацию + трекинг «свежести» листа |
| V6 | **Разметка** — нет готового датасета именно под top-down гидропонной клубники | Обязательный протокол сбора ground truth оператором через UI + использование предобученного backbone (DINOv2) + fine-tune на своих данных. Детали в §8 |
| V7 | **Трекинг отдельных растений** day-to-day | Растение закрепляется за позицией в зоне (`plant_position_grid`), камера фиксирована → поиск ближайшего детекта к сохранённой позиции |
| V8 | **Мучнистая роса** на ранней стадии = мелкие белые точки, нужен ≥ 1–2 px/мм | Расчёт минимального разрешения камеры (§5.3) |
| V9 | **Большие файлы в MQTT** (Mosquitto default 256KB) | Кадры НЕ идут через MQTT. HTTP POST в `image-ingestor`, через MQTT только событие `new_image` со ссылкой |
| V10 | **GPU не всегда доступен** | Поддержать CPU-only режим (torch) с понижением частоты inference; GPU — опциональное ускорение |

---

## 4. Архитектура (высокоуровнево)

```
┌────────────────────────────┐
│  Camera Node (RPi 5 + Cam) │   1 шт на зону
│  - capture_scheduler        │
│  - quality_prefilter        │  (focus, exposure, lights_on)
│  - metadata builder         │  (aruco_detected, color_chart_detected)
└──────────┬─────────────────┘
           │ HTTPS POST  (bytes + metadata)
           ▼
┌────────────────────────────┐       ┌──────────────────┐
│  image-ingestor (новый)    │──────►│  Object Storage  │
│  - валидация, rate limit   │       │  (MinIO/S3)      │
│  - запись в plant_images   │       └──────────────────┘
│  - publish MQTT event      │
└──────────┬─────────────────┘
           │ MQTT: hydro/{gh}/{zone}/{node}/camera/event
           ▼
┌────────────────────────────┐
│  vision-analyzer (новый)   │   GPU-worker, horizontally scalable
│  - pull image from S3      │
│  - geometric calibration    │  (ArUco → homography)
│  - color calibration        │  (ColorChecker → WB+gain)
│  - plant segmentation       │  (SAM2 / YOLOv11-seg)
│  - per-plant color features │  (LAB, NDI, HSV stats)
│  - disease classifier       │  (DINOv2 + linear head)
│  - fruit detector           │  (YOLOv11)
│  - growth metrics           │  (area, bbox, height-proxy)
└──────────┬─────────────────┘
           │
           ▼
   ┌───────────────────┬────────────────────┬─────────────────────┐
   ▼                   ▼                    ▼                     ▼
plant_detections  plant_disease_     plant_fruit_counts    plant_color_samples
                  predictions
                           │
                           ▼
             feature-builder (расширение из ML_FEATURE_PIPELINE)
                           │
                           ▼
             plant_visual_features_1h       ◄─┐
                           │                  │ JOIN по (zone_id, time_bucket)
             zone_features_5m ────────────────┘
             (из ML_FEATURE_PIPELINE)
                           │
                           ▼
                 Training / Inference / UI
```

**Ключевые принципы:**
- Кадр пересекает сеть максимум один раз (узел → MinIO). Всё остальное —
  ссылки + метаданные. Это радикально снижает трафик и позволяет переигрывать
  inference без повторной съёмки.
- `vision-analyzer` — единственный writer для `plant_detections`,
  `plant_disease_predictions`, `plant_fruit_counts`, `plant_color_samples`.
- `feature-builder` (из `ML_FEATURE_PIPELINE.md`) расширяется и становится
  единственным writer для `plant_visual_features_1h` (агрегат от раз в 15 мин
  до раз в час).
- Кадр никогда не удаляется до того, как из него извлечены все фичи и
  прошёл период ground truth labeling (§10).

---

## 5. Железо узла (рекомендация для 1 камеры на зону)

### 5.1. Спецификация

| Компонент | Рекомендация | Зачем |
|---|---|---|
| SBC | Raspberry Pi 5 4GB | Хватает для JPEG/PNG encode и отправки; есть CSI-2 |
| Камера | Raspberry Pi Camera Module 3 (12 МП, AF) | Автофокус, 4608×2592, достаточно для клубники |
| Крепление | Фикс-штанга, камера строго в надире ±5° | Стабильная геометрия day-to-day |
| Подсветка | Широкоспектральный белый LED-кольцевик с внешним триггером | Вкл только на момент съёмки, всегда одинаковая экспозиция |
| Цветовая карта | X-Rite ColorChecker Passport или 24-патч (~$30) | Обязательна для калибровки цвета |
| ArUco маркеры | 4 маркера DICT_4X4_50 в углах кадра | Геометрическая калибровка, пиксели → мм |
| Кожух | IP54, чёрный матовый внутри | Защита от влаги, антиблик |
| Питание | PoE-адаптер или 5V/3A | PoE предпочтительно — один кабель |

### 5.2. Почему Pi Camera Module 3, а не ESP32-CAM

ESP32-CAM (OV2640) даёт 1600×1200 и очень слабый сенсор — мучнистая роса на
ранней стадии не разрешится, динамический диапазон плохой. Дельта в $30 не
стоит пересъёмки через полгода.

### 5.3. Проверка разрешающей способности

Грядка клубники ~1.2×0.6 м в кадре → 12MP ≈ 4608×2592 = **260 мкм/px в центре**.
Мучнистая роса на ранней стадии — пятнышки 1–2 мм. На изображении это
4–8 px — **минимум для уверенной детекции**. Если зона больше — нужно
либо 2 камеры, либо более высокое разрешение, либо motorized-тур.

### 5.4. Частота съёмки

| Режим | Частота | Зачем |
|---|---|---|
| Standard | 1 раз в 15 минут (в окно «lights-on») | Основной трафик |
| Calibration | 1 раз в час | Отдельно со снимком цветовой карты крупным планом |
| On-demand | по команде из UI | Оператор просит «сфоткай сейчас» |

Объём данных при 15 мин интервале и окне света 16 часов:
**64 кадра/день × 2 МБ ≈ 130 МБ/сутки/зона**, **~47 ГБ/год/зона**.

---

## 6. Схема данных

Все DDL ниже — предложение. Миграция через `backend/laravel/database/migrations/`
с парой up/down. Timescale hypertable — где указано.

### 6.1. `plants` (логическая сущность — отдельное растение)

```sql
CREATE TABLE plants (
  id                    bigserial PRIMARY KEY,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  cycle_id              bigint      REFERENCES grow_cycles(id),
  position_code         varchar(32) NOT NULL,   -- 'A3', 'B7' — логический ID в зоне
  position_x_mm         integer,                -- координата в зоне (от ArUco-калибровки)
  position_y_mm         integer,
  cultivar              varchar(64),            -- 'Albion', 'Monterey' и т.д.
  planted_at            timestamptz NOT NULL,
  removed_at            timestamptz,
  removal_reason        varchar(32),            -- 'harvested'|'diseased'|'scheduled'
  notes                 text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (zone_id, position_code, planted_at)
);
CREATE INDEX plants_zone_active_idx
  ON plants (zone_id) WHERE removed_at IS NULL;
```

### 6.2. `plant_images` (метаданные кадра, сам файл в S3)

```sql
CREATE TABLE plant_images (
  id                    bigserial PRIMARY KEY,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  node_id               bigint      REFERENCES nodes(id),
  captured_at           timestamptz NOT NULL,

  storage_uri           text        NOT NULL,     -- s3://hydro-vision/2026/04/22/zone12/...jpg
  storage_size_bytes    integer     NOT NULL,
  mime_type             varchar(32) NOT NULL,     -- 'image/jpeg'|'image/png'
  width_px              integer     NOT NULL,
  height_px             integer     NOT NULL,
  sha256                varchar(64) NOT NULL,

  -- условия съёмки
  lights_on             boolean,
  lights_hours_since_on numeric(5,2),             -- для фильтра "свежий цикл света"
  exposure_us           integer,
  iso                   integer,
  focus_score           double precision,         -- Laplacian variance, для фильтра blur
  camera_fw             varchar(32),

  -- калибровка
  color_chart_detected  boolean NOT NULL DEFAULT false,
  aruco_detected_count  smallint NOT NULL DEFAULT 0,   -- 0..4
  calibration_id        bigint REFERENCES vision_calibrations(id),

  -- качество
  quality_ok            boolean,                  -- false если blur/wrong lighting/obstructed
  quality_reason        varchar(64),

  schema_version        smallint NOT NULL DEFAULT 1,
  created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX plant_images_zone_ts_idx ON plant_images (zone_id, captured_at DESC);
CREATE INDEX plant_images_quality_idx ON plant_images (zone_id, quality_ok, captured_at DESC);
SELECT create_hypertable('plant_images', 'captured_at', chunk_time_interval => interval '7 days');
```

### 6.3. `vision_calibrations` (snapshots калибровки камеры)

```sql
CREATE TABLE vision_calibrations (
  id                    bigserial PRIMARY KEY,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  valid_from            timestamptz NOT NULL,
  valid_to              timestamptz,             -- NULL = текущая

  -- геометрия
  homography_matrix     jsonb,                    -- 3x3, пиксели → мм
  mm_per_px_center      double precision,
  aruco_dict            varchar(32),

  -- цвет
  color_transform       jsonb,                    -- 3x3 или 3x4 matrix RGB → corrected RGB
  white_balance_gains   jsonb,                    -- {r,g,b}
  reference_illuminant  varchar(16),              -- 'D50'|'D65'|...
  color_chart_type      varchar(32),              -- 'xrite_passport_v2'|'generic_24'

  created_at            timestamptz NOT NULL DEFAULT now(),
  created_by            bigint REFERENCES users(id),
  notes                 text
);
CREATE INDEX vision_cal_zone_valid_idx
  ON vision_calibrations (zone_id, valid_from DESC);
```

### 6.4. `plant_detections` (по одной строке на растение-в-кадре)

```sql
CREATE TABLE plant_detections (
  id                    bigserial PRIMARY KEY,
  image_id              bigint      NOT NULL REFERENCES plant_images(id) ON DELETE CASCADE,
  plant_id              bigint      REFERENCES plants(id),    -- NULL если не удалось связать
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  captured_at           timestamptz NOT NULL,

  bbox_xyxy_px          jsonb       NOT NULL,    -- {x1,y1,x2,y2}
  mask_rle              text,                    -- run-length-encoded mask (опц.)
  mask_storage_uri      text,                    -- или ссылка на PNG-маску

  -- геометрические фичи (после homography)
  area_mm2              double precision,
  bbox_width_mm         double precision,
  bbox_height_mm        double precision,
  centroid_x_mm         double precision,
  centroid_y_mm         double precision,
  canopy_compactness    double precision,        -- area / bbox_area

  -- цветовые фичи (после color calibration), аггрегаты по маске
  lab_l_mean            double precision,
  lab_a_mean            double precision,
  lab_b_mean            double precision,
  lab_l_std             double precision,
  hsv_h_mean            double precision,
  ndi_mean              double precision,        -- (G-R)/(G+R), "зелёность"
  dark_green_ratio      double precision,        -- доля L*<35 в маске
  yellow_ratio          double precision,        -- по HSV порогам
  purple_ratio          double precision,        -- признак P-дефицита

  -- позиционные фичи для распознавания типа дефицита
  tip_burn_score        double precision,        -- повреждение молодых листьев (Ca)
  margin_burn_score     double precision,        -- края старых листьев (K)
  interveinal_score     double precision,        -- интервенальный хлороз (Mg/Fe)

  model_version         varchar(32) NOT NULL,    -- версия сегментатора
  feature_schema_version smallint NOT NULL DEFAULT 1
);
CREATE INDEX plant_det_plant_ts_idx ON plant_detections (plant_id, captured_at DESC);
CREATE INDEX plant_det_zone_ts_idx ON plant_detections (zone_id, captured_at DESC);
```

### 6.5. `plant_disease_predictions`

```sql
CREATE TABLE plant_disease_predictions (
  id                    bigserial PRIMARY KEY,
  detection_id          bigint      NOT NULL REFERENCES plant_detections(id) ON DELETE CASCADE,
  plant_id              bigint      REFERENCES plants(id),
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  captured_at           timestamptz NOT NULL,

  -- вероятности по классам (см. Приложение B)
  probs                 jsonb       NOT NULL,    -- {"healthy":0.82,"powdery_mildew":0.11,...}
  top_class             varchar(64) NOT NULL,
  top_prob              double precision NOT NULL,

  -- localization: где именно на растении
  evidence_regions      jsonb,                   -- [{bbox,score,class},...]

  model_version         varchar(32) NOT NULL,
  inference_latency_ms  integer,
  schema_version        smallint NOT NULL DEFAULT 1
);
CREATE INDEX pdp_plant_ts_idx ON plant_disease_predictions (plant_id, captured_at DESC);
CREATE INDEX pdp_zone_class_idx ON plant_disease_predictions (zone_id, top_class, captured_at DESC);
```

### 6.6. `plant_fruit_counts`

```sql
CREATE TABLE plant_fruit_counts (
  id                    bigserial PRIMARY KEY,
  image_id              bigint      NOT NULL REFERENCES plant_images(id) ON DELETE CASCADE,
  detection_id          bigint      REFERENCES plant_detections(id),
  plant_id              bigint      REFERENCES plants(id),
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  captured_at           timestamptz NOT NULL,

  -- raw counts (что видно; для клубники top-down это lower bound)
  count_flower          integer NOT NULL DEFAULT 0,
  count_green           integer NOT NULL DEFAULT 0,
  count_white           integer NOT NULL DEFAULT 0,
  count_turning         integer NOT NULL DEFAULT 0,
  count_ripe            integer NOT NULL DEFAULT 0,
  count_overripe        integer NOT NULL DEFAULT 0,

  -- отдельные детекты
  detections            jsonb,                   -- [{bbox,class,score,size_mm},...]

  -- признак occlusion — сколько ягод «частично»
  occluded_count        integer NOT NULL DEFAULT 0,
  lower_bound_flag      boolean NOT NULL DEFAULT true,  -- top-down → всегда true

  model_version         varchar(32) NOT NULL,
  schema_version        smallint NOT NULL DEFAULT 1
);
CREATE INDEX pfc_plant_ts_idx ON plant_fruit_counts (plant_id, captured_at DESC);
CREATE INDEX pfc_zone_ts_idx ON plant_fruit_counts (zone_id, captured_at DESC);
```

### 6.7. `plant_visual_features_1h` — главная ML-витрина

**Owner:** `feature-builder`. Аналог `zone_features_5m` из
`ML_FEATURE_PIPELINE.md`, но на уровне «растение × час».

```sql
CREATE TABLE plant_visual_features_1h (
  ts                    timestamptz NOT NULL,
  plant_id              bigint      NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  cycle_id              bigint      REFERENCES grow_cycles(id),
  recipe_phase          varchar(32),

  -- контекст
  days_since_planted    double precision,
  images_used_count     integer,
  valid_images_count    integer,

  -- рост (агрегаты по валидным детектам за час)
  area_mm2_mean         double precision,
  area_mm2_delta_1d     double precision,       -- прирост за 24ч
  area_growth_rate_per_day double precision,    -- % в день
  bbox_width_mm_mean    double precision,
  bbox_height_mm_mean   double precision,

  -- цвет (медиана по валидным детектам)
  lab_l_median          double precision,
  lab_a_median          double precision,
  lab_b_median          double precision,
  ndi_median            double precision,
  yellow_ratio_median   double precision,
  purple_ratio_median   double precision,
  tip_burn_score_max    double precision,
  margin_burn_score_max double precision,
  interveinal_score_max double precision,

  -- плоды/цветы (сумма, с поправкой lower_bound)
  count_flower_sum      integer,
  count_green_sum       integer,
  count_white_sum       integer,
  count_turning_sum     integer,
  count_ripe_sum        integer,

  -- болезни (максимумы вероятностей за час)
  prob_powdery_mildew_max double precision,
  prob_botrytis_max       double precision,
  prob_leaf_scorch_max    double precision,
  prob_anthracnose_max    double precision,
  prob_spider_mite_max    double precision,
  prob_aphid_max          double precision,
  healthy_prob_mean       double precision,

  feature_schema_version smallint NOT NULL DEFAULT 1,
  PRIMARY KEY (plant_id, ts)
);
CREATE INDEX pvf_zone_ts_idx ON plant_visual_features_1h (zone_id, ts);
SELECT create_hypertable('plant_visual_features_1h', 'ts', chunk_time_interval => interval '30 days');
```

### 6.8. `vision_ground_truth` (разметка оператора)

Критическая таблица — без неё модели болезней для клубники обучить нельзя.

```sql
CREATE TABLE vision_ground_truth (
  id                    bigserial PRIMARY KEY,
  image_id              bigint      NOT NULL REFERENCES plant_images(id) ON DELETE CASCADE,
  plant_id              bigint      REFERENCES plants(id),
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,

  labeler_id            bigint      NOT NULL REFERENCES users(id),
  labeled_at            timestamptz NOT NULL DEFAULT now(),
  labeler_confidence    smallint,                -- 1..5

  -- что отметил оператор
  labels                jsonb       NOT NULL,    -- {"health":"powdery_mildew","deficiency":"Ca","stage":"flowering",...}
  bboxes                jsonb,                   -- [{bbox,class,notes}]
  free_text             text,

  -- используется ли для train/val/test
  split                 varchar(8),              -- 'train'|'val'|'test'|'hold'
  schema_version        smallint NOT NULL DEFAULT 1
);
CREATE INDEX vgt_image_idx ON vision_ground_truth (image_id);
CREATE INDEX vgt_plant_ts_idx ON vision_ground_truth (plant_id, labeled_at);
```

### 6.9. `vision_data_quality_windows`

По аналогии с `ml_data_quality_windows` из `ML_FEATURE_PIPELINE.md`.

```sql
CREATE TABLE vision_data_quality_windows (
  id                    bigserial PRIMARY KEY,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  start_ts              timestamptz NOT NULL,
  end_ts                timestamptz NOT NULL,
  reason                varchar(64) NOT NULL,    -- 'lights_off'|'camera_offline'|
                                                 -- 'calibration_missing'|'operator_obstruction'|...
  severity              varchar(16) NOT NULL,    -- 'exclude'|'warn'
  details               jsonb,
  created_by            bigint REFERENCES users(id),
  created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX vdq_zone_range_idx
  ON vision_data_quality_windows (zone_id, start_ts, end_ts);
```

### 6.10. `plant_visual_alerts` (триггеры для `zone_events` / UI)

```sql
CREATE TABLE plant_visual_alerts (
  id                    bigserial PRIMARY KEY,
  plant_id              bigint      REFERENCES plants(id),
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  first_seen_at         timestamptz NOT NULL,
  last_seen_at          timestamptz NOT NULL,
  alert_type            varchar(64) NOT NULL,    -- 'disease_powdery_mildew'|'deficiency_ca'|...
  severity              varchar(16) NOT NULL,    -- 'info'|'warning'|'critical'
  evidence_image_id     bigint REFERENCES plant_images(id),
  confidence            double precision NOT NULL,
  status                varchar(16) NOT NULL,    -- 'open'|'acknowledged'|'resolved'|'false_positive'
  acknowledged_by       bigint REFERENCES users(id),
  acknowledged_at       timestamptz,
  notes                 text,
  created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pva_zone_status_idx ON plant_visual_alerts (zone_id, status, last_seen_at DESC);
```

При создании алерта **обязательно** пишется запись в `zone_events`
(`type='VISION_ALERT_RAISED'`, payload с `alert_id`, `alert_type`, `confidence`).

---

## 7. Контракты данных и MQTT/HTTP интерфейсы

### 7.1. Загрузка кадра (HTTP, узел → image-ingestor)

```
POST /v1/images
Authorization: Bearer <node_token>
Content-Type: multipart/form-data

fields:
  file: <jpeg bytes>
  metadata_json: {
    "node_id": "node_cam_01",
    "zone_uid": "zone_12",
    "captured_at": "2026-04-22T14:30:00Z",
    "width_px": 4608, "height_px": 2592,
    "exposure_us": 10000, "iso": 100,
    "focus_score": 185.4,
    "lights_on": true,
    "color_chart_detected": true,
    "aruco_detected_count": 4,
    "camera_fw": "picam3-2.0"
  }

response 201:
  { "image_id": 123456, "storage_uri": "s3://..." }
```

### 7.2. MQTT событие (image-ingestor → vision-analyzer)

Topic: `hydro/{gh}/{zone}/{node}/camera/event`
Payload:
```json
{
  "event": "new_image",
  "image_id": 123456,
  "captured_at": 1745337000,
  "quality_ok": true,
  "color_chart_detected": true,
  "aruco_detected_count": 4,
  "schema_version": 1
}
```

Не расширять payload без обновления этого документа.

### 7.3. `sensors` и новый `type='CAMERA'`

Миграция: расширить enum `sensors.type` значением `CAMERA`. `telemetry_last` и
`telemetry_samples` для такого сенсора **НЕ пишутся** — у камеры свой путь.
В `sensors.specs` (JSONB) хранится:
```json
{
  "resolution": [4608, 2592],
  "lens_focal_mm": 4.74,
  "mount_height_mm": 850,
  "nadir_angle_deg": 0
}
```

### 7.4. Инварианты

1. `vision-analyzer` — единственный writer для `plant_detections`,
   `plant_disease_predictions`, `plant_fruit_counts`, `plant_color_samples`,
   `plant_visual_alerts`.
2. `feature-builder` — единственный writer для `plant_visual_features_1h`.
3. `plant_images.storage_uri` иммутабельна после записи.
4. Кадр удаляется из S3 **только** после того, как:
   (а) он старше `VISION_RAW_RETENTION_DAYS`,
   (б) все связанные `plant_detections` с `mask_storage_uri` вычищены,
   (в) нет связанного `vision_ground_truth` (размеченные храним бессрочно).
5. Любое изменение формулы визуальной фичи → инкремент
   `feature_schema_version` + миграция.

---

## 8. Стратегия сбора ground truth

**Без этого пункт 1.1 недостижим.** Клубника top-down в гидропонике — узкий
домен, под который нет публичного датасета нужного качества.

### 8.1. Протокол сбора (первые 60 дней)

- Ежедневно оператор заходит в UI «Разметка зон» (новая вкладка в mobile app).
- Приложение показывает по 10–20 свежих кадров на зону.
- Оператор для каждого растения на кадре тыкает:
  - общее состояние: healthy / mild_stress / severe_stress
  - если нездорово: причина из списка (см. Приложение B)
  - confidence (1-5)
- Раз в неделю — **выделенная сессия разметки** с помощью агронома:
  полный бокс + точная метка для всех плодов в 5 «золотых» кадрах на зону.
- Цель: **≥ 500 размеченных кадров на зону за 60 дней**, из них
  ≥ 50 с каждым классом болезни/дефицита (пусть даже специально индуцированных
  в тестовом боксе).

### 8.2. Индукция болезней для датасета

Для редких классов (ботритис, мучнистая роса) выделяется **контрольная грядка**
в отдельной зоне, где намеренно поддерживаются условия, способствующие
заболеванию (высокая влажность, плохая вентиляция). Это единственный способ
получить классы, которые в штатной эксплуатации теплицы встречаются редко.

### 8.3. Использование публичных датасетов как bootstrap

На **старте**, пока нет своих меток:
- **StrawDI** (instance segmentation strawberries)
- **PlantVillage** (strawberry leaf scorch / healthy)
- **PlantDoc** (поле, не теплица, но есть клубника)
- **iNaturalist-plant-disease** (много классов)
- **DeepWeeds** (не релевантно, не брать)

Pipeline:
1. Предобучение сегментатора на StrawDI + PlantVillage → MVP-уровень сегмент.
2. Класс-классификатор (disease): DINOv2-small backbone + linear head,
   finetune на PlantVillage+PlantDoc → baseline.
3. По мере накопления своих меток — дообучение именно на них с высоким весом.

### 8.4. Active learning

`vision-analyzer` публикует в UI «кадры, на которых модель неуверена»
(энтропия вероятностей высокая). Оператор размечает именно их — это в 3-5 раз
ускоряет набор датасета по сравнению со случайной разметкой.

---

## 9. Модели: что берём и что тренируем

### 9.1. Плановый стек моделей

| Задача | Модель | Источник | Размер | Время inference (CPU / GPU) |
|---|---|---|---|---|
| Калибровка ArUco | OpenCV `aruco` | — | — | < 50 мс / — |
| Калибровка цвета | OpenCV + ColorChecker lib | — | — | < 100 мс / — |
| Plant segmentation | YOLOv11-seg (m) или SAM2-tiny | Ultralytics / Meta | ~50 МБ | ~500 мс / ~30 мс |
| Color features | чистая numpy/opencv арифметика | — | — | < 100 мс |
| Disease classification | DINOv2-small + linear head | Meta + finetune | ~90 МБ | ~300 мс / ~20 мс |
| Fruit/flower detection | YOLOv11-m | Ultralytics + finetune | ~40 МБ | ~300 мс / ~15 мс |
| Per-plant tracking | ByteTrack (при переходе к видео) | — | — | < 10 мс |

Итого бюджет inference на один кадр: **~1.5 с на CPU / ~100 мс на GPU**. При
частоте 1 кадр / 15 минут / зона даже CPU хватает на десятки зон.

### 9.2. Почему DINOv2, а не обычный ResNet/ViT

DINOv2 обучен self-supervised на огромном корпусе, его эмбеддинги по growth
stage и leaf texture сильно обобщают даже с малым finetune датасетом.
На 500 размеченных кадров это даёт заметно лучший результат, чем классический
ImageNet-preтрен.

### 9.3. Версионирование

Каждая модель живёт в `ml_models` (таблица из `ML_FEATURE_PIPELINE.md §5.6`) со
своим `name` (`vision_segmenter`, `vision_disease`, `vision_fruit`), статусом
(shadow/canary/active/retired) и правилами rollout по §12.3 того же документа.

---

## 10. Интеграция с `ML_FEATURE_PIPELINE.md`

Это главный момент, без которого весь vision — просто фотоальбом.

### 10.1. Как vision-фичи попадают в ML

Вариант 1 — **separate view** (рекомендуется для MVP):
`plant_visual_features_1h` и `zone_features_5m` живут отдельно. Training
notebook делает `JOIN ... ON zone_id AND time_bucket('1 hour', ts)`.

Вариант 2 — **zone-level rollup** (Phase 5):
Добавить в `zone_features_5m` (§5.2 ML_FEATURE_PIPELINE) колонки
`visual_disease_score`, `visual_tip_burn_score`, `visual_growth_rate`, `canopy_area_mm2`.
`feature-builder` агрегирует по всем растениям зоны и кладёт в ту же строку.

### 10.2. Новые таргеты для ML

В `ml_labels` добавляются таргеты:
- `onset_of_disease_in_7d` (binary, per plant) — оператор подтвердит болезнь
  в ближайшие 7 дней?
- `yield_ripe_in_14d` (regression) — сколько спелых плодов через 14 дней?

Считаются из `plant_visual_alerts` (статус `acknowledged`) и будущих
`plant_fruit_counts`. Это честные таргеты — мы не подсматриваем в будущее,
а ждём 7/14 дней и только потом материализуем метку.

### 10.3. Как модель использует химию + cv вместе

Пример — предсказание tip-burn:

Фичи (вход):
- из `zone_features_5m`: `ec_mean` последних 72 часов (max/mean),
  `ph_mean`, `water_temp_mean`
- из `plant_visual_features_1h`: `tip_burn_score_max` текущий,
  `area_growth_rate_per_day` последние 7 дней

Таргет: `onset_of_disease_in_7d{alert_type='deficiency_ca'}`.

Это даёт агроному конкретную рекомендацию: «В зоне 12 высокий EC + растёт
tip-burn score → в ближайшие 48 ч перейди на EC 1.4 мС, иначе k% растений
уйдёт в Ca-дефицит».

---

## 11. Retention, хранилище и стоимость

| Объект | Hot | Warm | Cold | Обоснование |
|---|---|---|---|---|
| Raw JPEG в S3 | 30 дней | 30–180 дней (IA tier) | 180+ дней → Glacier или удаление | 47 ГБ/год/зона — терпимо |
| Размеченные `vision_ground_truth` + их JPEG | ∞ | — | — | Ценнейший актив |
| `plant_images` (строки) | 180 дней | 180 дней – ∞ | — | Маленькая таблица |
| `plant_detections` | 90 дней | 90 дней – 12 мес | → агрегаты в `plant_visual_features_1h` | Большая таблица |
| `plant_disease_predictions` | 90 дней | 12 мес | — | |
| `plant_fruit_counts` | ∞ | — | — | Маленькая, ценная для yield-анализа |
| `plant_visual_features_1h` | ∞ | 3 мес – ∞ (compression) | — | Аналог `zone_features_5m` |
| Маски сегментации (PNG) | 7 дней | 30 дней | удалять | Пересоберутся из модели |

**Env vars в `vision-analyzer`:**
```
VISION_RAW_RETENTION_DAYS=30
VISION_MASKS_RETENTION_DAYS=30
VISION_DETECTIONS_RETENTION_DAYS=90
VISION_GROUND_TRUTH_RETENTION=NEVER
```

---

## 12. Inference pipeline

### 12.1. Сервис `vision-analyzer`

**Путь:** `backend/services/vision-analyzer/`
**Зависимости:** torch, ultralytics, opencv-python, timm, asyncpg, paho-mqtt,
boto3 (S3).

### 12.2. Worker loop

```
async def on_mqtt_event(evt):
    if evt["event"] != "new_image": return
    image_meta = await load_plant_image(evt["image_id"])
    if not image_meta.quality_ok: return
    if not image_meta.color_chart_detected or image_meta.aruco_detected_count < 3:
        await mark_quality_window(..., reason="calibration_missing")
        return

    img = await s3_get(image_meta.storage_uri)
    img = apply_calibration(img, image_meta.calibration_id)

    masks = await segment_plants(img)               # YOLOv11-seg
    for mask, bbox in masks:
        det = compute_geometry_color_features(img, mask, bbox)
        plant_id = associate_with_plant(image_meta.zone_id, det.centroid_mm)
        det_id = await save_plant_detection(image_meta, plant_id, det)

        crop = extract_crop(img, bbox)
        probs = await classify_disease(crop)        # DINOv2+head
        await save_disease_pred(det_id, probs)

    fruits = await detect_fruits(img)               # YOLOv11
    await save_fruit_counts(image_meta, fruits)

    await maybe_raise_alerts(image_meta.zone_id)
```

### 12.3. Safety

- Алерты от vision **никогда** не запускают дозирование/биопрепараты
  автоматически (только advisory в UI + `zone_events`).
- При любом crash vision-analyzer автоматика в `automation-engine` работает
  как без него (vision — optional path).

### 12.4. Метрики (Prometheus)

```
vision_images_ingested_total{zone_id=...}
vision_images_rejected_total{reason=...}
vision_analysis_seconds{stage="segment|classify|detect"}
vision_analyzer_errors_total{stage=...}
vision_plants_detected_per_image{zone_id=...}
vision_alerts_raised_total{type=...}
vision_gpu_utilization                  (если GPU)
```

---

## 13. Protocol калибровки

### 13.1. Первичная калибровка зоны (при монтаже)

1. Закрепить камеру, проверить, что нижняя плоскость строго в кадре с запасом.
2. Разместить 4 ArUco-маркера в 4 углах зоны, измерить точное расстояние
   рулеткой, внести в UI.
3. Положить ColorChecker в центр кадра, сделать 10 тестовых снимков.
4. UI запускает калибровочный прогон, вычисляет homography и color transform,
   сохраняет в `vision_calibrations` как `valid_from=now()`.

### 13.2. Regular re-calibration

- Раз в 7 дней — автоматический снимок с ColorChecker + проверка
  drift'а (ΔE > 5 → алерт, требуется ручная повторная калибровка).
- При смене ламп, пересадке или любом физическом вмешательстве в
  зону — обязательно закрыть текущую `vision_calibrations.valid_to=now()`
  и создать новую.

### 13.3. Что происходит без калибровки

Если `color_chart_detected=false` или `aruco_detected_count < 3`:
- `plant_images.quality_ok = false`, `quality_reason='calibration_missing'`
- `vision-analyzer` НЕ запускает inference
- В UI растёт счётчик «некалиброванных кадров», при ≥ 10 подряд — алерт
  оператору

---

## 14. План внедрения по фазам

### Phase V0 · Подготовка (1 неделя)

| Задача | DoD |
|---|---|
| Ревью и утверждение документа | merge в `doc_ai/` |
| Закупка железа (RPi 5, Cam Module 3, ColorChecker, ArUco print) на 1 пилотную зону | Оборудование на месте |
| MinIO в dev-стеке (`infra/docker/`) | `make up` включает minio, доступен по 9000/9001 |
| Схема бакетов: `hydro-vision/{env}/{yyyy}/{mm}/{dd}/zone_{id}/` | Документировано |

### Phase V1 · Узел + ingest (2 недели)

| Задача | DoD |
|---|---|
| `firmware/camera_node/` — Python-сервис на RPi (capture, prefilter, upload) | Кадры на MinIO каждые 15 мин |
| Миграции §6.2, §6.3, §6.9 + `sensors.type='CAMERA'` | Up/down проходят |
| `backend/services/image-ingestor/` | E2E: POST → S3 + `plant_images` + MQTT event |
| UI Zone page: превью последних кадров | Виден thumbnail |
| Калибровочный прогон (UI + image-ingestor) | `vision_calibrations` заполняется |

### Phase V2 · Минимальный vision-analyzer (2 недели)

| Задача | DoD |
|---|---|
| Миграции §6.1, §6.4, §6.10 | Up/down |
| `backend/services/vision-analyzer/` | Skeleton + `/healthz` + metrics |
| Plant segmentation pretrained (StrawDI) | По кадру рисуются маски на UI |
| Geometric + color features | `plant_detections` заполняется |
| `plants` — автосоздание по position grid | Новое растение регистрируется при первом стабильном детекте |

### Phase V3 · Ground truth + alerts (2 недели)

| Задача | DoD |
|---|---|
| UI «Разметка зон» (mobile + web) | Оператор может размечать изображения |
| Миграция §6.8 (`vision_ground_truth`) | Данные пишутся |
| Active learning queue | UI показывает «uncertain» кадры |
| Миграция §6.10 + правила alert'ов по порогам | `plant_visual_alerts` + `zone_events` при триггере |

### Phase V4 · Disease + fruits (3 недели)

| Задача | DoD |
|---|---|
| Миграции §6.5, §6.6 | Up/down |
| Baseline disease classifier (DINOv2+head, finetune на PlantVillage+500 своих) | precision@healthy ≥ 0.9 |
| YOLOv11 fruit detector (finetune на StrawDI + 200 своих) | mAP@0.5 ≥ 0.6 на val |
| Модели в `ml_models` со статусом `shadow` | Записи в `ml_predictions` с лагом до истинных alerts |

### Phase V5 · ML-ready витрина + интеграция (2 недели)

| Задача | DoD |
|---|---|
| Миграция §6.7 (`plant_visual_features_1h`) | Up/down, hypertable |
| Расширение `feature-builder` — агрегация визуалок по часу/растению | Строки появляются с лагом ≤ 5 мин после часа |
| Новые колонки в `zone_features_5m` (Вариант 2 из §10.1) | Реализован rollup на уровень зоны |
| Training notebook `tools/ml/vision/integrated_forecast.ipynb` | Показана модель tip-burn на 48h с MAE лучше baseline |

### Phase V6 · Доработки (TBD)

- Вторая камера под углом — честный подсчёт плодов
- Ночные съёмки с IR-подсветкой для диагностики стресса
- Тепловизор (Lepton 3) для ранней детекции водного стресса
- Motorized тур для крупных зон

---

## 15. Чек-лист перед мержем фичи в Vision-слой

- [ ] Новые таблицы/колонки в `DATA_MODEL_REFERENCE.md`
- [ ] `feature_schema_version` или `schema_version` инкрементирован
- [ ] Up/down миграции прошли на dev
- [ ] Unit-тесты на calibration pipeline (homography, color transform)
- [ ] E2E тест: upload → ingestor → MQTT → analyzer → БД
- [ ] Point-in-time: фичи в `plant_visual_features_1h` на `ts` используют
      только `plant_images.captured_at < ts`
- [ ] Prometheus метрики добавлены
- [ ] Retention policy обновлена (`DATA_RETENTION_POLICY.md`)
- [ ] Ownership таблицы зафиксирован
- [ ] При задетом `ML_FEATURE_PIPELINE.md` — обновление синхронное
- [ ] Alert'ы не триггерят дозирование автоматически

---

## 16. Правила для ИИ-агентов

### Можно:

- Генерировать DDL и миграции по §6 (пара up/down обязательна).
- Писать код сервисов `image-ingestor`, `vision-analyzer`, расширять
  `feature-builder`, тесты, metrics.
- Расширять список классов в Приложении B при добавлении новых фенотипов
  (с инкрементом `schema_version` и backfill-стратегией).
- Добавлять новые фичи в `plant_detections` / `plant_visual_features_1h`
  (с инкрементом `feature_schema_version`).
- Писать training notebooks в `tools/ml/vision/`.

### Нельзя:

- **Писать в vision-витрины из любого сервиса, кроме их owner'а** (§7.4).
- Гнать JPEG через MQTT (только HTTP → S3 + event с ссылкой).
- Запускать inference на кадрах с `quality_ok=false` или с
  `calibration_missing`.
- Использовать визуальные alert'ы для автоматического управления оборудованием
  без явного acknowledgement оператора.
- Удалять `vision_ground_truth` или связанные с ним `plant_images`, даже
  если подошёл retention.
- Тренировать на данных, пересекающих `vision_data_quality_windows` с
  `severity='exclude'`.
- Менять структуру payload MQTT-события `camera/event` без обновления §7.2.

### Обязательно:

- Каждый PR с Vision — обновление этого документа.
- Любая новая модель (`ml_models` INSERT) — с `trained_on_range`,
  `metrics_json`, отметкой публичный/приватный датасет.
- Новые алерты регистрируются в `zone_events` (не только в
  `plant_visual_alerts`).
- Фичи и таргеты физически разделены (как в §8 ML_FEATURE_PIPELINE).

---

## 17. Открытые вопросы

1. **Storage:** MinIO в самохосте vs AWS S3/Cloudflare R2. На 1 зону 47 ГБ/год —
   самохостимый MinIO хватает; на 50+ зон — стоит считать.
2. **GPU на сервере:** что закладываем в инфру? T4 / 3060 / A10? Или стартуем
   на CPU и апгрейдим при росте нагрузки?
3. **mobile app vs web:** разметка удобнее на планшете (тач-боксинг);
   есть ли апетит на iPad-native UI или ограничимся web?
4. **Пилот:** одна зона × 30 дней → оценка качества данных перед скейлом?
5. **Agronom-in-the-loop:** кто будет верифицировать сложные метки (болезни)?
   Без эксперта ground truth рискует быть шумным.
6. **Интеграция с существующим `grow_cycles`:** нужен ли `plant_id` в `sensors`
   (чтобы точечные pH/EC сенсоры ассоциировались с растением)? Скорее нет, но
   в будущем для rhizosphere-мониторинга — возможно.
7. **Privacy/Safety:** кадры могут случайно содержать оператора. Нужен ли
   face blur pipeline? (скорее да, если кадры уходят в публичный датасет).

---

## Приложение A. Классы цветового/геометрического анализа

Перечень базовых фенотипических сигналов для клубники, которые
`vision-analyzer` извлекает из каждого детекта:

| Сигнал | Вычисление | Что означает |
|---|---|---|
| `lab_l_median` | медиана L* по маске | светлость листьев; падение → стресс |
| `lab_a_median` | медиана a* | зелёно-красный баланс; рост → краснота (P, холод) |
| `lab_b_median` | медиана b* | жёлто-синий; рост → хлороз (N, Mg, Fe) |
| `ndi` | (G-R)/(G+R) | «зелёность»; классический индекс |
| `yellow_ratio` | доля HSV(H∈[40,70],S>0.3) | общий хлороз |
| `purple_ratio` | доля HSV(H∈[270,330],S>0.2) | признак P-дефицита / холодового стресса |
| `tip_burn_score` | доля «burnt» пикселей в верхней 1/3 маски по скелету | Ca-дефицит |
| `margin_burn_score` | доля burnt по контуру листа | K-дефицит |
| `interveinal_score` | контраст вены/меж-вены (Gabor-filter отклик) | Mg/Fe |

## Приложение B. Классы болезней/дефицитов/стадий для клубники

### Health / Disease
- `healthy`
- `powdery_mildew` (Podosphaera aphanis)
- `gray_mold_botrytis` (Botrytis cinerea)
- `leaf_scorch` (Diplocarpon earlianum)
- `leaf_spot` (Mycosphaerella / Ramularia)
- `anthracnose` (Colletotrichum)
- `verticillium_wilt`
- `red_stele` (Phytophthora fragariae)
- `spider_mite_damage` (Tetranychus urticae)
- `aphid_infestation`
- `thrips_damage`
- `mechanical_damage`
- `unknown_abnormal`

### Nutritional deficiencies / toxicities
- `deficiency_n` (равномерный хлороз старых листьев)
- `deficiency_p` (пурпурные оттенки, старые листья)
- `deficiency_k` (краевой ожог старых листьев)
- `deficiency_ca` (tip-burn, молодые листья) — **приоритет для клубники**
- `deficiency_mg` (интервенальный хлороз, старые листья)
- `deficiency_fe` (интервенальный хлороз, молодые листья)
- `deficiency_b` (деформация молодых листьев, недоразвитые плоды)
- `toxicity_ec_high` (ожог краёв всего растения, водный стресс)
- `toxicity_ph_low` (железо-марганцевая токсичность)
- `toxicity_ph_high` (вторичный Fe/Mn/P-дефицит)

### Plant stage
- `seedling`, `vegetative`, `flowering`, `fruiting`, `harvest`, `senescence`

### Fruit stages
- `flower_closed`, `flower_open`, `green`, `white`, `turning`, `ripe`,
  `overripe`, `rotten`

---

# Конец файла VISION_PIPELINE.md
