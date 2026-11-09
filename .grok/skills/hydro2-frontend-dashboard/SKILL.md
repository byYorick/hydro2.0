---
name: hydro2-frontend-dashboard
description: "Vue 3 + Pinia + Tailwind + ECharts (Inertia в Laravel) dashboard Hydro 2.0: design tokens, operator UX, роли, data-testid. Используй при работах в backend/laravel/resources/js, UI зон/scheduler cockpit, графиках телеметрии."
metadata:
  type: domain
  lifecycle: active
  version: "0.2.0"
---

# hydro2-frontend-dashboard

## Когда применять
Страницы/компоненты Vue, Pinia stores, ECharts, Tailwind/tokens, role-based UI, e2e browser testids.

## Стек (факт репо)
Inertia + Vue 3, Pinia, Tailwind, ECharts (`vue-echarts`) — `backend/laravel/package.json`. Код: `backend/laravel/resources/js/`.

## UI правила
`backend/laravel/resources/js/FRONTEND_UI_RULES.md`: CSS variables (`var(--...)`), `surface-card` / `input-field`, не ломать `data-testid` из `tests/e2e/browser/constants.ts`, EmptyState/SkeletonBlock.

## Hard rules (defer)
Русский для пользователя; не ломать пайплайн до Vue; docs только по запросу / контракты.

## Override внешних skills
- `laravel-11-12-app-guidelines` — общий Laravel; UI/Inertia/Vue conventions Hydro важнее для фронта.
- `run-smoke-tests` — Playwright ок, но сохранять testid-контракты Hydro.
- `documentation-guidelines` — UI docs в `doc_ai/07_FRONTEND/`; не плодить корневые `.md`.

## Источники
- `doc_ai/07_FRONTEND/{FRONTEND_ARCH_FULL,FRONTEND_UI_UX_SPEC,ROLE_BASED_UI_SPEC,API_MAPPING,FRONTEND_TESTING}.md`
- `backend/laravel/resources/js/{FRONTEND_UI_RULES.md,stores,Pages,Components,composables}`
- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`

## Актуализация 2026-11-06

- Перед использованием API_MAPPING.md учитывай его статус «требует актуализации»; endpoint сверяй с routes и действующей API-спекой.
- Готовность UI/автоматики не выводится из HTTP 200 одного health endpoint.
- Playwright запускай по конкретному spec/grep после краткого пояснения scope; не очищай dev DB ради webServer.
- Для текстовых изменений достаточно статической проверки; для поведения выбери существующий Vitest/Playwright сценарий.
