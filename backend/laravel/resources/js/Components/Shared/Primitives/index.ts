/**
 * Hydroflow UI primitives — atomic building blocks для launch wizard и cockpit-страниц.
 *
 * Эти примитивы НЕ заменяют существующие Button/Card/Badge/TextInput, а дополняют
 * их под Hydroflow-палитру (--brand/--growth/--warn/--alert) и tone-based composition.
 *
 *   Chip ≠ Badge: Chip = tone+icon (статусы), Badge = success/warning/danger (счётчики).
 *   Stat ≠ Card:  Stat = label + value pair, Card = container.
 */
export { default as Field } from './Field.vue'
export { default as Select } from './Select.vue'
export { default as Chip } from './Chip.vue'
export { default as Stat } from './Stat.vue'
export { default as Hint } from './Hint.vue'
export { default as KV } from './KV.vue'

export type { SelectOption } from './Select.vue'
export type { ChipTone } from './Chip.vue'
export type { StatTone } from './Stat.vue'
