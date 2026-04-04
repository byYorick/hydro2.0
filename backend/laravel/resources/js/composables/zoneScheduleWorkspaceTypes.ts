export interface ScheduleWorkspaceControl {
  automation_runtime: string
  control_mode: string
  allowed_manual_steps: string[]
  bundle_revision?: string | null
  generated_at?: string | null
  timezone?: string | null
}

export interface ScheduleWorkspaceCapabilities {
  executable_task_types: string[]
  planned_task_types: string[]
  /** true, если зона на AE3: Laravel scheduler диспатчит только полив */
  ae3_irrigation_only_dispatch?: boolean
  /** Типы окон в плане, для которых нет автоматического dispatch при текущем runtime */
  non_executable_planned_task_types?: string[]
  diagnostics_available: boolean
}

export interface PlanLane {
  task_type: string
  label: string
  mode: string
  enabled?: boolean
  available?: boolean
  executable?: boolean
}

export interface PlanWindow {
  plan_window_id: string
  zone_id: number
  task_type: string
  schedule_task_type?: string | null
  label: string
  schedule_key: string
  trigger_at: string
  origin: string
  state: string
  mode: string
}

export interface ExecutionLifecycleItem {
  status: string
  at: string | null
  error?: string | null
  source?: string | null
}

export interface ExecutionTimelineItem {
  event_id: string
  event_seq?: number | null
  event_type: string
  type?: string | null
  at: string | null
  task_id?: string | null
  correlation_id?: string | null
  task_type?: string | null
  stage?: string | null
  status?: string | null
  terminal_status?: string | null
  decision?: string | null
  reason_code?: string | null
  reason?: string | null
  error_code?: string | null
  node_uid?: string | null
  channel?: string | null
  cmd?: string | null
  command_submitted?: boolean | null
  command_effect_confirmed?: boolean | null
  details?: Record<string, unknown> | null
  source?: string | null
}

export interface ExecutionRun {
  execution_id: string
  task_id: string
  zone_id: number
  task_type: string
  schedule_task_type?: string | null
  status: string
  runtime_status?: string | null
  intent_status?: string | null
  intent_type?: string | null
  correlation_id?: string | null
  schedule_key?: string | null
  control_mode_snapshot?: string | null
  current_stage?: string | null
  workflow_phase?: string | null
  irrigation_mode?: string | null
  requested_duration_sec?: number | null
  decision_strategy?: string | null
  decision_config?: Record<string, unknown> | null
  decision_bundle_revision?: string | null
  decision_outcome?: string | null
  decision_reason_code?: string | null
  decision_degraded?: boolean | null
  replay_count?: number | null
  created_at?: string | null
  updated_at?: string | null
  scheduled_for?: string | null
  accepted_at?: string | null
  due_at?: string | null
  expires_at?: string | null
  completed_at?: string | null
  error_code?: string | null
  error_message?: string | null
  human_error_message?: string | null
  is_active?: boolean
  lifecycle?: ExecutionLifecycleItem[]
  timeline?: ExecutionTimelineItem[]
  timeline_preview?: ExecutionTimelineItem[]
  latest_event?: ExecutionTimelineItem | null
}

export interface ExecutionFailureSummary {
  source: string
  task_id?: string | null
  intent_id?: string | null
  task_type: string
  status: string
  error_code?: string | null
  error_message?: string | null
  human_error_message?: string | null
  at?: string | null
}

export interface ScheduleWorkspaceExecution {
  active_run: ExecutionRun | null
  recent_runs: ExecutionRun[]
  counters: {
    active: number
    completed_24h: number
    failed_24h: number
  }
  latest_failure?: ExecutionFailureSummary | null
}

export interface ScheduleWorkspacePlan {
  horizon: '24h' | '7d'
  lanes: PlanLane[]
  windows: PlanWindow[]
  summary: {
    planned_total: number
    suppressed_total: number
    missed_total: number
  }
}

export interface ScheduleWorkspace {
  control: ScheduleWorkspaceControl
  capabilities: ScheduleWorkspaceCapabilities
  plan: ScheduleWorkspacePlan
  execution: ScheduleWorkspaceExecution
}

export interface ScheduleWorkspaceResponse {
  status: string
  data?: ScheduleWorkspace
}

export interface ExecutionResponse {
  status: string
  data?: ExecutionRun
}

export interface SchedulerDiagnosticsTask {
  task_id: string
  task_type?: string | null
  schedule_key?: string | null
  correlation_id?: string | null
  status?: string | null
  accepted_at?: string | null
  due_at?: string | null
  expires_at?: string | null
  last_polled_at?: string | null
  terminal_at?: string | null
  updated_at?: string | null
  details?: Record<string, unknown> | null
}

export interface SchedulerDiagnosticsLog {
  log_id: number
  task_name?: string | null
  status?: string | null
  created_at?: string | null
  details?: Record<string, unknown> | null
}

export interface SchedulerDiagnostics {
  zone_id: number
  generated_at?: string | null
  sources: {
    dispatcher_tasks: boolean
    scheduler_logs: boolean
  }
  summary: {
    tracked_tasks_total: number
    active_tasks_total: number
    overdue_tasks_total: number
    stale_tasks_total: number
    recent_logs_total: number
    last_log_at?: string | null
  }
  dispatcher_tasks: SchedulerDiagnosticsTask[]
  recent_logs: SchedulerDiagnosticsLog[]
}

export interface SchedulerDiagnosticsResponse {
  status: string
  data?: SchedulerDiagnostics
}
