import { computed, onBeforeUnmount, ref } from 'vue'
import { useAutomationConfig, type AutomationDocument } from '@/composables/useAutomationConfig'
import type { AutomationRuntimeSettingSection } from '@/types/SystemSettings'
import type { ToastHandler } from '@/services/api'
import { buildRuntimePatch, isRuntimeFieldDirty, runtimeFieldError, runtimeItems, type RuntimeDraft } from '@/utils/automationRuntimeDraft'

interface RuntimeDocument extends AutomationDocument {
  snapshot?: { generated_at?: string; sections?: AutomationRuntimeSettingSection[] }
}

export function useAutomationRuntimeSettings(showToast: ToastHandler) {
  // This editor owns error messages; avoid duplicate global + local toasts.
  const config = useAutomationConfig()
  const document = ref<RuntimeDocument | null>(null)
  const draft = ref<RuntimeDraft>({})
  const loading = ref(false)
  const saving = ref(false)
  const resetting = ref(false)
  const error = ref<string | null>(null)
  const sections = computed(() => document.value?.snapshot?.sections ?? [])
  const items = computed(() => runtimeItems(sections.value))
  const dirtyCount = computed(() => items.value.filter(item => isRuntimeFieldDirty(item, draft.value[item.key])).length)
  const errors = computed(() => Object.fromEntries(items.value.flatMap(item => {
    const message = runtimeFieldError(item, draft.value[item.key])
    return message ? [[item.key, message]] : []
  })))
  const busy = computed(() => loading.value || saving.value || resetting.value)
  const canSave = computed(() => !busy.value && dirtyCount.value > 0 && Object.keys(errors.value).length === 0)
  const updatedAt = computed(() => document.value?.snapshot?.generated_at ?? null)

  function discard() {
    draft.value = Object.fromEntries(items.value.map(item => [item.key, item.value])) as RuntimeDraft
    error.value = null
  }
  function apply(value: RuntimeDocument) {
    document.value = value
    discard()
  }
  function report(cause: unknown, fallback: string) {
    const response = (cause as { response?: { data?: { message?: string; errors?: Record<string, string[]> } } })?.response?.data
    const detail = response?.errors && Object.values(response.errors).flat().find(value => typeof value === 'string')
    error.value = detail || response?.message || (cause instanceof Error ? cause.message : fallback)
    showToast(error.value, 'error')
  }
  async function load(options: { silent?: boolean; discard?: boolean } = {}) {
    if (busy.value || (dirtyCount.value > 0 && !options.discard)) return
    loading.value = true
    error.value = null
    try {
      apply(await config.getDocument('system', 0, 'system.runtime') as RuntimeDocument)
      if (!options.silent) showToast('Настройки AE3 и планировщика обновлены.', 'success')
    } catch (cause) {
      report(cause, 'Не удалось загрузить настройки.')
    } finally { loading.value = false }
  }
  async function save() {
    if (!canSave.value) return
    saving.value = true
    error.value = null
    try {
      apply(await config.updateDocument('system', 0, 'system.runtime', buildRuntimePatch(sections.value, draft.value)) as RuntimeDocument)
      showToast('Изменения настроек сохранены.', 'success')
    } catch (cause) {
      report(cause, 'Не удалось сохранить настройки.')
    } finally { saving.value = false }
  }
  async function reset(): Promise<boolean> {
    if (busy.value) return false
    resetting.value = true
    error.value = null
    try {
      apply(await config.resetDocument('system', 0, 'system.runtime') as RuntimeDocument)
      showToast('Настройки восстановлены к значениям по умолчанию.', 'success')
      return true
    } catch (cause) {
      report(cause, 'Не удалось сбросить настройки.')
      return false
    } finally { resetting.value = false }
  }
  function beforeUnload(event: BeforeUnloadEvent) {
    if (!dirtyCount.value) return
    event.preventDefault()
    event.returnValue = ''
  }
  function beforeVisit(event: Event) {
    if (dirtyCount.value && !window.confirm('Изменения настроек не сохранены. Покинуть страницу?')) event.preventDefault()
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', beforeUnload)
    document.addEventListener('inertia:before', beforeVisit)
  }
  onBeforeUnmount(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('beforeunload', beforeUnload)
      document.removeEventListener('inertia:before', beforeVisit)
    }
  })
  return { sections, draft, loading, saving, resetting, busy, error, errors, dirtyCount, canSave, updatedAt, load, save, reset, discard }
}
