/**
 * Launch wizard shell — собственный layout (без AppLayout/BaseWizard).
 *
 *   LaunchShell (root, data-density / data-stepper)
 *   ├─ LaunchTopBar (logo + breadcrumbs + service pills + settings popover)
 *   ├─ LaunchStepper (HStepper или VStepper по prefs + media-query)
 *   ├─ <main slot> (StepHeader + текущий шаг)
 *   └─ LaunchFooterNav (sticky прогресс + Назад/Далее/Запустить)
 */
export { default as LaunchShell } from './LaunchShell.vue'
export { default as LaunchTopBar } from './LaunchTopBar.vue'
export { default as LaunchStepper } from './LaunchStepper.vue'
export { default as HStepper } from './HStepper.vue'
export { default as VStepper } from './VStepper.vue'
export { default as LaunchFooterNav } from './LaunchFooterNav.vue'
export { default as StepHeader } from './StepHeader.vue'
export { default as LaunchSettingsPopover } from './LaunchSettingsPopover.vue'

export type { LaunchStep, StepCompletion } from './types'
