import { computed, type Ref } from 'vue'
import type { ScheduleWorkspace } from './zoneScheduleWorkspaceTypes'
import type { AutomationState } from '@/types/Automation'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import { laneLabel, workflowStageLabel, formatDateTime } from '@/utils/schedulerLabels'

export function useSchedulerAttention(workspace: Ref<ScheduleWorkspace | null>, state: Ref<AutomationState | null>) {
  type Entry = { tone: 'danger' | 'warning' | 'info'; title: string; detail: string | null }
  const attentionAlerts = computed<Entry[]>(() => {
    const view = workspace.value
    if (!view) return []
    const items: Entry[] = []
    if (view.control?.control_mode === 'manual') items.push({ tone: 'info', title: 'Зона в ручном режиме', detail: 'Наличие расписания не означает автоматический запуск. Проверьте режим управления перед ожиданием полива.' })
    const failure = view.execution.latest_failure
    if (failure) items.push({ tone: 'warning', title: `Последняя ошибка: ${laneLabel(failure.task_type)} · ${resolveHumanErrorMessage({ code: failure.error_code, message: failure.error_message, humanMessage: failure.human_error_message }, 'Причина не указана')}`, detail: `${formatDateTime(failure.at)}. Это запись из истории, а не подтверждение текущего аварийного состояния.` })
    const missing = view.capabilities?.non_executable_planned_task_types ?? view.plan.lanes.filter(lane => !lane.executable).map(lane => lane.task_type)
    if (missing.length) items.push({ tone: 'warning', title: 'Часть расписаний служит только для отображения плана', detail: `Автоматически не запускаются: ${missing.map(laneLabel).join(', ')}. Проверьте поддерживаемые типы задач перед ожиданием выполнения.` })
    if (view.execution.counters?.failed_24h > 0) items.push({ tone: 'warning', title: `Ошибок за 24 часа: ${view.execution.counters?.failed_24h}`, detail: 'Откройте историю и выберите запуск с ошибкой. Устраните причину перед повтором.' })
    if (view.execution.active_run && state.value?.state_details?.failed) items.unshift({ tone: 'danger', title: `Сбой автоматики: ${state.value.state_label}`, detail: workflowStageLabel(state.value.current_stage) })
    return items.slice(0, 4)
  })
  const attentionStatus = computed<Entry[]>(() => {
    if (!workspace.value?.execution.active_run || !state.value?.state_label || state.value.state_details?.failed) return []
    return [{ tone: 'info', title: `Состояние процесса: ${state.value.state_label}`, detail: workflowStageLabel(state.value.current_stage) }]
  })
  return { attentionAlerts, attentionStatus }
}
