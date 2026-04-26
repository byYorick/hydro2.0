/**
 * Launch wizard user preferences (density / stepper layout / show hints).
 *
 * Persisted in localStorage (key `hydro.launch.prefs`). State is module-level
 * singleton — все компоненты, которые вызывают `useLaunchPreferences()`,
 * получают один и тот же reactive объект.
 *
 * Применение в LaunchShell.vue: атрибуты `data-density` / `data-stepper`
 * на корне контейнера, чтобы CSS/Tailwind мог реагировать (см. реф hydroflow).
 */
import { computed, reactive, watch } from 'vue'

export type LaunchDensity = 'compact' | 'comfortable'
export type LaunchStepper = 'horizontal' | 'vertical'

export interface LaunchPreferences {
  density: LaunchDensity
  stepper: LaunchStepper
  showHints: boolean
}

const STORAGE_KEY = 'hydro.launch.prefs'
const DEFAULTS: LaunchPreferences = {
  density: 'compact',
  stepper: 'horizontal',
  showHints: true,
}

function load(): LaunchPreferences {
  if (typeof localStorage === 'undefined') return { ...DEFAULTS }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<LaunchPreferences>
    return {
      density: parsed.density === 'comfortable' ? 'comfortable' : 'compact',
      stepper: parsed.stepper === 'vertical' ? 'vertical' : 'horizontal',
      showHints: parsed.showHints !== false,
    }
  } catch {
    return { ...DEFAULTS }
  }
}

const state = reactive<LaunchPreferences>(load())

watch(
  () => ({ ...state }),
  (next) => {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // localStorage unavailable / quota exceeded — silently ignore
    }
  },
  { deep: true },
)

export function useLaunchPreferences() {
  return {
    state,
    density: computed(() => state.density),
    stepper: computed(() => state.stepper),
    showHints: computed(() => state.showHints),
    setDensity: (v: LaunchDensity) => {
      state.density = v
    },
    setStepper: (v: LaunchStepper) => {
      state.stepper = v
    },
    setShowHints: (v: boolean) => {
      state.showHints = v
    },
  }
}

/** Test-only: reset singleton to defaults (for isolated specs). */
export function _resetLaunchPreferencesForTests(): void {
  state.density = DEFAULTS.density
  state.stepper = DEFAULTS.stepper
  state.showHints = DEFAULTS.showHints
}
