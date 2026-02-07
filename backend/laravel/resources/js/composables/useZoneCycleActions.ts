import { reactive } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { logger } from '@/utils/logger'
import type { ToastHandler } from '@/composables/useApi'

interface GrowCycleRef {
  value: {
    id?: number
  } | null
}

interface ApiStatusResponse {
  data?: {
    status?: string
  }
}

interface ZoneIdRef {
  value: number | undefined
}

type SetLoadingHandler = (
  key: 'nextPhase' | 'cyclePause' | 'cycleResume' | 'cycleHarvest' | 'cycleAbort' | 'cycleChangeRecipe',
  value: boolean
) => void

interface UseZoneCycleActionsDeps {
  activeGrowCycle: GrowCycleRef
  zoneId: ZoneIdRef
  api: {
    post: (url: string, payload?: Record<string, unknown>) => Promise<ApiStatusResponse>
  }
  reloadZone: (zoneId: number | undefined, only?: string[]) => Promise<unknown> | void
  showToast: ToastHandler
  setLoading: SetLoadingHandler
  handleError: (error: unknown) => void
}

export function useZoneCycleActions({
  activeGrowCycle,
  zoneId,
  api,
  reloadZone,
  showToast,
  setLoading,
  handleError,
}: UseZoneCycleActionsDeps): {
  harvestModal: { open: boolean; batchLabel: string }
  abortModal: { open: boolean; notes: string }
  changeRecipeModal: { open: boolean; recipeRevisionId: string; applyMode: 'now' | 'next_phase' }
  closeHarvestModal: () => void
  closeAbortModal: () => void
  closeChangeRecipeModal: () => void
  onNextPhase: () => Promise<void>
  onCyclePause: () => Promise<void>
  onCycleResume: () => Promise<void>
  onCycleHarvest: () => void
  confirmHarvest: () => Promise<void>
  onCycleAbort: () => void
  confirmAbort: () => Promise<void>
  onCycleChangeRecipe: () => void
  confirmChangeRecipe: () => Promise<void>
} {
  const harvestModal = reactive<{ open: boolean; batchLabel: string }>({
    open: false,
    batchLabel: '',
  })

  const abortModal = reactive<{ open: boolean; notes: string }>({
    open: false,
    notes: '',
  })

  const changeRecipeModal = reactive<{ open: boolean; recipeRevisionId: string; applyMode: 'now' | 'next_phase' }>({
    open: false,
    recipeRevisionId: '',
    applyMode: 'now',
  })

  function closeHarvestModal(): void {
    harvestModal.open = false
    harvestModal.batchLabel = ''
  }

  function closeAbortModal(): void {
    abortModal.open = false
    abortModal.notes = ''
  }

  function closeChangeRecipeModal(): void {
    changeRecipeModal.open = false
    changeRecipeModal.recipeRevisionId = ''
    changeRecipeModal.applyMode = 'now'
  }

  async function onNextPhase(): Promise<void> {
    if (!activeGrowCycle.value?.id) {
      return
    }

    setLoading('nextPhase', true)
    try {
      const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/advance-phase`)
      if (response.data?.status === 'ok') {
        showToast('Фаза успешно изменена', 'success', TOAST_TIMEOUT.NORMAL)
        await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
      }
    } catch (err) {
      logger.error('Failed to change phase:', err)
      handleError(err)
    } finally {
      setLoading('nextPhase', false)
    }
  }

  async function onCyclePause(): Promise<void> {
    if (!activeGrowCycle.value?.id) {
      return
    }

    setLoading('cyclePause', true)
    try {
      const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/pause`)
      if (response.data?.status === 'ok') {
        showToast('Цикл приостановлен', 'success', TOAST_TIMEOUT.NORMAL)
        await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
      }
    } catch (err) {
      logger.error('Failed to pause cycle:', err)
      handleError(err)
    } finally {
      setLoading('cyclePause', false)
    }
  }

  async function onCycleResume(): Promise<void> {
    if (!activeGrowCycle.value?.id) {
      return
    }

    setLoading('cycleResume', true)
    try {
      const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/resume`)
      if (response.data?.status === 'ok') {
        showToast('Цикл возобновлен', 'success', TOAST_TIMEOUT.NORMAL)
        await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
      }
    } catch (err) {
      logger.error('Failed to resume cycle:', err)
      handleError(err)
    } finally {
      setLoading('cycleResume', false)
    }
  }

  function onCycleHarvest(): void {
    if (!activeGrowCycle.value?.id) {
      return
    }
    harvestModal.open = true
  }

  async function confirmHarvest(): Promise<void> {
    if (!activeGrowCycle.value?.id) {
      return
    }

    setLoading('cycleHarvest', true)
    try {
      const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/harvest`, {
        batch_label: harvestModal.batchLabel || undefined,
      })
      if (response.data?.status === 'ok') {
        showToast('Урожай зафиксирован, цикл закрыт', 'success', TOAST_TIMEOUT.NORMAL)
        await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
        closeHarvestModal()
      }
    } catch (err) {
      logger.error('Failed to harvest cycle:', err)
      handleError(err)
    } finally {
      setLoading('cycleHarvest', false)
    }
  }

  function onCycleAbort(): void {
    if (!activeGrowCycle.value?.id) {
      return
    }
    abortModal.open = true
  }

  async function confirmAbort(): Promise<void> {
    if (!activeGrowCycle.value?.id) {
      return
    }

    setLoading('cycleAbort', true)
    try {
      const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/abort`, {
        notes: abortModal.notes || undefined,
      })
      if (response.data?.status === 'ok') {
        showToast('Цикл аварийно остановлен', 'success', TOAST_TIMEOUT.NORMAL)
        await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
        closeAbortModal()
      }
    } catch (err) {
      logger.error('Failed to abort cycle:', err)
      handleError(err)
    } finally {
      setLoading('cycleAbort', false)
    }
  }

  function onCycleChangeRecipe(): void {
    if (!activeGrowCycle.value?.id) {
      return
    }
    changeRecipeModal.open = true
  }

  async function confirmChangeRecipe(): Promise<void> {
    if (!activeGrowCycle.value?.id) {
      return
    }

    const revisionIdNum = parseInt(changeRecipeModal.recipeRevisionId, 10)
    if (Number.isNaN(revisionIdNum)) {
      showToast('Неверный ID ревизии', 'error', TOAST_TIMEOUT.NORMAL)
      return
    }

    setLoading('cycleChangeRecipe', true)
    try {
      const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/change-recipe-revision`, {
        recipe_revision_id: revisionIdNum,
        apply_mode: changeRecipeModal.applyMode,
      })
      if (response.data?.status === 'ok') {
        showToast('Ревизия рецепта обновлена', 'success', TOAST_TIMEOUT.NORMAL)
        await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
        closeChangeRecipeModal()
      }
    } catch (err) {
      logger.error('Failed to change recipe revision:', err)
      handleError(err)
    } finally {
      setLoading('cycleChangeRecipe', false)
    }
  }

  return {
    harvestModal,
    abortModal,
    changeRecipeModal,
    closeHarvestModal,
    closeAbortModal,
    closeChangeRecipeModal,
    onNextPhase,
    onCyclePause,
    onCycleResume,
    onCycleHarvest,
    confirmHarvest,
    onCycleAbort,
    confirmAbort,
    onCycleChangeRecipe,
    confirmChangeRecipe,
  }
}
