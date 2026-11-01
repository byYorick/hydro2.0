/**
 * Hydroflow UI primitives — atomic building blocks для launch wizard и cockpit-страниц.
 *
 * Тона статуса живут в `@/theme/statusTones` (ok/warning/critical/offline/info).
 * Chip по-прежнему принимает Hydroflow-имена growth/warn/alert/brand и рисует их
 * прежними классами. Badge и StatusPill берут классы из того же словаря.
 *
 *   Chip = тон + иконка. Badge = компактная метка счётчиков и статусов.
 *   Stat ≠ Card:  Stat = label + value pair, Card = container.
 */
export { default as Field } from './Field.vue'
export { default as Select } from './Select.vue'
export { default as Chip } from './Chip.vue'
export { default as Stat } from './Stat.vue'
export { default as Hint } from './Hint.vue'
export { default as KV } from './KV.vue'
export { default as ToggleField } from './ToggleField.vue'

export type { SelectOption } from './Select.vue'
export type { ChipTone } from './Chip.vue'
export type { StatTone } from './Stat.vue'
