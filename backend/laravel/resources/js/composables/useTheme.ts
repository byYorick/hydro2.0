import { computed, ref, watch } from 'vue'

type ThemeMode = 'light' | 'dark'

const THEME_STORAGE_KEY = 'hydro.ui.theme'

function getInitialTheme(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'dark'
  }

  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') {
    return stored
  }

  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches
  return prefersDark ? 'dark' : 'light'
}

const theme = ref<ThemeMode>(getInitialTheme())

function applyTheme(value: ThemeMode) {
  if (typeof document === 'undefined') {
    return
  }

  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
}

applyTheme(theme.value)

watch(theme, (value) => {
  applyTheme(value)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(THEME_STORAGE_KEY, value)
  }
})

export function useTheme() {
  const isDark = computed(() => theme.value === 'dark')

  function setTheme(value: ThemeMode) {
    theme.value = value
  }

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return {
    theme,
    isDark,
    setTheme,
    toggleTheme,
  }
}
