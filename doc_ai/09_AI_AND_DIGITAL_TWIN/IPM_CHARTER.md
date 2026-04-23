# IPM_CHARTER.md
# Паспорт pipeline: Integrated Pest Management (клейкие ловушки + биоагенты)

**Статус:** 🟡 CHARTER
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/IPM_CHARTER.md`
**Связанные:** `VISION_PIPELINE.md` (базовая инфраструктура CV), `UNIFIED_ALERTING_CHARTER.md`

---

## 1. Назначение

Клубника в закрытой теплице несовместима с химическими пестицидами (остатки
на ягоде = отбраковка). IPM — стандарт отрасли: мониторинг вредителей +
выпуск полезных насекомых. Этот pipeline:
- автоматически считает вредителей по фото клейких ловушек;
- прогнозирует динамику популяции;
- планирует выпуск биоагентов (Phytoseiulus, Amblyseius, Orius);
- связывается с CV-анализом повреждений листьев.

## 2. Цели

- Автоподсчёт 5 ключевых вредителей на ловушках (трипс, тля, белокрылка,
  паутинный клещ, сциарида) с precision ≥ 0.85.
- Детекция превышения порога → alert за 24–48ч до видимого ущерба.
- Планирование доз биоагентов по формулам IPM-поставщиков (Koppert, Biobest).
- Retrospective analysis: эффективность каждой биоинтервенции.

## 3. Ключевые дизайн-решения

1. **Клейкие ловушки как fixed imaging targets** — жёлтые (трипс, тля,
   белокрылка) + синие (трипс, сциарида) ловушки на штативе в одной позиции.
   Съёмка 1 раз в 6 часов точечно камерой VISION.
2. **Pre-processing вручную**: ловушка заменяется оператором раз в 2 недели;
   система сохраняет «страницу» полностью и считает дельту с предыдущего
   кадра. Не идентификация отдельных насекомых, а прирост за 6 часов.
3. **Биоагенты как commands**: выпуск биоагента → запись в таблицу с
   дозой и типом; ML-модель учится на «какая доза → какая динамика
   популяции вредителя через 7 дней».
4. **Two-track detection**:
   - Ловушки = индикатор популяции (количественный)
   - CV листьев (повреждения) из VISION_PIPELINE = индикатор ущерба
     (качественный)

## 4. Структура данных

```sql
CREATE TABLE pest_traps (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  trap_code varchar(32) NOT NULL,        -- 'T-12-01'
  trap_type varchar(16) NOT NULL,        -- 'yellow'|'blue'|'pheromone'
  position_code varchar(32),
  installed_at timestamptz NOT NULL,
  replaced_at timestamptz,
  UNIQUE (zone_id, trap_code, installed_at)
);

CREATE TABLE pest_trap_readings (
  id bigserial PRIMARY KEY,
  trap_id bigint NOT NULL REFERENCES pest_traps(id) ON DELETE CASCADE,
  zone_id bigint NOT NULL REFERENCES zones(id),
  captured_at timestamptz NOT NULL,
  image_id bigint REFERENCES plant_images(id),
  counts jsonb NOT NULL,                 -- {thrips: 12, aphid: 3, whitefly: 8, ...}
  counts_delta_6h jsonb,                 -- прирост с прошлого чтения
  model_version varchar(32),
  confidence_scores jsonb,
  schema_version smallint DEFAULT 1
);
SELECT create_hypertable('pest_trap_readings','captured_at',
                         chunk_time_interval=>interval '30 days');

CREATE TABLE biological_control_agents (
  id bigserial PRIMARY KEY,
  name varchar(64) NOT NULL,             -- 'Phytoseiulus persimilis'
  target_pest varchar(32) NOT NULL,      -- 'spider_mite'
  recommended_dose_per_m2 double precision,
  source_supplier varchar(32)
);

CREATE TABLE bcagent_releases (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  bcagent_id bigint NOT NULL REFERENCES biological_control_agents(id),
  released_at timestamptz NOT NULL,
  released_by bigint REFERENCES users(id),
  dose_count integer NOT NULL,           -- кол-во хищников/паразитоидов
  release_method varchar(32),            -- 'scatter'|'sachets'|'cards'
  reason varchar(64),                    -- 'preventive'|'curative'|'schedule'
  advisory_id bigint REFERENCES ipm_advisories(id),
  notes text
);

CREATE TABLE ipm_advisories (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  generated_at timestamptz NOT NULL,
  pest varchar(32) NOT NULL,
  risk_level varchar(16) NOT NULL,       -- 'ok'|'monitor'|'alert'|'urgent'
  population_estimate integer,
  population_trend_7d varchar(16),       -- 'decreasing'|'stable'|'increasing'
  recommended_action varchar(64),        -- 'release_phytoseiulus_200/m2'
  recommended_bcagent_id bigint REFERENCES biological_control_agents(id),
  recommended_dose integer,
  confidence double precision,
  model_id bigint REFERENCES ml_models(id)
);

CREATE TABLE ipm_thresholds (
  id bigserial PRIMARY KEY,
  pest varchar(32) NOT NULL,
  phenology_stage varchar(32),
  threshold_monitor_per_trap integer,
  threshold_alert_per_trap integer,
  threshold_urgent_per_trap integer,
  UNIQUE (pest, phenology_stage)
);
```

## 5. Сервисы

| Сервис | Роль |
|---|---|
| `ipm-analyzer` | Расширение `vision-analyzer`: специализированный детектор вредителей на ловушках |
| `ipm-planner` | Новый. Раз в сутки анализирует тренды, публикует `ipm_advisories` |
| `release-logger` | UI для регистрации фактического выпуска биоагентов |

## 6. Модели

- **Trap object detector** — YOLOv11 или RT-DETR, fine-tune на собственных
  снимках ловушек + публичных (InsectNet, Trap-Based Pest Dataset).
- **Population dynamics model** — Lotka-Volterra или simple logistic with
  bioagent predation term, параметры калибруются на истории.
- **Release timing optimizer** — когда выпускать предотвращает всплеск, а
  когда уже поздно и нужно больше.

## 7. Safety

- **Never auto-release** — рекомендации всегда требуют операторского
  подтверждения (живые организмы, дорогие, не вернёшь).
- Alert'ы дублируются в `UNIFIED_ALERTING` с severity=warning (не critical —
  biological lag 3-7 дней).

## 8. Фазы

| Phase | Задача | DoD |
|---|---|---|
| P0 | Конструктив ловушек + крепления | Все зоны имеют стандартную position |
| P1 | Миграции + `ipm-analyzer` pest detection | Счёт на кадре ≥ 80% accuracy |
| P2 | `pest_trap_readings` + delta counts | Данные пишутся |
| P3 | UI регистрации выпусков биоагентов | Оператор логирует |
| P4 | Population dynamics + advisories | `ipm_advisories` генерируются |
| P5 | Retrospective analysis | Отчёт «что работало» в UI |

## 9. Интеграция

- **VISION_PIPELINE** — переиспользует `plant_images` infrastructure, но
  добавляет свой detector. Тип детекции различается по `trap` vs `plant`.
- **UNIFIED_ALERTING** — IPM urgent alerts туда.
- **ECONOMIC layer** (из YIELD_FORECASTING) — стоимость биоагентов +
  предотвращённый ущерб.

## 10. Правила для ИИ-агентов

### Можно:
- Расширять список `biological_control_agents` (с ссылкой на поставщика).
- Обновлять `ipm_thresholds` с ссылкой на источник (manual IPM guide).

### Нельзя:
- Генерировать команды release без human-in-the-loop.
- Менять `trap_type` конкретной ловушки (это физическое устройство).
- Смешивать детекцию на ловушках и на листьях в одной модели.

## 11. Открытые вопросы

1. Нужна ли специальная камера близко к ловушке (5-10 см) для точности,
   или хватит zoom на существующей?
2. Smart-ловушки с встроенной камерой (Trapview, Scoutek) — покупать
   готовое решение или делать своё?
3. Как обрабатывать смену ловушки оператором (reset counter)?

---

# Конец IPM_CHARTER.md
