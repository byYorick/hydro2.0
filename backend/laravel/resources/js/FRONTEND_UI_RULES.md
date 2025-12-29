# FRONTEND UI RULES

## Definition of Done (Frontend)

- Design tokens: use CSS variables (`var(--...)`) for colors/shadows; avoid hardcoded hex values.
- Core layout primitives: prefer `surface-card`, `input-field`, `input-select` for containers and controls.
- E2E stability: do not remove or rename existing `data-testid` attributes referenced in `tests/e2e/browser/constants.ts`.
  - If a new test id is required, add it to the constants file first.
- Components default to TypeScript (`<script setup lang="ts">`); use JS only with a clear reason.
- New features must show unified states for:
  - `EmptyState` for empty/error views.
  - `SkeletonBlock` (or `LoadingState` where appropriate) for loading views.

## Notes

- Preserve existing `data-testid` attributes when refactoring layouts or moving blocks.
- Keep visual consistency with existing tokenized styles and surface patterns.
