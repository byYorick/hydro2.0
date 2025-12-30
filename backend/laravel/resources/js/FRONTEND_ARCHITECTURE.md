# FRONTEND ARCHITECTURE

## Structure map

- `backend/laravel/resources/js/Components/`
  - UI primitives and reusable blocks (buttons, cards, table wrappers, charts).
- `backend/laravel/resources/js/Pages/`
  - Inertia pages (route-level containers and orchestration).
- `backend/laravel/resources/js/Layouts/`
  - App layout wrappers for pages.
- `backend/laravel/resources/js/composables/`
  - Shared logic (hooks) for data loading, URL state, WebSocket, UI helpers.
- `backend/laravel/resources/js/stores/`
  - Pinia stores, cache, and app state.
- `backend/laravel/resources/js/utils/`
  - Pure helpers and formatters.
- `backend/laravel/resources/js/constants/`
  - Static constants used across the UI.
- `backend/laravel/resources/js/types/`
  - Shared TypeScript types.
- `backend/laravel/resources/js/commands/`
  - Command palette registry and search helpers.

## Page pattern (default)

Use the same structure so pages look and behave consistently.

1) Layout + header
- Wrap in `AppLayout`.
- Use `PageHeader` for title/subtitle/eyebrow and primary actions.

2) Filters
- Use `FilterBar` for all filter controls.
- For filters that should be shareable, sync with URL via `useUrlState`.

3) Content states
- Loading: use `SkeletonBlock` or `LoadingState`.
- Empty: use `EmptyState` with a short description.
- Error: render `EmptyState` with variant `error` or inline error text.

4) Data blocks
- Prefer `DataTableV2` for list pages.
- Use `surface-card` + tokenized colors (`var(--...)`) for all containers.

## Adding a new page

1) Create a page in `Pages/<Module>/Index.vue`.
2) Use `AppLayout` + `PageHeader` + `FilterBar`.
3) Fetch data in composables or stores; keep the page as orchestration.
4) Implement loading/empty/error states with shared components.
5) Add `data-testid` if the page is part of e2e flows.

## Adding a new dashboard or widget

1) Create a widget component in `Components/<WidgetName>.vue`.
2) Keep widget props small and typed; avoid direct API calls inside widgets.
3) Fetch/transform data in a page or composable; pass it down.
4) Use `surface-card` and tokenized colors, align with existing spacing.
5) Add concise empty and loading states using `EmptyState`/`SkeletonBlock`.

## Notes

- Prefer TypeScript (`<script setup lang="ts">`).
- Reuse `useUrlState` for filters and pagination.
- Follow `FRONTEND_UI_RULES.md` for DoD and e2e test ids.
