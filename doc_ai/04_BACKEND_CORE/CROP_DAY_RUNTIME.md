# Суточный контур культуры: текущее поведение

**Статус:** `guide`. Описывает существующую реализацию, не очередь разработки.
**Сверено:** 2026-11-06 по коду репозитория. Приёмка физического стенда проверяется отдельно.

## Владельцы и источники данных

Laravel хранит фазы цикла, рецепты, конфигурацию и расписания. Scheduler-dispatch
формирует intents; AE3 выполняет workflow и публикует команды через history-logger.
Агрохимические цели берутся из активной `grow_cycle_phases`; PID, execution и
планы команд — из compiled bundle по revision цикла.

Канон: [ae3lite.md](ae3lite.md),
[EFFECTIVE_TARGETS_SPEC.md](../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md),
[SCHEDULER_ENGINE.md](../06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md).

## Реализованные части

| Область | Поведение и граница |
|---|---|
| Полив по датчику | Решение принимает `irrigation_decision_controller.py`. Проверяются настройка, свежесть и готовность; успешный `skip` не означает запуск насоса |
| Температура раствора | `solution_temp_irrigation_guard.py` проверяет диапазон и hold перед новым поливом; это не аварийное прерывание уже выполняемой дозы |
| Свет и DLI | При заданной цели используется интеграл PPFD в пределах местных суток и фотопериода. Люксы не преобразуются в PPFD; недостаток/разрыв данных отражается отдельно |
| Климат теплицы | Существующий decision engine рассчитывает воздушный VPD и точку росы; правила форточек — в climate spec |
| Рекомендация подмены | `SolutionRefreshRecommendation` вызывается scheduler-dispatch, пишет событие/алерт с ограничением частоты; не создаёт `solution_change` intent автоматически |
| Состояние для UI | `ZoneAutomationStateService` дополняет read-model суточными данными/DLI; GET состояния не запускает scheduler и не создаёт рекомендацию подмены |

## Где смотреть реализацию

- [Решение полива](../../backend/services/automation-engine/ae3lite/domain/services/irrigation_decision_controller.py)
- [Температурный guard](../../backend/services/automation-engine/ae3lite/domain/services/solution_temp_irrigation_guard.py)
- [DLI integral AE3](../../backend/services/automation-engine/ae3lite/domain/services/dli_integral.py)
- [DLI read-model Laravel](../../backend/laravel/app/Services/CropDay/DliDayBalance.php)
- [Рекомендация подмены](../../backend/laravel/app/Services/CropDay/SolutionRefreshRecommendation.php)
- [Состояние зоны](../../backend/laravel/app/Services/ZoneAutomationStateService.php)
- [Климатический контракт](../06_DOMAIN_ZONES_RECIPES/GREENHOUSE_CLIMATE_CONTROL_SPEC.md)

## Проверка

Существующие целевые проверки: `ZoneDayBalanceTest`,
`SolutionRefreshRecommendationTest`, `test_ae3lite_solution_temp_irrigation_gate.py`,
`test_ae3lite_dli_lighting.py`, `test_ae3lite_crop_day_metrics.py`.
Наличие этих файлов не является результатом их запуска или приёмкой оборудования.
Backend-проверки выполняются в проектных контейнерах на отдельной test DB;
порядок — в [TESTING_OVERVIEW.md](../13_TESTING/TESTING_OVERVIEW.md).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
