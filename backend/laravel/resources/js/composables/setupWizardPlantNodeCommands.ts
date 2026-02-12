import type { ComputedRef, Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useNodeLifecycle } from '@/composables/useNodeLifecycle'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'
import { extractCollection } from './setupWizardCollection'
import { extractSetupWizardErrorMessage } from './setupWizardErrors'
import type {
  Node,
  Plant,
  SetupWizardDeviceAssignments,
  PlantFormState,
  SetupWizardLoadingState,
  Zone,
} from './setupWizardTypes'
import type { SetupWizardDataApiClient } from './setupWizardDataLoaders'

interface SetupWizardPlantNodeCommandsOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  availableNodes: Ref<Node[]>
  availablePlants: Ref<Plant[]>
  selectedPlantId: Ref<number | null>
  selectedZone: Ref<Zone | null>
  selectedPlant: Ref<Plant | null>
  selectedNodeIds: Ref<number[]>
  attachedNodesCount: Ref<number>
  plantForm: PlantFormState
  loaders: {
    loadPlants: () => Promise<void>
    loadAvailableNodes: () => Promise<void>
  }
}

export interface SetupWizardPlantNodeCommandActions {
  createPlant: () => Promise<void>
  selectPlant: () => void
  attachNodesToZone: (assignments?: SetupWizardDeviceAssignments | null) => Promise<void>
  isNodeAttachedToCurrentZone: (nodeId: number) => boolean
}

export function canSelectPlant(canConfigure: boolean, selectedPlantId: number | null): boolean {
  return canConfigure && selectedPlantId !== null
}

export function resolveSelectedPlant(plants: Plant[], selectedPlantId: number | null): Plant | null {
  if (!selectedPlantId) {
    return null
  }

  return plants.find((item) => item.id === selectedPlantId) ?? null
}

const NODE_BINDING_POLL_INTERVAL_MS = 3000
const NODE_BINDING_MAX_ATTEMPTS = 4
const NODE_BINDING_INFO_TIMEOUT_MS = 5000
const DEVICE_ROLE_LABELS: Record<keyof SetupWizardDeviceAssignments, string> = {
  irrigation: 'полив',
  ph_correction: 'коррекция pH',
  ec_correction: 'коррекция EC',
  accumulation: 'накопительный узел',
  climate: 'климат',
  light: 'свет',
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

function parseNodeUpdate(payload: unknown): Node | null {
  const node = extractData<unknown>(payload)
  if (!node || typeof node !== 'object' || !('id' in node)) {
    return null
  }

  return node as Node
}

function hasRequiredAssignments(assignments: SetupWizardDeviceAssignments): boolean {
  return (
    typeof assignments.irrigation === 'number'
    && typeof assignments.ph_correction === 'number'
    && typeof assignments.ec_correction === 'number'
    && typeof assignments.accumulation === 'number'
  )
}

export function createSetupWizardPlantNodeCommands(
  options: SetupWizardPlantNodeCommandsOptions
): SetupWizardPlantNodeCommandActions {
  const {
    api,
    loading,
    canConfigure,
    showToast,
    availableNodes,
    availablePlants,
    selectedPlantId,
    selectedZone,
    selectedPlant,
    selectedNodeIds,
    attachedNodesCount,
    plantForm,
    loaders,
  } = options
  const toastHandler = (
    message: string,
    variant: ToastVariant = 'info',
    timeout?: number
  ): number => {
    showToast(message, variant, timeout)
    return 0
  }
  const { canAssignToZone, getStateLabel } = useNodeLifecycle(toastHandler)
  const { handleError } = useErrorHandler(toastHandler)
  const attachedNodeIds = new Set<number>()
  let attachedZoneId: number | null = null

  function getNodeById(nodeId: number): Node | null {
    return availableNodes.value.find((item) => item.id === nodeId) ?? null
  }

  function isNodeAttachedToCurrentZone(nodeId: number): boolean {
    const currentZoneId = selectedZone.value?.id ?? null
    if (!currentZoneId || attachedZoneId !== currentZoneId) {
      return false
    }

    return attachedNodeIds.has(nodeId)
  }

  function getNodeLabel(nodeId: number): string {
    const node = getNodeById(nodeId)
    return node?.uid || node?.name || `Node #${nodeId}`
  }

  async function waitForBindingConfirmation(nodeIds: number[]): Promise<{ confirmed: number[]; pending: number[] }> {
    const pending = new Set<number>(nodeIds)
    const confirmed = new Set<number>()

    for (let attempt = 0; attempt < NODE_BINDING_MAX_ATTEMPTS && pending.size > 0; attempt += 1) {
      try {
        const response = await api.get('/nodes', {
          params: { unassigned: true },
        })
        const unassignedNodes = extractCollection<Node>(response.data)
        const unassignedIds = new Set(unassignedNodes.map((node) => node.id))

        Array.from(pending).forEach((nodeId) => {
          if (!unassignedIds.has(nodeId)) {
            pending.delete(nodeId)
            confirmed.add(nodeId)
          }
        })
      } catch (error) {
        logger.error('[Setup/Wizard] Failed while waiting for node binding confirmation', { error })
        showToast('Ошибка проверки ответа от ноды. Повторите обновление списка устройств.', 'error', TOAST_TIMEOUT.NORMAL)
        break
      }

      if (pending.size > 0 && attempt < NODE_BINDING_MAX_ATTEMPTS - 1) {
        await sleep(NODE_BINDING_POLL_INTERVAL_MS)
      }
    }

    return {
      confirmed: Array.from(confirmed),
      pending: Array.from(pending),
    }
  }

  function unresolvedAssignmentRoles(
    assignments: SetupWizardDeviceAssignments,
    confirmedNodeIdSet: Set<number>
  ): string[] {
    return (Object.keys(assignments) as Array<keyof SetupWizardDeviceAssignments>)
      .filter((role) => {
        const nodeId = assignments[role]
        return typeof nodeId === 'number' && !confirmedNodeIdSet.has(nodeId)
      })
      .map((role) => DEVICE_ROLE_LABELS[role])
  }

  async function canAssignNodeToZone(node: Node): Promise<boolean> {
    if (node.lifecycle_state && node.lifecycle_state !== 'REGISTERED_BACKEND') {
      const currentStateLabel = getStateLabel(node.lifecycle_state as Parameters<typeof getStateLabel>[0])
      showToast(
        `Узел не может быть присвоен к зоне. Текущее состояние: ${currentStateLabel}. Требуется: Зарегистрирован (REGISTERED_BACKEND)`,
        'error',
        6000
      )
      return false
    }

    if (!node.lifecycle_state) {
      try {
        const canAssign = await canAssignToZone(node.id)
        if (!canAssign) {
          showToast(
            'Узел не может быть присвоен к зоне. Узел должен быть зарегистрирован (REGISTERED_BACKEND) перед присвоением.',
            'error',
            6000
          )
          return false
        }
      } catch (error) {
        logger.warn('[Setup/Wizard] Failed to check lifecycle state, proceeding with assignment', { error, node_id: node.id })
      }
    }

    return true
  }

  async function assignNodeByDevicesFlow(nodeId: number, zoneId: number): Promise<'confirmed' | 'pending' | 'failed'> {
    const node = getNodeById(nodeId)
    const label = node?.uid || node?.name || `Node #${nodeId}`

    if (!node) {
      showToast(`Нода "${label}" не найдена в списке доступных. Обновите список устройств.`, 'error', TOAST_TIMEOUT.NORMAL)
      return 'failed'
    }

    const lifecycleAllowed = await canAssignNodeToZone(node)
    if (!lifecycleAllowed) {
      return 'failed'
    }

    try {
      const response = await api.patch(`/nodes/${nodeId}`, {
        zone_id: zoneId,
        name: node.name || node.uid || `Node #${nodeId}`,
      })
      const updatedNode = parseNodeUpdate(response.data)

      if (updatedNode?.lifecycle_state === 'ASSIGNED_TO_ZONE') {
        showToast(`Нода "${label}" успешно привязана к зоне и отправила конфиг`, 'success', TOAST_TIMEOUT.NORMAL)
        return 'confirmed'
      }

      if (updatedNode?.pending_zone_id && !updatedNode?.zone_id) {
        showToast(
          `Нода "${label}" привязывается к зоне. Ждём config_report от ноды (~2-5 сек)...`,
          'info',
          NODE_BINDING_INFO_TIMEOUT_MS
        )
        return 'pending'
      }

      if (updatedNode?.zone_id && !updatedNode?.pending_zone_id) {
        showToast(`Нода "${label}" успешно привязана к зоне!`, 'success', TOAST_TIMEOUT.NORMAL)
        return 'confirmed'
      }

      logger.warn('[Setup/Wizard] Unexpected node state after assignment', {
        node_id: nodeId,
        zone_id: updatedNode?.zone_id ?? null,
        pending_zone_id: updatedNode?.pending_zone_id ?? null,
        lifecycle_state: updatedNode?.lifecycle_state ?? null,
      })
      showToast(`Нода "${label}" обновлена. Проверьте статус через несколько секунд.`, 'warning', TOAST_TIMEOUT.LONG)
      return 'pending'
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to assign node', { error, node_id: nodeId, zone_id: zoneId })
      handleError(error, {
        component: 'Setup/Wizard',
        action: 'attachNodesToZone',
        nodeId,
        zoneId,
      })

      const errorMessage = String((error as { response?: { data?: { message?: string } } })?.response?.data?.message || '')
      const normalizedErrorMessage = errorMessage.toLowerCase()
      if (normalizedErrorMessage.includes('lifecycle') || normalizedErrorMessage.includes('state') || normalizedErrorMessage.includes('состояни')) {
        showToast(
          `Ошибка lifecycle: ${errorMessage}. Убедитесь, что узел в состоянии REGISTERED_BACKEND.`,
          'error',
          7000
        )
      }

      return 'failed'
    }
  }

  async function createPlant(): Promise<void> {
    if (!canConfigure.value || !plantForm.name.trim()) {
      return
    }

    loading.stepPlant = true
    try {
      const response = await api.post('/plants', {
        name: plantForm.name,
        species: plantForm.species || null,
        variety: plantForm.variety || null,
      })

      const payload = extractData<Record<string, unknown>>(response.data)
      const plantId = typeof payload?.id === 'number' ? payload.id : null
      if (!plantId) {
        throw new Error('Plant id missing in response')
      }

      selectedPlant.value = {
        id: plantId,
        name: plantForm.name,
      }
      selectedPlantId.value = plantId

      showToast('Растение создано', 'success', TOAST_TIMEOUT.NORMAL)
      await loaders.loadPlants()
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to create plant', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось создать растение'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepPlant = false
    }
  }

  function selectPlant(): void {
    if (!canSelectPlant(canConfigure.value, selectedPlantId.value)) {
      return
    }

    const plant = resolveSelectedPlant(availablePlants.value, selectedPlantId.value)
    if (!plant) {
      return
    }

    selectedPlant.value = plant
    showToast('Растение выбрано', 'success', TOAST_TIMEOUT.NORMAL)
  }

  async function attachNodesToZone(assignments?: SetupWizardDeviceAssignments | null): Promise<void> {
    const zoneId = selectedZone.value?.id ?? null
    if (!canConfigure.value || !zoneId || selectedNodeIds.value.length === 0) {
      return
    }

    if (attachedZoneId !== zoneId) {
      attachedNodeIds.clear()
      attachedZoneId = zoneId
    }

    const nodeIds = [...selectedNodeIds.value]
    const failedNodeIds = new Set<number>()
    const waitingNodeIds = new Set<number>()
    const shouldValidateAndApplyBindings = Boolean(assignments && hasRequiredAssignments(assignments))

    loading.stepDevices = true
    try {
      if (assignments && shouldValidateAndApplyBindings) {
        await api.post('/setup-wizard/validate-devices', {
          zone_id: zoneId,
          assignments,
          selected_node_ids: nodeIds,
        })
      }

      showToast('Отправляем конфиг на выбранные ноды...', 'info', TOAST_TIMEOUT.NORMAL)
      for (const nodeId of nodeIds) {
        if (attachedNodeIds.has(nodeId)) {
          continue
        }

        const assignmentState = await assignNodeByDevicesFlow(nodeId, zoneId)
        if (assignmentState === 'confirmed') {
          attachedNodeIds.add(nodeId)
          continue
        }
        if (assignmentState === 'pending') {
          waitingNodeIds.add(nodeId)
          continue
        }
        failedNodeIds.add(nodeId)
      }

      if (failedNodeIds.size > 0) {
        showToast(
          `Ошибка отправки конфига для ${failedNodeIds.size} нод. Проверьте состояние и повторите.`,
          'error',
          TOAST_TIMEOUT.NORMAL
        )
      }

      if (waitingNodeIds.size > 0) {
        const { confirmed, pending } = await waitForBindingConfirmation(Array.from(waitingNodeIds))
        confirmed.forEach((nodeId) => {
          attachedNodeIds.add(nodeId)
          const label = getNodeLabel(nodeId)
          showToast(`Нода "${label}" успешно привязана к зоне!`, 'success', TOAST_TIMEOUT.NORMAL)
        })

        pending.forEach((nodeId) => {
          const label = getNodeLabel(nodeId)
          showToast(`Нода "${label}" не подтвердила привязку. Ответ от ноды не получен.`, 'error', TOAST_TIMEOUT.LONG)
        })
      }

      if (assignments && shouldValidateAndApplyBindings) {
        const unresolvedRoles = unresolvedAssignmentRoles(assignments, attachedNodeIds)
        if (unresolvedRoles.length > 0) {
          showToast(
            `Привязка не завершена: нет подтверждения по ролям ${unresolvedRoles.join(', ')}.`,
            'error',
            TOAST_TIMEOUT.LONG
          )
        } else {
          await api.post('/setup-wizard/apply-device-bindings', {
            zone_id: zoneId,
            assignments,
            selected_node_ids: nodeIds,
          })
        }
      }

      attachedNodesCount.value = attachedNodeIds.size
      showToast(`Подтверждено привязанных узлов: ${attachedNodesCount.value}`, 'success', TOAST_TIMEOUT.NORMAL)

      const retryNodeIds = [
        ...Array.from(waitingNodeIds).filter((nodeId) => !attachedNodeIds.has(nodeId)),
        ...Array.from(failedNodeIds),
      ]
      selectedNodeIds.value = Array.from(new Set(retryNodeIds))
      await loaders.loadAvailableNodes()
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to attach nodes', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось привязать устройства к зоне'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepDevices = false
    }
  }

  return {
    createPlant,
    selectPlant,
    attachNodesToZone,
    isNodeAttachedToCurrentZone,
  }
}
