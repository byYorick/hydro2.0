# AE 1.0.0 — runtime

**Дата:** 2026-09-22
**Статус:** контракт runtime. Формулы полива, дозы и стока здесь не живут.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Значение

`zones.automation_runtime` допускает `ae3` и `ae4`. Ограничение — `zones_automation_runtime_check`. Значение по умолчанию остаётся `ae3`.

Смена значения при активной задаче (`pending`, `claimed`, `running`, `waiting_command`), живой lease или незавершённой команде запрещена. Исключение то же: `ZoneRuntimeSwitchDeniedException`.

## Два воркера

Один процесс automation-engine. `main.py` поднимает воркер AE3 и воркер AE4. Отдельного сервиса в compose нет. Переменной, которая выключает один из воркеров на весь процесс, нет.

Интервал опроса — уже существующий `AE_RECONCILE_POLL_INTERVAL_SEC`.

Воркер AE3 забирает `ae_tasks` со статусом `pending` только у зоны `automation_runtime = ae3`. Воркер AE4 — только у зоны `ae4`. Чужой runtime не берётся. Owner воркера AE4 — `ae4-runtime-worker`.

## due_at

Claim берёт строку, у которой `due_at <= now`. Пустой `due_at` и `due_at` в будущем не берутся. Порядок: `due_at`, `created_at`, `id`. Блокировка задачи: `FOR UPDATE OF tasks SKIP LOCKED`. Строка зоны при этом не блокируется.

Тик волны 3 пишет `due_at = now`, когда создаёт задачу мутации.

## Пробуждение

После волны 3 единственное автоматическое пробуждение автоматики — тик воркера 1.0.0. До этой волны диспетчер Laravel этим контрактом не заменяется и не патчится.

## FSM задачи

```
pending → claimed → running → waiting_command → completed
                                               → failed
        → cancelled
```

Воркер AE4 этой поставки переводит свою pending-задачу в `claimed`. Переход не исполняет стадии и не публикует команды.
