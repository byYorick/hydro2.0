# Архив промежуточных отчётов и legacy-документов

**Статус:** `archive` — не source of truth.  
**Дата обновления:** 2026-08-02

Исторические материалы. Для актуальной работы используйте:

- [`../INDEX.md`](../INDEX.md) — навигация
- [`../IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md) — статус реализации
- [`../SYNC_PLAN.md`](../SYNC_PLAN.md) — code-first drift backlog

На старых путях в рабочих разделах оставлены короткие **stubs** со ссылкой сюда (чтобы не ломать ссылки из INDEX/кода).

## Структура

| Папка | Содержимое |
|-------|------------|
| `REPORTS/` | Отчёты аудита/cleanup/gaps (backend, python, docs) |
| `PHASE_REPORTS/` | Промежуточные отчёты фаз рефакторинга backend |
| `FRONTEND_REPORTS/` | Архивные аудиты frontend |
| `SUPERSEDED/` | Полные тексты документов, заменённых каноном |
| `PLANS/` | Закрытые/исторические audit- и refactor-plans |

## SUPERSEDED (полные тексты)

- `GLOBAL_SCHEDULER_ENGINE.md` — канон: `../06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`
- `HYDROPONIC_RECIPES_ENGINE.md` — канон: `../06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md`

## PLANS (исторические)

Корень (stubs в `doc_ai/`):

- `AUDIT_2026_05_28_BUGFIX_PLAN.md`
- `AUDIT_2026_07_07_RELIABILITY_PLAN.md`

Система / backend / frontend — см. файлы в этой папке; stubs на прежних путях в `01_SYSTEM/`, `04_BACKEND_CORE/`, `07_FRONTEND/`.

## Примечание

Каталог `11_LEGACY_ARCHIVES/` (zip-дампы старых docs) **удалён** 2026-08-02 — не SoT и не навигация.
