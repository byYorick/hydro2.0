# AE2 Scheduler Split Invariants

**Дата:** 2026-02-19  
**Статус:** ACTIVE

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Зафиксировать machine-checkable guard rails для split-архитектуры scheduler.

## Инструменты

1. `tools/testing/SCHEDULER_SPLIT_INVARIANTS.py`
2. `tools/testing/check_scheduler_split_invariants.sh`

## Проверяемые инварианты

1. Наличие обязательных split-модулей (`app/domain/infrastructure`).
2. Наличие фасадных import markers в `backend/services/scheduler/main.py`.
3. Единственная дефиниция ключевых фасадных функций (`main.py`).
4. Отсутствие прямого `httpx.AsyncClient` в `main.py` после split.
5. Контроль размера `main.py` (line-count guard).

## Команда запуска

```bash
tools/testing/check_scheduler_split_invariants.sh
```

## Текущий baseline

- Результат: `PASS`.
