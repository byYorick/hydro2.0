import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface UrlStateOptions<T> {
  key: string
  defaultValue: T
  parse?: (value: string | null) => T
  serialize?: (value: T) => string | null
  debounceMs?: number
}

export function useUrlState<T>(options: UrlStateOptions<T>) {
  const { key, defaultValue, debounceMs } = options
  const parse = options.parse ?? ((value: string | null) => (value === null ? defaultValue : (value as unknown as T)))
  const serialize = options.serialize ?? ((value: T) => String(value))

  const state = ref<T>(defaultValue)

  const readFromUrl = (): T => {
    if (typeof window === 'undefined') return defaultValue
    const params = new URLSearchParams(window.location.search)
    return parse(params.get(key))
  }

  const writeToUrl = (value: T): void => {
    if (typeof window === 'undefined') return

    const url = new URL(window.location.href)
    const serialized = serialize(value)
    const shouldClear = Object.is(value, defaultValue) || serialized === null || serialized === ''

    if (shouldClear) {
      url.searchParams.delete(key)
    } else {
      url.searchParams.set(key, serialized)
    }

    const nextUrl = `${url.pathname}${url.search}${url.hash}`
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
    if (nextUrl !== currentUrl) {
      window.history.replaceState(window.history.state, '', nextUrl)
    }
  }

  const syncFromUrl = (): void => {
    const nextValue = readFromUrl()
    if (!Object.is(nextValue, state.value)) {
      state.value = nextValue
    }
  }

  if (typeof window !== 'undefined') {
    state.value = readFromUrl()
  }

  let debounceTimer: number | null = null

  watch(state, (value) => {
    if (!debounceMs) {
      writeToUrl(value)
      return
    }

    if (debounceTimer !== null) {
      window.clearTimeout(debounceTimer)
    }

    debounceTimer = window.setTimeout(() => {
      writeToUrl(value)
      debounceTimer = null
    }, debounceMs)
  })

  onMounted(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('popstate', syncFromUrl)
    }
  })

  onBeforeUnmount(() => {
    if (debounceTimer !== null) {
      window.clearTimeout(debounceTimer)
    }

    if (typeof window !== 'undefined') {
      window.removeEventListener('popstate', syncFromUrl)
    }
  })

  return state
}
